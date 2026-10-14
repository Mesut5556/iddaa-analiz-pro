"""V3.29 Team Analysis Center.
Read-only team dashboard built from fixture/results already loaded by app.py.
Does not alter prediction, decision, odds, coupon or settlement logic.
"""
import pandas as pd
import streamlit as st


def _team_matches(completed, team):
    if completed is None or completed.empty:
        return pd.DataFrame()
    return completed[(completed["home"] == team) | (completed["away"] == team)].sort_values("datetime", ascending=False).copy()


def _stats(df, team):
    if df is None or df.empty:
        return None
    w=d=l=gf=ga=over15=over25=btts=cs=0
    for _, r in df.iterrows():
        home = r["home"] == team
        a = int(r["home_goals"] if home else r["away_goals"])
        b = int(r["away_goals"] if home else r["home_goals"])
        gf += a; ga += b
        w += a > b; d += a == b; l += a < b
        over15 += a+b >= 2; over25 += a+b >= 3
        btts += a > 0 and b > 0; cs += b == 0
    n=len(df)
    return {"Maç":n,"G":w,"B":d,"M":l,"Puan":3*w+d,"Gol":gf,"Yenen":ga,
            "Gol/maç":round(gf/n,2),"Yenen/maç":round(ga/n,2),
            "1.5 Üst %":round(100*over15/n,1),"2.5 Üst %":round(100*over25/n,1),
            "KG Var %":round(100*btts/n,1),"Gol yemeden %":round(100*cs/n,1)}


def _form(df, team, n=5):
    out=[]
    for _,r in df.head(n).iterrows():
        home=r["home"]==team
        a=int(r["home_goals"] if home else r["away_goals"]); b=int(r["away_goals"] if home else r["home_goals"])
        out.append("G" if a>b else "B" if a==b else "M")
    return " • ".join(out) if out else "—"


def _display_matches(df, team, limit=10):
    if df is None or df.empty:
        st.info("Gösterilecek maç bulunamadı."); return
    rows=[]
    for _,r in df.head(limit).iterrows():
        home=r["home"]==team
        a=int(r["home_goals"] if home else r["away_goals"]); b=int(r["away_goals"] if home else r["home_goals"])
        rows.append({"Tarih":r["datetime"].strftime("%d.%m.%Y"),"Ev":r["home"],"Deplasman":r["away"],
                     "Skor":f'{r["home_goals"]}-{r["away_goals"]}',"Takım sonucu":"✅ G" if a>b else "➖ B" if a==b else "❌ M"})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)


def render(matches, completed, current_season, future, league_table_before):
    st.subheader("🛡️ Takım Analiz Merkezi • V3.29")
    st.caption("Takımın formunu, iç/deplasman performansını, gol eğilimlerini, lig konumunu ve yaklaşan maçlarını tek ekranda gösterir. Karar motorunu değiştirmez.")
    if matches is None or matches.empty:
        st.info("Takım analizi için veri yok."); return

    # V3.29: Takım seçiciyi yalnızca güncel 2026-27 Süper Lig takımlarıyla sınırla.
    # Eski sezonlarda yer alan ancak bu sezon ligde olmayan takımlar seçim listesine girmez.
    if current_season is not None and not current_season.empty:
        selector_df = current_season.copy()
        if "season" in selector_df.columns:
            selector_df = selector_df[selector_df["season"].astype(str).eq("2026-27")].copy()
        teams = sorted(set(selector_df["home"].dropna()) | set(selector_df["away"].dropna()))
    else:
        teams = []

    if not teams:
        st.info("2026-27 Süper Lig takım listesi oluşturulamadı.")
        return

    team=st.selectbox("Takım seç",teams)
    hist=_team_matches(completed,team)

    # Güncel sezon verisini modül içinde de kesin olarak 2026-27 ile sınırla.
    # Böylece eski sezonlar hiçbir koşulda "Güncel sezon görünümü"ne karışmaz.
    if current_season is not None and not current_season.empty:
        season_df = current_season.copy()
        if "season" in season_df.columns:
            season_df = season_df[season_df["season"].astype(str).eq("2026-27")].copy()
        season_played = season_df[season_df["finished"] == True].copy()  # noqa:E712
    else:
        season_df = pd.DataFrame()
        season_played = pd.DataFrame()

    season_hist=_team_matches(season_played,team)
    # İç/deplasman sezon özeti için güncel sezonda maç yoksa eski sezonlara düşme.
    base=season_hist
    last5=hist.head(5); last10=hist.head(10)

    st.markdown(f"## {team}")
    s5=_stats(last5,team)
    s10=_stats(last10,team)
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Son 5 form",_form(hist,team,5))
    c2.metric("Son 5 puan",s5["Puan"] if s5 else "—")
    c3.metric("Son 10 gol/maç",s10["Gol/maç"] if s10 else "—")
    c4.metric("Son 10 yenen/maç",s10["Yenen/maç"] if s10 else "—")

    st.markdown("### 📍 Güncel sezon görünümü")
    if season_played.empty or season_hist.empty:
        st.info("Bu takımın 2026-27 Süper Lig sezonunda oynanmış maçı bulunmuyor.")
    else:
        table=league_table_before(season_played.copy(), pd.Timestamp.now(tz="Europe/Istanbul") + pd.Timedelta(days=1))
        if table is not None and not table.empty and team in set(table["Takım"]):
            st.dataframe(table[table["Takım"]==team],hide_index=True,use_container_width=True)
        else:
            st.info("Bu takım için 2026-27 güncel lig sırası hesaplanamadı.")

    home_df=base[base["home"]==team].head(10); away_df=base[base["away"]==team].head(10)
    summary=[]
    for label,df in [("Son 5",last5),("Son 10",last10),("İç saha",home_df),("Deplasman",away_df)]:
        s=_stats(df,team)
        if s: summary.append({"Dilim":label,**s})
    st.markdown("### 📊 Performans özeti")
    if summary: st.dataframe(pd.DataFrame(summary),hide_index=True,use_container_width=True)

    st.markdown("### ⚽ Gol eğilimleri • son 10")
    if s10:
        a,b,c,d=st.columns(4)
        a.metric("1.5 Üst",f'%{s10["1.5 Üst %"]:.1f}')
        b.metric("2.5 Üst",f'%{s10["2.5 Üst %"]:.1f}')
        c.metric("KG Var",f'%{s10["KG Var %"]:.1f}')
        d.metric("Gol yemeden",f'%{s10["Gol yemeden %"]:.1f}')

    st.markdown("### 🧾 Son maçlar")
    _display_matches(hist,team,10)

    st.markdown("### 📅 Yaklaşan maçlar")
    upcoming=future[(future["home"]==team)|(future["away"]==team)].sort_values("datetime").head(5) if future is not None and not future.empty else pd.DataFrame()
    if upcoming.empty: st.info("Kayıtlı yaklaşan maç bulunamadı.")
    else:
        d=upcoming.copy(); d["Tarih"]=d["datetime"].dt.strftime("%d.%m.%Y %H:%M")
        st.dataframe(d[["Tarih","home","away","round"]].rename(columns={"home":"Ev","away":"Deplasman","round":"Hafta"}),hide_index=True,use_container_width=True)

    st.info("Bu ekran bet önerisi üretmez. İstatistikler mevcut fikstür/skor verilerinden hesaplanır; geçmiş performans gelecekteki sonucu garanti etmez.")
