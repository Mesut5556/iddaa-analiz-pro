"""V3.31 Match ↔ Team Analysis bridge.
Read-only comparison panel. It does not alter decision, odds, coupon or settlement logic.
"""
import pandas as pd
import streamlit as st


def _history(completed, team, before, limit=10, venue=None):
    if completed is None or completed.empty:
        return pd.DataFrame()
    d = completed[completed["datetime"] < before].copy()
    if venue == "home":
        d = d[d["home"] == team]
    elif venue == "away":
        d = d[d["away"] == team]
    else:
        d = d[(d["home"] == team) | (d["away"] == team)]
    return d.sort_values("datetime", ascending=False).head(limit)


def _stats(df, team):
    if df is None or df.empty:
        return None
    w=d=l=gf=ga=o15=o25=btts=0
    for _, r in df.iterrows():
        is_home = r["home"] == team
        a = int(r["home_goals"] if is_home else r["away_goals"])
        b = int(r["away_goals"] if is_home else r["home_goals"])
        gf += a; ga += b
        w += a > b; d += a == b; l += a < b
        o15 += a+b >= 2; o25 += a+b >= 3; btts += a > 0 and b > 0
    n=len(df)
    return {
        "Maç":n, "G-B-M":f"{w}-{d}-{l}", "Puan":3*w+d,
        "Gol/maç":round(gf/n,2), "Yenen/maç":round(ga/n,2),
        "1.5 Üst %":round(100*o15/n,1), "2.5 Üst %":round(100*o25/n,1),
        "KG Var %":round(100*btts/n,1),
    }


def _form(df, team, n=5):
    out=[]
    for _,r in df.head(n).iterrows():
        is_home=r["home"] == team
        a=int(r["home_goals"] if is_home else r["away_goals"])
        b=int(r["away_goals"] if is_home else r["home_goals"])
        out.append("G" if a>b else "B" if a==b else "M")
    return " • ".join(out) if out else "—"


def render(completed, selected_match, prediction_model):
    home, away = selected_match["home"], selected_match["away"]
    before = selected_match["datetime"]
    h10 = _history(completed, home, before, 10)
    a10 = _history(completed, away, before, 10)
    hh = _history(completed, home, before, 10, "home")
    aa = _history(completed, away, before, 10, "away")
    hs, ass = _stats(h10, home), _stats(a10, away)
    hvs, avs = _stats(hh, home), _stats(aa, away)

    st.markdown("### 🆚 Maç + Takım Karşılaştırması • V3.31")
    st.caption("İki takımın maç öncesi formu, saha gücü, gol eğilimleri ve mevcut Poisson tahmini aynı panelde. Yalnızca maçtan önceki veriler kullanılır.")

    c1,c2 = st.columns(2)
    with c1:
        st.markdown(f"#### 🏠 {home}")
        st.metric("Son 5 form", _form(h10, home, 5))
        if hs:
            st.dataframe(pd.DataFrame([{"Dilim":"Son 10", **hs}, {"Dilim":"İç saha", **hvs} if hvs else {"Dilim":"İç saha"}]), hide_index=True, use_container_width=True)
        else: st.info("Yeterli geçmiş veri yok.")
    with c2:
        st.markdown(f"#### ✈️ {away}")
        st.metric("Son 5 form", _form(a10, away, 5))
        if ass:
            st.dataframe(pd.DataFrame([{"Dilim":"Son 10", **ass}, {"Dilim":"Deplasman", **avs} if avs else {"Dilim":"Deplasman"}]), hide_index=True, use_container_width=True)
        else: st.info("Yeterli geçmiş veri yok.")

    pred, err = prediction_model(completed, selected_match)
    st.markdown("#### 🧠 Aynı maçın model görünümü")
    if err:
        st.warning(err); return
    x1,x2,x3 = st.columns(3)
    x1.metric("1 • Ev", f'%{pred["1"]}')
    x2.metric("X", f'%{pred["X"]}')
    x3.metric("2 • Dep", f'%{pred["2"]}')
    g1,g2 = st.columns(2)
    g1.metric(f"{home} beklenen gol", pred["Ev gol beklentisi"])
    g2.metric(f"{away} beklenen gol", pred["Dep gol beklentisi"])
    st.caption("Bu panel raporlama/karşılaştırma katmanıdır; V3.14 Nihai Karar Motorunun eşiklerini veya kararlarını değiştirmez.")
