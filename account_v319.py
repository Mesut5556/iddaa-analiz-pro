"""V3.16 account + persistent coupon storage + automatic coupon settlement.
Uses Supabase Auth/RLS. Coupon settlement only uses finished fixtures already supplied by app.py.
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
    # V3.19: coupon financial snapshot is stored inside the immutable coupon payload.
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
        # Same fixture names can recur across seasons; require kickoff within 36 hours.
        times = pd.to_datetime(d["datetime"], errors="coerce", utc=True)
        delta = (times - target).abs()
        d = d.assign(_delta=delta).sort_values("_delta")
        if d.iloc[0]["_delta"] > pd.Timedelta(hours=36): return None
    return d.iloc[0]


def _settle_coupon(row, matches):
    legs = row.get("legs") if isinstance(row.get("legs"), list) else []
    if not legs: return None
    changed = False; all_finished = True; any_lost = False; all_won = True
    new_legs = []
    for original in legs:
        leg = dict(original) if isinstance(original, dict) else {}
        if leg.get("V3.16 Durum") in ("BİLDİ", "BİLEMEDİ"):
            result = leg.get("V3.16 Durum")
        else:
            fx = _find_finished_fixture(leg, matches)
            if fx is None:
                result = "BEKLİYOR"
            else:
                hg, ag = int(fx["home_goals"]), int(fx["away_goals"])
                verdict = _grade_pick(_leg_pick(leg), hg, ag)
                if verdict is None:
                    result = "PAZAR DESTEKLENMİYOR"
                else:
                    result = "BİLDİ" if verdict else "BİLEMEDİ"
                    leg["V3.16 Skor"] = f"{hg}-{ag}"
                    leg["V3.16 Durum"] = result
                    leg["V3.16 Sonuçlandı"] = datetime.now().astimezone().isoformat()
                    changed = True
        if result == "BEKLİYOR" or result == "PAZAR DESTEKLENMİYOR": all_finished = False
        if result == "BİLEMEDİ": any_lost = True; all_won = False
        elif result != "BİLDİ": all_won = False
        new_legs.append(leg)
    new_status = "KAYBETTI" if any_lost else ("KAZANDI" if all_finished and all_won else "ACIK")
    if new_status != row.get("status"): changed = True
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
    st.subheader("👤 Hesabım • V3.19")
    st.caption("Supabase Auth + kullanıcıya özel kupon geçmişi. Karar motoru ve V3.16 sonuçlandırma mantığı değiştirilmedi.")
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

    if matches is not None:
        try:
            info=settle_saved_coupons(matches)
            if info["updated"]: st.success(f"V3.19: {info['updated']} kupon kaydı yeni maç sonuçlarıyla güncellendi.")
        except Exception as exc: st.warning("Kupon sonuçlandırma geçici olarak tamamlanamadı: "+str(exc)[:160])

    rows=list_coupons()
    st.markdown("### 📊 Kupon performansım")
    total=len(rows); open_n=sum(r.get("status")=="ACIK" for r in rows); won=sum(r.get("status")=="KAZANDI" for r in rows); lost=sum(r.get("status")=="KAYBETTI" for r in rows)
    a,b,c,d=st.columns(4)
    a.metric("Toplam", total); b.metric("Açık", open_n); c.metric("Kazandı", won); d.metric("Kaybetti", lost)

    st.markdown("### 🎟️ Kayıtlı kuponlarım")
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
        # V3.19: show the exact financial snapshot captured when the coupon was saved.
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
        with st.expander("Kupon ayaklarını göster", expanded=(len(visible)==1)):
            if not legs:
                st.info("Bu kuponda ayak verisi yok.")
            else:
                display=[]
                for leg in legs:
                    if not isinstance(leg,dict): continue
                    ls=_leg_status(leg)
                    li="✅" if ls=="BİLDİ" else ("❌" if ls=="BİLEMEDİ" else "⏳")
                    display.append({
                        "Durum":f"{li} {ls}", "Tarih":str(leg.get("Tarih",""))[:16].replace("T"," "),
                        "Maç":leg.get("Maç","—"), "Pazar Grubu":leg.get("Pazar Grubu","—"),
                        "Seçim":leg.get("Pazar") or leg.get("Seçim") or "—", "Skor":leg.get("V3.16 Skor") or "—",
                        "Maç Önü Oran": leg.get("Maç Önü Oran") if leg.get("Maç Önü Oran") is not None else "—",
                        "Oran Kaynağı": leg.get("Oran Kaynağı") or "—",
                        "Model %":leg.get("Model %","—"), "Backtest %":leg.get("Backtest %","—")
                    })
                st.dataframe(pd.DataFrame(display), hide_index=True, use_container_width=True)
        st.divider()
