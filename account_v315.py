"""V3.15 account + persistent coupon storage using Supabase Auth and RLS.
No passwords are stored by the Streamlit app; authentication is delegated to Supabase Auth.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd
import streamlit as st


def _cfg():
    try:
        url = str(st.secrets.get("SUPABASE_URL", "")).strip().rstrip("/")
        key = str(st.secrets.get("SUPABASE_ANON_KEY", "") or st.secrets.get("SUPABASE_KEY", "")).strip()
    except Exception:
        return "", ""
    return url, key


def _request(path, method="GET", body=None, token=None, query=None):
    url, key = _cfg()
    if not (url.startswith("https://") and key):
        raise ValueError("SUPABASE_URL ve SUPABASE_ANON_KEY (veya SUPABASE_KEY) gerekli.")
    endpoint = url + path
    if query:
        endpoint += "?" + urllib.parse.urlencode(query)
    headers = {"apikey": key, "Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(endpoint, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            msg = json.loads(raw).get("msg") or json.loads(raw).get("message") or json.loads(raw).get("error_description")
        except Exception:
            msg = None
        raise ValueError(msg or f"Supabase HTTP {exc.code}") from None
    except urllib.error.URLError:
        raise ValueError("Supabase sunucusuna erişilemedi.") from None


def current_user():
    return st.session_state.get("v315_user")


def access_token():
    return st.session_state.get("v315_access_token", "")


def sign_in(email, password):
    data = _request("/auth/v1/token", method="POST", query={"grant_type": "password"},
                    body={"email": email.strip(), "password": password})
    user = (data or {}).get("user")
    token = (data or {}).get("access_token")
    if not user or not token:
        raise ValueError("Oturum açılamadı.")
    st.session_state["v315_user"] = user
    st.session_state["v315_access_token"] = token
    st.session_state["v315_refresh_token"] = (data or {}).get("refresh_token", "")
    return user


def sign_up(email, password):
    data = _request("/auth/v1/signup", method="POST", body={"email": email.strip(), "password": password})
    user = (data or {}).get("user")
    token = (data or {}).get("access_token")
    if user and token:
        st.session_state["v315_user"] = user
        st.session_state["v315_access_token"] = token
        st.session_state["v315_refresh_token"] = (data or {}).get("refresh_token", "")
    return user, bool(token)


def sign_out():
    token = access_token()
    if token:
        try:
            _request("/auth/v1/logout", method="POST", token=token, body={})
        except Exception:
            pass
    for k in ("v315_user", "v315_access_token", "v315_refresh_token"):
        st.session_state.pop(k, None)


def _json_safe(v):
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if isinstance(v, datetime):
        return v.isoformat()
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        try: return v.item()
        except Exception: pass
    return v


def coupon_payload(coupon):
    rows = []
    for _, r in coupon.iterrows():
        rows.append({str(k): _json_safe(v) for k, v in r.to_dict().items()})
    return rows


def save_coupon(coupon, mode, title=""):
    user, token = current_user(), access_token()
    if not user or not token:
        raise ValueError("Kupon kaydetmek için önce Hesabım bölümünden giriş yap.")
    if coupon is None or coupon.empty:
        raise ValueError("Kaydedilecek kupon boş.")
    body = {
        "user_id": user["id"],
        "title": (title or f"{mode} • {datetime.now().strftime('%d.%m.%Y')}")[:120],
        "mode": str(mode)[:50],
        "legs": coupon_payload(coupon),
        "status": "ACIK",
    }
    url, key = _cfg()
    endpoint = url + "/rest/v1/saved_coupons"
    headers = {"apikey": key, "Authorization": "Bearer " + token, "Content-Type": "application/json",
               "Accept": "application/json", "Prefer": "return=representation"}
    req = urllib.request.Request(endpoint, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            out = json.loads(resp.read().decode("utf-8") or "[]")
        return out[0] if isinstance(out, list) and out else body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        if "saved_coupons" in raw and ("does not exist" in raw or "schema cache" in raw):
            raise ValueError("saved_coupons tablosu henüz kurulmamış. V3.15 SQL kurulumunu bir kez çalıştır.") from None
        raise ValueError("Kupon Supabase'e kaydedilemedi: " + raw[:140]) from None


def list_coupons():
    user, token = current_user(), access_token()
    if not user or not token:
        return []
    try:
        data = _request("/rest/v1/saved_coupons", token=token, query={
            "select": "id,title,mode,status,created_at,legs",
            "user_id": f"eq.{user['id']}", "order": "created_at.desc", "limit": 50
        })
        return data if isinstance(data, list) else []
    except Exception:
        return []


def render_account():
    st.subheader("👤 Hesabım • V3.15")
    st.caption("Giriş sistemi Supabase Auth kullanır. Parolan uygulama koduna veya kupon tablosuna kaydedilmez.")
    user = current_user()
    if not user:
        tab1, tab2 = st.tabs(["🔐 Giriş yap", "✨ Hesap oluştur"])
        with tab1:
            with st.form("v315_login"):
                email = st.text_input("E-posta")
                password = st.text_input("Şifre", type="password")
                go = st.form_submit_button("Giriş yap", use_container_width=True)
            if go:
                try:
                    sign_in(email, password); st.success("Giriş başarılı."); st.rerun()
                except Exception as exc: st.error(str(exc))
        with tab2:
            with st.form("v315_signup"):
                email = st.text_input("E-posta", key="signup_email")
                password = st.text_input("Şifre (en az 6 karakter)", type="password", key="signup_password")
                password2 = st.text_input("Şifre tekrar", type="password")
                go = st.form_submit_button("Hesap oluştur", use_container_width=True)
            if go:
                if len(password) < 6: st.error("Şifre en az 6 karakter olmalı.")
                elif password != password2: st.error("Şifreler aynı değil.")
                else:
                    try:
                        _, active = sign_up(email, password)
                        if active: st.success("Hesap oluşturuldu ve giriş yapıldı."); st.rerun()
                        else: st.success("Hesap oluşturuldu. E-posta doğrulaması açıksa gelen bağlantıyı onaylayıp giriş yap.")
                    except Exception as exc: st.error(str(exc))
        return

    email = user.get("email", "Kullanıcı")
    c1, c2 = st.columns([3,1])
    c1.success(f"🟢 Oturum açık • {email}")
    if c2.button("Çıkış yap", use_container_width=True):
        sign_out(); st.rerun()

    st.markdown("### 🎟️ Kayıtlı kuponlarım")
    rows = list_coupons()
    if not rows:
        st.info("Henüz kayıtlı kupon yok. Kupon Merkezi'nden bir kuponu hesabına kaydedebilirsin.")
        return
    summary = []
    for r in rows:
        created = str(r.get("created_at", ""))[:16].replace("T", " ")
        legs = r.get("legs") if isinstance(r.get("legs"), list) else []
        summary.append({"Başlık": r.get("title"), "Kupon tipi": r.get("mode"), "Ayak": len(legs),
                        "Durum": r.get("status"), "Kayıt": created})
    st.dataframe(pd.DataFrame(summary), hide_index=True, use_container_width=True)
    with st.expander("Kupon ayrıntılarını göster"):
        for r in rows[:20]:
            st.markdown(f"**{r.get('title','Kupon')}** • {r.get('status','—')}")
            legs = r.get("legs") if isinstance(r.get("legs"), list) else []
            if legs:
                d = pd.DataFrame(legs)
                cols = [c for c in ["Tarih","Maç","Pazar Grubu","Pazar","Model %","Backtest %","Destek"] if c in d.columns]
                st.dataframe(d[cols] if cols else d, hide_index=True, use_container_width=True)
