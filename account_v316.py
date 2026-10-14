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


def save_coupon(coupon, mode, title=""):
    user, token = current_user(), access_token()
    if not user or not token: raise ValueError("Kupon kaydetmek için önce Hesabım bölümünden giriş yap.")
    if coupon is None or coupon.empty: raise ValueError("Kaydedilecek kupon boş.")
    body = {"user_id": user["id"], "title": (title or f"{mode} • {datetime.now().strftime('%d.%m.%Y')}")[:120],
            "mode": str(mode)[:50], "legs": coupon_payload(coupon), "status": "ACIK"}
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


def render_account(matches=None):
    st.subheader("👤 Hesabım • V3.16")
    st.caption("Supabase Auth + kullanıcıya özel kupon geçmişi. Biten maçlar görüldüğünde kayıtlı kupon ayakları otomatik sonuçlandırılır.")
    user = current_user()
    if not user:
        tab1, tab2 = st.tabs(["🔐 Giriş yap", "✨ Hesap oluştur"])
        with tab1:
            with st.form("v316_login"):
                email=st.text_input("E-posta"); password=st.text_input("Şifre", type="password"); go=st.form_submit_button("Giriş yap", use_container_width=True)
            if go:
                try: sign_in(email,password); st.success("Giriş başarılı."); st.rerun()
                except Exception as exc: st.error(str(exc))
        with tab2:
            with st.form("v316_signup"):
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
            if info["updated"]: st.success(f"V3.16: {info['updated']} kupon kaydı yeni maç sonuçlarıyla güncellendi.")
        except Exception as exc: st.warning("Kupon sonuçlandırma geçici olarak tamamlanamadı: "+str(exc)[:160])

    st.markdown("### 🎟️ Kayıtlı kuponlarım")
    rows=list_coupons()
    if not rows:
        st.info("Henüz kayıtlı kupon yok. Kupon Merkezi'nden bir kuponu hesabına kaydedebilirsin."); return
    summary=[]
    for r in rows:
        legs=r.get("legs") if isinstance(r.get("legs"),list) else []
        done=sum(1 for x in legs if isinstance(x,dict) and x.get("V3.16 Durum") in ("BİLDİ","BİLEMEDİ"))
        summary.append({"Başlık":r.get("title"),"Kupon tipi":r.get("mode"),"Ayak":len(legs),"Sonuçlanan":f"{done}/{len(legs)}","Durum":r.get("status"),"Kayıt":str(r.get("created_at",""))[:16].replace("T"," ")})
    st.dataframe(pd.DataFrame(summary),hide_index=True,use_container_width=True)
    with st.expander("Kupon ayrıntılarını göster"):
        for r in rows[:20]:
            status=r.get("status","—"); icon="🏆" if status=="KAZANDI" else ("❌" if status=="KAYBETTI" else "⏳")
            st.markdown(f"**{r.get('title','Kupon')}** • {icon} {status}")
            legs=r.get("legs") if isinstance(r.get("legs"),list) else []
            if legs:
                d=pd.DataFrame(legs)
                cols=[c for c in ["Tarih","Maç","Pazar Grubu","Pazar","Model %","Backtest %","V3.16 Skor","V3.16 Durum"] if c in d.columns]
                st.dataframe(d[cols] if cols else d,hide_index=True,use_container_width=True)
