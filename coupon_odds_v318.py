"""V3.18 read-only bridge from the persistent pre-match odds ledger to Coupon Center.
Never writes or replaces odds. It only uses already locked odds_records rows.
"""
import json
import urllib.parse
import urllib.request
import unicodedata

import pandas as pd
import streamlit as st


def _cfg():
    try:
        url = str(st.secrets.get("SUPABASE_URL", "")).strip().rstrip("/")
        key = str(
            st.secrets.get("SUPABASE_SECRET_KEY", "")
            or st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")
            or st.secrets.get("SUPABASE_KEY", "")
        ).strip()
    except Exception:
        return "", ""
    return url, key


def _norm(value):
    s = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").casefold()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s).split())


def _split_match(name):
    text = str(name or "")
    for sep in (" - ", " – ", " — ", " vs ", " VS "):
        if sep in text:
            a, b = text.split(sep, 1)
            return a.strip(), b.strip()
    return "", ""


@st.cache_data(ttl=60, show_spinner=False)
def load_locked_odds():
    url, key = _cfg()
    if not (url.startswith("https://") and key):
        return [], "Oran defteri bağlantısı yok: uygun Supabase sunucu anahtarı bulunamadı."
    query = urllib.parse.urlencode({"select": "*", "order": "locked_at.asc"})
    req = urllib.request.Request(
        f"{url}/rest/v1/odds_records?{query}",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        return (raw if isinstance(raw, list) else []), None
    except Exception as exc:
        return [], f"Oran defteri okunamadı: {str(exc)[:120]}"


def _match_record(item, records):
    home, away = _split_match(item.get("Maç"))
    selection = str(item.get("Pazar") or "").strip().upper()
    if not home or not away or not selection:
        return None
    target = pd.to_datetime(item.get("Tarih"), errors="coerce", utc=True)
    candidates = []
    for r in records:
        if not isinstance(r, dict):
            continue
        if _norm(r.get("home_team")) != _norm(home) or _norm(r.get("away_team")) != _norm(away):
            continue
        if str(r.get("selection") or "").strip().upper() != selection:
            continue
        try:
            odd = float(r.get("odds"))
        except (TypeError, ValueError):
            continue
        if odd < 1.01:
            continue
        rec_time = pd.to_datetime(r.get("match_date"), errors="coerce", utc=True)
        delta = abs(rec_time - target) if pd.notna(target) and pd.notna(rec_time) else pd.Timedelta(0)
        if pd.notna(target) and pd.notna(rec_time) and delta > pd.Timedelta(hours=36):
            continue
        candidates.append((delta, r))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def enrich_coupon(coupon):
    """Return a copy enriched only with immutable, previously locked pre-match odds."""
    if coupon is None or coupon.empty:
        return coupon.copy() if coupon is not None else pd.DataFrame(), {"matched": 0, "total": 0, "error": None}
    records, error = load_locked_odds()
    out = coupon.copy()
    odds, sources = [], []
    for _, item in out.iterrows():
        r = _match_record(item, records)
        if r:
            odds.append(float(r["odds"]))
            sources.append(str(r.get("bookmaker") or "—"))
        else:
            odds.append(None)
            sources.append(None)
    out["Maç Önü Oran"] = odds
    out["Oran Kaynağı"] = sources
    matched = sum(x is not None for x in odds)
    return out, {"matched": matched, "total": len(out), "error": error}


def combined_odds(coupon):
    if coupon is None or coupon.empty or "Maç Önü Oran" not in coupon.columns:
        return None
    vals = pd.to_numeric(coupon["Maç Önü Oran"], errors="coerce")
    if vals.isna().any() or (vals < 1.01).any():
        return None
    result = 1.0
    for value in vals:
        result *= float(value)
    return result
