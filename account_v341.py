"""V3.41 account + immutable coupon snapshot + guarded automatic settlement.
Uses Supabase Auth/RLS. Settlement only consumes finished fixtures supplied by app.py.
V3.41 does not alter the V3.14 decision engine or any locked pre-match odds.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
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


def save_coupon(coupon, mode, title="", stake=None, total_odds=None):
    user, token = current_user(), access_token()
    if not user or not token: raise ValueError("Kupon kaydetmek için önce Hesabım bölümünden giriş yap.")
    if coupon is None or coupon.empty: raise ValueError("Kaydedilecek kupon boş.")
    legs = coupon_payload(coupon)
    # V3.20: financial snapshot is frozen inside the coupon payload at save time.
    # This is backwards-compatible with the existing saved_coupons schema/RLS.
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
        }
        legs[0].update(meta)
    body = {"user_id": user["id"], "title": (title or f"{mode} • {datetime.now().strftime('%d.%m.%Y')}")[:120],
            "mode": str(mode)[:50], "legs": legs, "status": "ACIK"}
    out = _request("/rest/v1/saved_coupons", method="POST", token=token, body=body, prefer="return=representation")
    return out[0] if isinstance(out, list) and out else body


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
    st.subheader("👤 Hesabım • V3.41")
    st.caption("Supabase Auth + kullanıcıya özel kupon geçmişi. V3.41 güvenli sonuçlandırma katmanı; V3.14 karar motoruna ve kilitli oranlara dokunmaz.")
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
                st.success(f"V3.41: {settlement_info['updated']} kupon kaydı yeni maç sonuçlarıyla güncellendi.")
        except Exception as exc:
            settlement_error = str(exc)[:160]
            st.warning("Kupon sonuçlandırma geçici olarak tamamlanamadı: " + settlement_error)

    rows=list_coupons()

    # V3.41: visible, non-invasive settlement audit panel. This does not create
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
    st.caption("V3.41 kontrolü yalnızca kesinleşmiş fikstür/skor verisini okur. Kayıtlı maç önü oranı, kupon tutarı ve seçimler değiştirilmez.")

    st.markdown("### 📊 Kupon performansım")
    total=len(rows); open_n=sum(r.get("status")=="ACIK" for r in rows); won=sum(r.get("status")=="KAZANDI" for r in rows); lost=sum(r.get("status")=="KAYBETTI" for r in rows)
    a,b,c,d=st.columns(4)
    a.metric("Toplam", total); b.metric("Açık", open_n); c.metric("Kazandı", won); d.metric("Kaybetti", lost)

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
    f1,f2,f3,f4=st.columns(4)
    f1.metric("Kayıtlı toplam tutar", f"{total_staked:,.2f} TL" if financial_coupon_count else "—")
    f2.metric("Sonuçlanan yatırım", f"{settled_staked:,.2f} TL" if settled_financial_count else "—")
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
    w1,w2,w3,w4,w5 = st.columns(5)
    w1.metric("Kaydedilen", weekly_total)
    w2.metric("Açık", weekly_open)
    w3.metric("Kazandı", weekly_won)
    w4.metric("Kaybetti", weekly_lost)
    w5.metric("Kupon isabeti", f"%{weekly_hit:.1f}" if weekly_hit is not None else "—")

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
        x1,x2,x3,x4=st.columns(4)
        x1.metric("Durum", status); x2.metric("Ayak", len(legs)); x3.metric("Sonuçlanan", f"{done}/{len(legs)}"); x4.metric("Tip", str(r.get("mode") or "—").replace("🛡️ ","").replace("⚖️ ","").replace("🔥 ",""))
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
                m1,m2,m3=st.columns(3)
                m1.metric("Kayıtlı toplam oran", f"{float(saved_total):.2f}")
                m2.metric("Kupon tutarı", f"{float(saved_stake):,.2f} TL" if saved_stake is not None else "—")
                m3.metric("Olası brüt dönüş", f"{float(saved_return):,.2f} TL" if saved_return is not None else "—")
                realized_net = meta_leg.get("V3.20 Net TL")
                realized_gross = meta_leg.get("V3.20 Gerçekleşen Brüt Dönüş")
                if realized_net is not None:
                    r1,r2=st.columns(2)
                    r1.metric("Gerçekleşen brüt dönüş", f"{float(realized_gross):,.2f} TL" if realized_gross is not None else "—")
                    r2.metric("Net sonuç", f"{float(realized_net):+,.2f} TL")
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
                st.caption("V3.41: Her ayak yalnızca kayıtlı maç önü oranı ve kesinleşmiş fikstür/skor verisiyle gösterilir; bekleyen maç için sonuç üretilmez.")
        st.divider()
