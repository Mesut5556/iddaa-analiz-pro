"""V3.14 persistent settlement engine.
Reads only locked/pending Supabase ledger rows, matches them to finished Fixture Download
matches, computes hit/loss and virtual P/L, and PATCHes settlement fields only.
Pre-match odds/bookmaker/locked_at are never modified.
"""
from datetime import datetime, timezone
import json
import re
import unicodedata
import urllib.parse
import urllib.request
import urllib.error

import pandas as pd
import streamlit as st

TABLE = "odds_records"


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


def _headers(key, prefer=None):
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _token(value):
    value = unicodedata.normalize("NFKD", str(value).casefold().replace("ı", "i"))
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    aliases = {
        "istanbul basaksehir": "basaksehir", "basaksehir": "basaksehir",
        "gaziantep fk": "gaziantep", "gaziantep": "gaziantep",
        "amed sportif faaliyetler": "amedspor", "amed": "amedspor", "amedspor": "amedspor",
        "erzurumspor fk": "erzurumspor", "erzurumspor": "erzurumspor",
        "eyupspor": "eyupspor", "caykur rizespor": "rizespor", "rizespor": "rizespor",
        "genclerbirligi": "genclerbirligi", "genclerbirligi sk": "genclerbirligi",
        "fenerbahce istanbul": "fenerbahce", "fenerbahce": "fenerbahce",
        "galatasaray istanbul": "galatasaray", "galatasaray": "galatasaray",
        "besiktas istanbul": "besiktas", "besiktas": "besiktas",
        "kasimpasa istanbul": "kasimpasa", "kasimpasa": "kasimpasa",
        "goztepe izmir": "goztepe", "goztepe": "goztepe",
        "corum fk": "corum", "corum": "corum",
    }
    return aliases.get(value, value.replace(" ", ""))


def _pending_rows(url, key):
    params = urllib.parse.urlencode({
        "select": "*",
        "status": "eq.BEKLIYOR",
        "order": "locked_at.asc",
    })
    req = urllib.request.Request(
        f"{url}/rest/v1/{TABLE}?{params}", headers=_headers(key), method="GET"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, list) else []


def _as_ts(value):
    try:
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("Europe/Istanbul")
        else:
            ts = ts.tz_convert("Europe/Istanbul")
        return ts
    except Exception:
        return None


def _find_finished(row, completed):
    if completed is None or completed.empty:
        return None
    h, a = _token(row.get("home_team", "")), _token(row.get("away_team", ""))
    if not h or not a:
        return None
    candidates = completed[
        completed.apply(lambda r: _token(r.get("home", "")) == h and _token(r.get("away", "")) == a, axis=1)
    ].copy()
    if candidates.empty:
        return None
    wanted = _as_ts(row.get("match_date"))
    if wanted is not None:
        candidates["_delta"] = candidates["datetime"].apply(
            lambda x: abs((_as_ts(x) - wanted).total_seconds()) if _as_ts(x) is not None else 10**12
        )
        candidates = candidates[candidates["_delta"] <= 36 * 3600].sort_values("_delta")
    if len(candidates) != 1:
        return None
    return candidates.iloc[0]


def _is_hit(selection, hg, ag):
    pick = str(selection or "").strip()
    result = "1" if hg > ag else "X" if hg == ag else "2"
    total = hg + ag
    if pick == "1": return result == "1"
    if pick == "X": return result == "X"
    if pick == "2": return result == "2"
    if pick == "1X": return result in ("1", "X")
    if pick == "X2": return result in ("X", "2")
    if pick == "12": return result in ("1", "2")
    if pick == "1.5 Üst": return total >= 2
    if pick == "1.5 Alt": return total <= 1
    if pick == "2.5 Üst": return total >= 3
    if pick == "2.5 Alt": return total <= 2
    if pick == "KG Var": return hg > 0 and ag > 0
    if pick == "KG Yok": return hg == 0 or ag == 0
    return None


def _patch(url, key, row, update):
    # Filter on the immutable composite identity so another market can never be overwritten.
    params = urllib.parse.urlencode({
        "match_key": f"eq.{row.get('match_key','')}",
        "market": f"eq.{row.get('market','')}",
        "selection": f"eq.{row.get('selection','')}",
        "status": "eq.BEKLIYOR",
    })
    body = json.dumps(update).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/rest/v1/{TABLE}?{params}", data=body,
        headers=_headers(key, "return=representation"), method="PATCH"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        returned = json.loads(resp.read().decode("utf-8") or "[]")
    return len(returned) if isinstance(returned, list) else 0


def settle_locked_records(completed):
    """Settle every still-pending locked row whose finished match is uniquely verified."""
    url, key = _cfg()
    if not (url.startswith("https://") and key):
        return {"settled": 0, "wins": 0, "losses": 0, "net": 0.0,
                "error": "Supabase URL veya Secret key bulunamadı."}
    try:
        rows = _pending_rows(url, key)
    except Exception as exc:
        return {"settled": 0, "wins": 0, "losses": 0, "net": 0.0,
                "error": "Supabase bekleyen kayıtları okunamadı: " + str(exc)[:140]}

    settled = wins = losses = 0
    net = 0.0
    skipped = 0
    for row in rows:
        match = _find_finished(row, completed)
        if match is None:
            skipped += 1
            continue
        try:
            hg, ag = int(match["home_goals"]), int(match["away_goals"])
            hit = _is_hit(row.get("selection"), hg, ag)
            if hit is None:
                skipped += 1
                continue
            stake = float(row.get("stake") or 100.0)
            odds = float(row.get("odds") or 0.0)
            if odds < 1.0 or stake <= 0:
                skipped += 1
                continue
            pl = round(stake * (odds - 1.0) if hit else -stake, 2)
            update = {
                "status": "BILDI" if hit else "BILEMEDI",
                "home_score": hg,
                "away_score": ag,
                "is_hit": bool(hit),
                "profit_loss": pl,
                "settled_at": datetime.now(timezone.utc).isoformat(),
            }
            changed = _patch(url, key, row, update)
            if changed:
                settled += 1
                wins += int(hit)
                losses += int(not hit)
                net += pl
        except Exception:
            skipped += 1
            continue
    return {"settled": settled, "wins": wins, "losses": losses,
            "net": round(net, 2), "pending": len(rows), "skipped": skipped}
