"""V3.47 account UI polish + immutable coupon snapshot + guarded automatic settlement + settlement audit + duplicate-safe saving + safe deletion.
Uses Supabase Auth/RLS. Settlement only consumes finished fixtures supplied by app.py.
V3.47 does not alter the V3.14 decision engine or any locked pre-match odds.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
import hashlib
from datetime import datetime

import pandas as pd
import streamlit as st


def _cfg():
    try:
        url = str(st.secrets.get("SUPABASE_URL", "")).strip().rstrip("/")
        key = str(st.secrets.get("SUPABASE_ANON_KEY", "") or st.secrets.get("SUPABASE_KEY", "")).strip()
    except Exception:
        return "", ""
    return url, key


def _request(path, method="GET", body=None, token=None, query=None, prefer=None):
    url, key = _cfg()
    if not (url.startswith("https://") and key):
        raise ValueError("SUPABASE_URL ve SUPABASE_ANON_KEY (veya SUPABASE_KEY) gerekli.")
    endpoint = url + path
    if query:
        endpoint += "?" + urllib.parse.urlencode(query)
    headers = {"apikey": key, "Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(endpoint, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(raw)
            msg = parsed.get("msg") or parsed.get("message") or parsed.get("error_description")
        except Exception:
            msg = None
        raise ValueError(msg or f"Supabase HTTP {exc.code}: {raw[:120]}") from None
    except urllib.error.URLError:
        raise ValueError("Supabase sunucusuna erişilemedi.") from None


def current_user(): return st.session_state.get("v315_user")
def access_token(): return st.session_state.get("v315_access_token", "")


def sign_in(email, password):
    data = _request("/auth/v1/token", method="POST", query={"grant_type": "password"}, body={"email": email.strip(), "password": password})
    user, token = (data or {}).get("user"), (data or {}).get("access_token")
    if not user or not token: raise ValueError("Oturum açılamadı.")
    st.session_state["v315_user"] = user; st.session_state["v315_access_token"] = token
    st.session_state["v315_refresh_token"] = (data or {}).get("refresh_token", "")
    return user


def sign_up(email, password):
    data = _request("/auth/v1/signup", method="POST", body={"email": email.strip(), "password": password})
    user, token = (data or {}).get("user"), (data or {}).get("access_token")
    if user and token:
        st.session_state["v315_user"] = user; st.session_state["v315_access_token"] = token
        st.session_state["v315_refresh_token"] = (data or {}).get("refresh_token", "")
    return user, bool(token)


def sign_out():
    token = access_token()
    if token:
        try: _request("/auth/v1/logout", method="POST", token=token, body={})
        except Exception: pass
    for k in ("v315_user", "v315_access_token", "v315_refresh_token"): st.session_state.pop(k, None)


def _json_safe(v):
    if isinstance(v, (pd.Timestamp, datetime)): return v.isoformat()
    try:
        if pd.isna(v): return None
    except Exception: pass
    if hasattr(v, "item"):
        try: return v.item()
        except Exception: pass
    return v


def coupon_payload(coupon):
    return [{str(k): _json_safe(v) for k, v in r.to_dict().items()} for _, r in coupon.iterrows()]


def _coupon_fingerprint_from_legs(legs):
    """Canonical coupon identity: kickoff date/time + teams + pick.
    Normalizes old/new saved payload formatting so the same coupon cannot be
    inserted again merely because display metadata or date formatting changed.
    """
    keys = []
    for leg in legs or []:
        if not isinstance(leg, dict):
            continue
        match = _norm(leg.get("Maç") or leg.get("Mac") or leg.get("match") or "")
        pick = _norm(leg.get("Pazar") or leg.get("Seçim") or leg.get("Secim") or "")
        raw_date = leg.get("Tarih") or leg.get("datetime") or leg.get("date") or ""
        dt = pd.to_datetime(raw_date, errors="coerce", dayfirst=True)
        date_key = dt.strftime("%Y-%m-%dT%H:%M") if pd.notna(dt) else _norm(raw_date)
        if match and pick:
            keys.append(f"{date_key}|{match}|{pick}")
    raw = "||".join(sorted(set(keys)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw else ""


def _stored_fingerprint(row):
    legs = row.get("legs") if isinstance(row, dict) else None
    if isinstance(legs, list) and legs and isinstance(legs[0], dict):
        stored = str(legs[0].get("V3.42 Kupon Parmak İzi") or "").strip()
        if stored:
            return stored
    return ""


def _existing_coupon_by_fingerprint(fingerprint, legs=None):
    if not fingerprint:
        return None
    target_fallback = _coupon_fingerprint_from_legs(legs or [])
    for row in list_coupons():
        # New canonical comparison is authoritative. Stored V3.42 fingerprint is
        # retained as a backwards-compatible secondary check.
        existing_legs = row.get("legs") or []
        canonical = _coupon_fingerprint_from_legs(existing_legs)
        if canonical and canonical == target_fallback:
            return row
        if _stored_fingerprint(row) == fingerprint:
            return row
    return None


def delete_coupon(coupon_id):
    """Delete exactly one coupon owned by the signed-in user (RLS + user_id guard)."""
    user, token = current_user(), access_token()
    if not user or not token:
        raise ValueError("Kupon silmek için giriş yapmalısın.")
    cid = str(coupon_id or "").strip()
    if not cid:
        raise ValueError("Silinecek kupon kimliği bulunamadı.")
    _request("/rest/v1/saved_coupons", method="DELETE", token=token,
             query={"id": f"eq.{cid}", "user_id": f"eq.{user['id']}"},
             prefer="return=minimal")
    return True


def save_coupon(coupon, mode, title="", stake=None, total_odds=None):
    user, token = current_user(), access_token()
    if not user or not token: raise ValueError("Kupon kaydetmek için önce Hesabım bölümünden giriş yap.")
    if coupon is None or coupon.empty: raise ValueError("Kaydedilecek kupon boş.")
    legs = coupon_payload(coupon)

    # V3.42: the same logical coupon may not be saved twice for the same user.
    # Identity uses kickoff + match + market group + pick, not title/stake/odds.
    fingerprint = _coupon_fingerprint_from_legs(legs)
    existing = _existing_coupon_by_fingerprint(fingerprint, legs)
    if existing:
        return {"_v342_duplicate": True, "id": existing.get("id"), "title": existing.get("title"),
                "status": existing.get("status"), "created_at": existing.get("created_at")}

    # Financial snapshot remains frozen at save time.
    if legs:
        try:
            stake_value = float(stake) if stake is not None else None
        except (TypeError, ValueError):
            stake_value = None
        try:
            total_value = float(total_odds) if total_odds is not None else None
        except (TypeError, ValueError):
            total_value = None
        meta = {
            "V3.19 Kupon Tutarı": stake_value,
            "V3.19 Toplam Oran": total_value,
            "V3.19 Olası Brüt Dönüş": (stake_value * total_value) if stake_value is not None and total_value is not None else None,
            "V3.19 Oran Kilidi": datetime.now().astimezone().isoformat(),
            "V3.20 Finansal Snapshot": True,
            "V3.42 Kupon Parmak İzi": fingerprint,
        }
        legs[0].update(meta)
    body = {"user_id": user["id"], "title": (title or f"{mode} • {datetime.now().strftime('%d.%m.%Y')}")[:120],
            "mode": str(mode)[:50], "legs": legs, "status": "ACIK"}
    out = _request("/rest/v1/saved_coupons", method="POST", token=token, body=body, prefer="return=representation")
    saved = out[0] if isinstance(out, list) and out else body
    saved["_v342_duplicate"] = False
    # Read-after-write verification: confirms it is visible through the user's RLS-scoped list.
    saved_id = saved.get("id")
    saved["_v342_verified"] = bool(saved_id and any(str(r.get("id")) == str(saved_id) for r in list_coupons()))
    return saved


def list_coupons():
    user, token = current_user(), access_token()
    if not user or not token: return []
    data = _request("/rest/v1/saved_coupons", token=token, query={"select":"id,title,mode,status,created_at,updated_at,legs", "user_id":f"eq.{user['id']}", "order":"created_at.desc", "limit":50})
    return data if isinstance(data, list) else []


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii").casefold()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s).split())


def _split_match(name):
    text = str(name or "")
    for sep in (" - ", " – ", " — ", " vs ", " VS "):
        if sep in text:
            a,b = text.split(sep,1); return a.strip(), b.strip()
    return "", ""


def _leg_pick(leg): return str(leg.get("Pazar") or leg.get("Seçim") or "").strip()


def _grade_pick(pick, hg, ag):
    p = pick.casefold().replace("  ", " ").strip(); total = hg + ag
    if p == "1": return hg > ag
    if p == "x": return hg == ag
    if p == "2": return ag > hg
    if p == "1x": return hg >= ag
    if p == "x2": return ag >= hg
    if p == "12": return hg != ag
    if p in ("kg var", "btts var"): return hg > 0 and ag > 0
    if p in ("kg yok", "btts yok"): return not (hg > 0 and ag > 0)
    if "1.5" in p and "üst" in p.casefold(): return total >= 2
    if "1.5" in p and "alt" in p.casefold(): return total <= 1
    if "2.5" in p and "üst" in p.casefold(): return total >= 3
    if "2.5" in p and "alt" in p.casefold(): return total <= 2
    return None


def _find_finished_fixture(leg, matches):
    if matches is None or matches.empty: return None
    home, away = _split_match(leg.get("Maç"))
    if not home or not away: return None
    d = matches[matches["finished"] == True].copy()  # noqa: E712
    d = d[(d["home"].map(_norm) == _norm(home)) & (d["away"].map(_norm) == _norm(away))]
    if d.empty: return None
    target = pd.to_datetime(leg.get("Tarih"), errors="coerce", utc=True)
    if pd.notna(target):
        # V3.41 guard: same team pairing can recur. Require the saved kickoff and
        # finished fixture to belong to the same local calendar date; then choose
        # the closest kickoff. This prevents an old-season result from settling a coupon.
        times = pd.to_datetime(d["datetime"], errors="coerce", utc=True)
        valid = times.notna()
        d = d.loc[valid].copy(); times = times.loc[valid]
        if d.empty: return None
        same_day = times.dt.date == target.date()
        d = d.loc[same_day].copy(); times = times.loc[same_day]
        if d.empty: return None
        delta = (times - target).abs()
        d = d.assign(_delta=delta).sort_values("_delta")
        if d.iloc[0]["_delta"] > pd.Timedelta(hours=12): return None
    return d.iloc[0]


def _settle_coupon(row, matches):
    """V3.41 guarded/idempotent coupon settlement.

    Rules:
    - already graded legs are immutable;
    - only an exact finished fixture may grade a leg;
    - unsupported markets remain open instead of being guessed;
    - coupon closes only after EVERY leg has a supported final verdict;
    - frozen stake/combined odds are read-only; only realized fields are added.
    """
    legs = row.get("legs") if isinstance(row.get("legs"), list) else []
    if not legs: return None

    changed = False
    new_legs = []
    verdicts = []

    for original in legs:
        leg = dict(original) if isinstance(original, dict) else {}
        old = str(leg.get("V3.16 Durum") or "").strip()
        if old in ("BİLDİ", "BİLEMEDİ"):
            verdicts.append(old)
            new_legs.append(leg)
            continue

        fx = _find_finished_fixture(leg, matches)
        if fx is None:
            verdicts.append("BEKLİYOR")
            new_legs.append(leg)
            continue

        try:
            hg, ag = int(fx["home_goals"]), int(fx["away_goals"])
        except (TypeError, ValueError):
            verdicts.append("BEKLİYOR")
            new_legs.append(leg)
            continue
        if hg < 0 or ag < 0:
            verdicts.append("BEKLİYOR")
            new_legs.append(leg)
            continue

        verdict = _grade_pick(_leg_pick(leg), hg, ag)
        if verdict is None:
            verdicts.append("PAZAR DESTEKLENMİYOR")
            new_legs.append(leg)
            continue

        result = "BİLDİ" if verdict else "BİLEMEDİ"
        leg["V3.16 Skor"] = f"{hg}-{ag}"
        leg["V3.16 Durum"] = result
        leg["V3.16 Sonuçlandı"] = datetime.now().astimezone().isoformat()
        verdicts.append(result)
        new_legs.append(leg)
        changed = True

    all_final = bool(verdicts) and all(v in ("BİLDİ", "BİLEMEDİ") for v in verdicts)
    if all_final:
        new_status = "KAYBETTI" if "BİLEMEDİ" in verdicts else "KAZANDI"
    else:
        new_status = "ACIK"
    if new_status != row.get("status"):
        changed = True

    # Financial result is created only when every leg is final. Save-time stake and
    # combined odds are never recalculated or overwritten.
    if all_final and new_legs and isinstance(new_legs[0], dict):
        meta = new_legs[0]
        if meta.get("V3.20 Finansal Sonuçlandı") is None:
            try:
                stake = float(meta.get("V3.19 Kupon Tutarı")) if meta.get("V3.19 Kupon Tutarı") is not None else None
                total_odds = float(meta.get("V3.19 Toplam Oran")) if meta.get("V3.19 Toplam Oran") is not None else None
            except (TypeError, ValueError):
                stake, total_odds = None, None
            if stake is not None and stake >= 0:
                gross = stake * total_odds if new_status == "KAZANDI" and total_odds is not None else (0.0 if new_status == "KAYBETTI" else None)
                net = (gross - stake) if gross is not None else None
                meta["V3.20 Gerçekleşen Brüt Dönüş"] = gross
                meta["V3.20 Net TL"] = net
                meta["V3.20 Finansal Sonuçlandı"] = datetime.now().astimezone().isoformat()
                changed = True

    return (new_legs, new_status) if changed else None


def _settlement_audit(row):
    """Read-only V3.43 settlement audit reconstructed from the frozen coupon snapshot."""
    legs = row.get("legs") if isinstance(row.get("legs"), list) else []
    states = [_leg_status(x) for x in legs if isinstance(x, dict)]
    won = sum(x == "BİLDİ" for x in states)
    lost = sum(x == "BİLEMEDİ" for x in states)
    waiting = sum(x not in ("BİLDİ", "BİLEMEDİ") for x in states)
    meta = legs[0] if legs and isinstance(legs[0], dict) else {}
    return {
        "legs": len(states), "won": won, "lost": lost, "waiting": waiting,
        "status": str(row.get("status") or "ACIK"),
        "settled_at": meta.get("V3.20 Finansal Sonuçlandı"),
        "gross": meta.get("V3.20 Gerçekleşen Brüt Dönüş"),
        "net": meta.get("V3.20 Net TL"),
    }


def settle_saved_coupons(matches):
    user, token = current_user(), access_token()
    if not user or not token: return {"checked":0,"updated":0}
    rows = list_coupons(); updated = 0
    for row in rows:
        if row.get("status") in ("KAZANDI", "KAYBETTI", "IPTAL"): continue
        settled = _settle_coupon(row, matches)
        if not settled: continue
        legs, status = settled
        _request("/rest/v1/saved_coupons", method="PATCH", token=token,
                 query={"id":f"eq.{row['id']}", "user_id":f"eq.{user['id']}"},
                 body={"legs":legs, "status":status, "updated_at":datetime.now().astimezone().isoformat()},
                 prefer="return=minimal")
        updated += 1
    return {"checked":len(rows),"updated":updated}


def _leg_status(leg):
    return str(leg.get("V3.16 Durum") or "BEKLİYOR")


def render_account(matches=None):
    st.subheader("👤 Hesabım • V3.47")
    st.caption("Kullanıcıya özel kupon geçmişi, otomatik sonuç kontrolü ve performans özeti. V3.14 karar motoruna ve kilitli maç önü oranlarına dokunmaz.")
    user = current_user()
    if not user:
        tab1, tab2 = st.tabs(["🔐 Giriş yap", "✨ Hesap oluştur"])
        with tab1:
            with st.form("v318_login"):
                email=st.text_input("E-posta"); password=st.text_input("Şifre", type="password"); go=st.form_submit_button("Giriş yap", use_container_width=True)
            if go:
                try: sign_in(email,password); st.success("Giriş başarılı."); st.rerun()
                except Exception as exc: st.error(str(exc))
        with tab2:
            with st.form("v318_signup"):
                email=st.text_input("E-posta",key="signup_email"); password=st.text_input("Şifre (en az 6 karakter)",type="password",key="signup_password"); password2=st.text_input("Şifre tekrar",type="password"); go=st.form_submit_button("Hesap oluştur",use_container_width=True)
            if go:
                if len(password)<6: st.error("Şifre en az 6 karakter olmalı.")
                elif password!=password2: st.error("Şifreler aynı değil.")
                else:
                    try:
                        _,active=sign_up(email,password)
                        if active: st.success("Hesap oluşturuldu ve giriş yapıldı."); st.rerun()
                        else: st.success("Hesap oluşturuldu. E-posta doğrulaması açıksa gelen bağlantıyı onaylayıp giriş yap.")
                    except Exception as exc: st.error(str(exc))
        return

    c1,c2=st.columns([3,1]); c1.success(f"🟢 Oturum açık • {user.get('email','Kullanıcı')}")
    if c2.button("Çıkış yap",use_container_width=True): sign_out(); st.rerun()

    settlement_info = {"checked": 0, "updated": 0}
    settlement_error = None
    if matches is not None:
        try:
            settlement_info = settle_saved_coupons(matches)
            if settlement_info["updated"]:
                st.success(f"{settlement_info['updated']} kupon kesinleşmiş maç sonuçlarıyla güncellendi.")
        except Exception as exc:
            settlement_error = str(exc)[:160]
            st.warning("Kupon sonuçlandırma geçici olarak tamamlanamadı: " + settlement_error)

    rows=list_coupons()

    # V3.42: visible, non-invasive settlement audit panel. This does not create
    # picks, alter frozen odds, or change the V3.14 decision engine.
    st.markdown("### 🔄 Otomatik sonuç kontrolü")
    open_after = sum(r.get("status") == "ACIK" for r in rows)
    finished_after = sum(r.get("status") in ("KAZANDI", "KAYBETTI") for r in rows)
    s1, s2, s3 = st.columns(3)
    s1.metric("Kontrol edilen kupon", settlement_info.get("checked", 0))
    s2.metric("Bu kontrolde güncellenen", settlement_info.get("updated", 0))
    s3.metric("Kesinleşen toplam", finished_after)
    if settlement_error:
        st.error("Sonuç kontrolü tamamlanamadı; mevcut kayıtlar değiştirilmedi.")
    elif matches is None:
        st.info("Fikstür/skor verisi gelmediği için sonuç kontrolü yapılmadı.")
    elif open_after:
        st.info(f"⏳ {open_after} açık kupon var. Yalnızca kesinleşmiş maç skorları geldikçe ayaklar otomatik işaretlenir.")
    else:
        st.success("Açık kupon bulunmuyor.")
    if st.button("🔄 Sonuçları şimdi yeniden kontrol et", use_container_width=True, key="v341_recheck"):
        st.rerun()
    st.caption("Yalnızca kesinleşmiş skorlar okunur; kayıtlı seçim, kupon tutarı ve kilitli maç önü oranı değiştirilmez.")

    st.markdown("### 📊 Kupon performansım")
    total=len(rows); open_n=sum(r.get("status")=="ACIK" for r in rows); won=sum(r.get("status")=="KAZANDI" for r in rows); lost=sum(r.get("status")=="KAYBETTI" for r in rows)
    a,b=st.columns(2)
    a.metric("Toplam kupon", total); b.metric("Açık kupon", open_n)
    c,d=st.columns(2)
    c.metric("Kazandı", won); d.metric("Kaybetti", lost)

    # V3.21: portfolio-level finance is rebuilt only from immutable save-time snapshots.
    total_staked = 0.0
    settled_staked = 0.0
    realized_gross_total = 0.0
    realized_net_total = 0.0
    financial_coupon_count = 0
    settled_financial_count = 0
    for row in rows:
        legs_fin = row.get("legs") if isinstance(row.get("legs"), list) else []
        if not legs_fin or not isinstance(legs_fin[0], dict):
            continue
        meta_fin = legs_fin[0]
        try:
            stake_fin = float(meta_fin.get("V3.19 Kupon Tutarı")) if meta_fin.get("V3.19 Kupon Tutarı") is not None else None
        except (TypeError, ValueError):
            stake_fin = None
        if stake_fin is None:
            continue
        financial_coupon_count += 1
        total_staked += stake_fin
        if row.get("status") in ("KAZANDI", "KAYBETTI"):
            try:
                net_fin = float(meta_fin.get("V3.20 Net TL")) if meta_fin.get("V3.20 Net TL") is not None else None
                gross_fin = float(meta_fin.get("V3.20 Gerçekleşen Brüt Dönüş")) if meta_fin.get("V3.20 Gerçekleşen Brüt Dönüş") is not None else None
            except (TypeError, ValueError):
                net_fin, gross_fin = None, None
            if net_fin is not None:
                settled_financial_count += 1
                settled_staked += stake_fin
                realized_net_total += net_fin
                realized_gross_total += gross_fin or 0.0

    st.markdown("### 💰 Finansal performans")
    f1,f2=st.columns(2)
    f1.metric("Kayıtlı toplam tutar", f"{total_staked:,.2f} TL" if financial_coupon_count else "—")
    f2.metric("Sonuçlanan yatırım", f"{settled_staked:,.2f} TL" if settled_financial_count else "—")
    f3,f4=st.columns(2)
    f3.metric("Gerçekleşen dönüş", f"{realized_gross_total:,.2f} TL" if settled_financial_count else "—")
    f4.metric("Net kâr / zarar", f"{realized_net_total:+,.2f} TL" if settled_financial_count else "—")
    roi = (realized_net_total / settled_staked * 100.0) if settled_staked > 0 else None
    st.metric("Sonuçlanan kupon ROI", f"%{roi:+.2f}" if roi is not None else "—")
    st.caption("ROI yalnızca sonucu kesinleşmiş ve kayıt anında tutarı/oranı dondurulmuş kuponlardan hesaplanır. Açık kuponlar ROI'ye dahil edilmez.")

    # V3.35: Monday-Sunday weekly coupon performance from persistent saved coupons.
    st.markdown("### 📅 Bu haftanın kupon performansı")
    local_now = pd.Timestamp.now(tz="Europe/Istanbul")
    week_start = local_now.normalize() - pd.Timedelta(days=local_now.weekday())
    week_end = week_start + pd.Timedelta(days=7)
    weekly_rows = []
    for row in rows:
        created = pd.to_datetime(row.get("created_at"), errors="coerce", utc=True)
        if pd.isna(created):
            continue
        created = created.tz_convert("Europe/Istanbul")
        if week_start <= created < week_end:
            weekly_rows.append(row)
    weekly_total = len(weekly_rows)
    weekly_open = sum(r.get("status") == "ACIK" for r in weekly_rows)
    weekly_won = sum(r.get("status") == "KAZANDI" for r in weekly_rows)
    weekly_lost = sum(r.get("status") == "KAYBETTI" for r in weekly_rows)
    weekly_settled = weekly_won + weekly_lost
    weekly_hit = (100.0 * weekly_won / weekly_settled) if weekly_settled else None
    w1,w2,w3 = st.columns(3)
    w1.metric("Kaydedilen", weekly_total)
    w2.metric("Açık", weekly_open)
    w3.metric("Sonuçlanan", weekly_settled)
    w4,w5,w6 = st.columns(3)
    w4.metric("Kazandı", weekly_won)
    w5.metric("Kaybetti", weekly_lost)
    w6.metric("Kupon isabeti", f"%{weekly_hit:.1f}" if weekly_hit is not None else "—")

    weekly_stake = 0.0
    weekly_net = 0.0
    weekly_fin_n = 0
    for row in weekly_rows:
        if row.get("status") not in ("KAZANDI", "KAYBETTI"):
            continue
        legs_w = row.get("legs") if isinstance(row.get("legs"), list) else []
        if not legs_w or not isinstance(legs_w[0], dict):
            continue
        meta_w = legs_w[0]
        try:
            stake_w = float(meta_w.get("V3.19 Kupon Tutarı")) if meta_w.get("V3.19 Kupon Tutarı") is not None else None
            net_w = float(meta_w.get("V3.20 Net TL")) if meta_w.get("V3.20 Net TL") is not None else None
        except (TypeError, ValueError):
            stake_w, net_w = None, None
        if stake_w is not None and net_w is not None:
            weekly_stake += stake_w
            weekly_net += net_w
            weekly_fin_n += 1
    weekly_roi = (weekly_net / weekly_stake * 100.0) if weekly_stake > 0 else None
    q1,q2 = st.columns(2)
    q1.metric("Haftalık net sonuç", f"{weekly_net:+,.2f} TL" if weekly_fin_n else "—")
    q2.metric("Haftalık ROI", f"%{weekly_roi:+.2f}" if weekly_roi is not None else "—")
    st.caption(f"Hafta: {week_start.strftime('%d.%m.%Y')} – {(week_end - pd.Timedelta(days=1)).strftime('%d.%m.%Y')}. Bekleyen kuponlar isabet ve ROI hesabına katılmaz.")

    st.markdown("### 🎟️ Kuponlarım • ayrıntılı sonuç defteri")
    if not rows:
        st.info("Henüz kayıtlı kupon yok. Kupon Merkezi'nden bir kuponu hesabına kaydedebilirsin."); return

    filt=st.radio("Durum filtresi", ["Tümü","AÇIK","KAZANDI","KAYBETTİ"], horizontal=True, key="v318_filter")
    status_map={"AÇIK":"ACIK","KAZANDI":"KAZANDI","KAYBETTİ":"KAYBETTI"}
    visible=rows if filt=="Tümü" else [r for r in rows if r.get("status")==status_map[filt]]
    if not visible:
        st.info("Bu filtrede kupon bulunmuyor."); return

    for i,r in enumerate(visible[:50]):
        legs=r.get("legs") if isinstance(r.get("legs"),list) else []
        done=sum(1 for x in legs if isinstance(x,dict) and _leg_status(x) in ("BİLDİ","BİLEMEDİ"))
        status=r.get("status","ACIK")
        icon="🏆" if status=="KAZANDI" else ("❌" if status=="KAYBETTI" else "⏳")
        title=r.get("title") or "Kupon"
        created=str(r.get("created_at","")).replace("T"," ")[:16]
        st.markdown(f"#### {icon} {title}")
        clean_mode = str(r.get("mode") or "—").replace("🛡️ ","").replace("⚖️ ","").replace("🔥 ","")
        x1,x2=st.columns(2)
        x1.metric("Durum", "AÇIK" if status == "ACIK" else status); x2.metric("Kupon tipi", clean_mode)
        x3,x4=st.columns(2)
        x3.metric("Ayak", len(legs)); x4.metric("Sonuçlanan", f"{done}/{len(legs)}")
        st.caption(f"Kayıt: {created}")
        # V3.37: coupon detail card. All figures come from the frozen save-time snapshot;
        # settlement continues to use the existing V3.16 logic without changing the decision engine.
        if status == "KAZANDI":
            st.success("🏆 KUPON KAZANDI")
        elif status == "KAYBETTI":
            st.error("❌ KUPON KAYBETTİ")
        else:
            st.info("⏳ KUPON AÇIK • maç sonuçları bekleniyor")
        # V3.20: show frozen save-time snapshot and, after settlement, realized result.
        if legs and isinstance(legs[0], dict):
            meta_leg = legs[0]
            saved_stake = meta_leg.get("V3.19 Kupon Tutarı")
            saved_total = meta_leg.get("V3.19 Toplam Oran")
            saved_return = meta_leg.get("V3.19 Olası Brüt Dönüş")
            if saved_total is not None:
                m1,m2=st.columns(2)
                m1.metric("Toplam oran", f"{float(saved_total):.2f}")
                m2.metric("Kupon tutarı", f"{float(saved_stake):,.2f} TL" if saved_stake is not None else "—")
                st.metric("Olası brüt dönüş", f"{float(saved_return):,.2f} TL" if saved_return is not None else "—")
                realized_net = meta_leg.get("V3.20 Net TL")
                realized_gross = meta_leg.get("V3.20 Gerçekleşen Brüt Dönüş")
                if realized_net is not None:
                    r1,r2=st.columns(2)
                    r1.metric("Gerçekleşen brüt dönüş", f"{float(realized_gross):,.2f} TL" if realized_gross is not None else "—")
                    r2.metric("Net sonuç", f"{float(realized_net):+,.2f} TL")

        audit = _settlement_audit(r)
        with st.expander("🧾 Sonuçlandırma denetimi", expanded=(status in ("KAZANDI", "KAYBETTI"))):
            au1, au2, au3, au4 = st.columns(4)
            au1.metric("Ayak", audit["legs"])
            au2.metric("✅ Bildi", audit["won"])
            au3.metric("❌ Bilemedi", audit["lost"])
            au4.metric("⏳ Bekliyor", audit["waiting"])
            if audit["status"] == "KAZANDI":
                st.success("Tüm ayaklar kesinleşti ve doğru: kupon KAZANDI.")
            elif audit["status"] == "KAYBETTI":
                st.error("Tüm ayaklar kesinleşti ve en az bir ayak yanlış: kupon KAYBETTİ.")
            else:
                st.info("Kupon henüz açık. Kesinleşmemiş ayaklar sonuç hesabına katılmaz.")
            if audit.get("settled_at"):
                st.caption("Finansal sonuçlandırma zamanı: " + str(audit["settled_at"]).replace("T", " ")[:19])
            st.caption("Audit yalnızca dondurulmuş kupon kaydını okur; seçim, oran veya karar üretmez.")
        with st.expander("Kupon ayaklarını göster", expanded=(len(visible)==1)):
            if not legs:
                st.info("Bu kuponda ayak verisi yok.")
            else:
                leg_states=[_leg_status(x) for x in legs if isinstance(x,dict)]
                won=sum(x=="BİLDİ" for x in leg_states)
                lost=sum(x=="BİLEMEDİ" for x in leg_states)
                waiting=sum(x not in ("BİLDİ","BİLEMEDİ") for x in leg_states)
                q1,q2,q3=st.columns(3)
                q1.metric("✅ Bildi", won); q2.metric("❌ Bilemedi", lost); q3.metric("⏳ Bekliyor", waiting)
                display=[]
                for leg in legs:
                    if not isinstance(leg,dict): continue
                    ls=_leg_status(leg)
                    li="✅" if ls=="BİLDİ" else ("❌" if ls=="BİLEMEDİ" else "⏳")
                    display.append({
                        "Maç":leg.get("Maç","—"),
                        "Seçim":leg.get("Pazar") or leg.get("Seçim") or "—",
                        "Kilitli Oran":leg.get("Maç Önü Oran") if leg.get("Maç Önü Oran") is not None else "—",
                        "Skor":leg.get("V3.16 Skor") or "—",
                        "Sonuç":f"{li} {ls}",
                        "Tarih":str(leg.get("Tarih",""))[:16].replace("T"," "),
                        "Pazar Grubu":leg.get("Pazar Grubu","—"),
                        "Oran Kaynağı":leg.get("Oran Kaynağı") or "—",
                        "Model %":leg.get("Model %","—"),
                        "Backtest %":leg.get("Backtest %","—")
                    })
                # V3.38: mobile-first leg cards. Avoid wide horizontal tables on phones/tablets.
                for idx, row in enumerate(display, start=1):
                    with st.container(border=True):
                        st.markdown(f"**{idx}. {row['Maç']}**")
                        a,b,c=st.columns(3)
                        a.metric("Seçim", str(row["Seçim"]))
                        b.metric("Oran", str(row["Kilitli Oran"]))
                        c.metric("Durum", str(row["Sonuç"]))
                        d,e=st.columns(2)
                        d.caption(f"Skor: {row['Skor']}")
                        e.caption(f"Tarih: {row['Tarih'] or '—'}")
                        source=row.get("Oran Kaynağı","—")
                        model=row.get("Model %","—")
                        backtest=row.get("Backtest %","—")
                        st.caption(f"Kaynak: {source} • Model: %{model} • Backtest: %{backtest}")
                st.caption("Her ayak yalnızca kayıtlı maç önü oranı ve kesinleşmiş skor verisiyle gösterilir; bekleyen maç için sonuç üretilmez.")

        # V3.42.1 safe per-coupon deletion: first click arms confirmation,
        # second click deletes only this user's exact coupon id.
        coupon_id = str(r.get("id") or "")
        confirm_key = f"v3421_delete_confirm_{coupon_id}"
        if coupon_id:
            if not st.session_state.get(confirm_key, False):
                if st.button("🗑️ Kuponu sil", key=f"v3421_delete_{coupon_id}", use_container_width=True):
                    st.session_state[confirm_key] = True
                    st.rerun()
            else:
                st.warning(f"‘{title}’ kuponu kalıcı olarak silinsin mi?")
                dc1, dc2 = st.columns(2)
                if dc1.button("✅ Evet, sil", key=f"v3421_yes_{coupon_id}", use_container_width=True):
                    try:
                        delete_coupon(coupon_id)
                        st.session_state.pop(confirm_key, None)
                        st.success("Kupon silindi.")
                        st.rerun()
                    except Exception as exc:
                        st.error("Kupon silinemedi: " + str(exc)[:160])
                if dc2.button("↩️ Vazgeç", key=f"v3421_no_{coupon_id}", use_container_width=True):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
        st.divider()
