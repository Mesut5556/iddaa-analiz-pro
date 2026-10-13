import json
import urllib.request
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

st.set_page_config(page_title="İDDAA ANALİZ PRO", page_icon="⚽", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""<style>
.stApp {background:linear-gradient(180deg,#071426,#0b1d33);color:#eaf3fa}
.block-container {max-width:1200px;padding-top:1.4rem}
h1,h2,h3 {color:#fff!important}
.hero {background:linear-gradient(120deg,#102a43,#086b50);padding:24px;border-radius:18px;margin-bottom:16px}
.hero-title {font-size:30px;font-weight:900;color:#fff}
.hero-sub {color:#d8f4e8;margin-top:6px}
.stat-card,.match-card {background:#10253c;border:1px solid #23405b;border-radius:15px;padding:16px;margin-bottom:12px}
.stat-number {font-size:27px;font-weight:900;color:#43e39d}
.stat-label,.match-info {font-size:13px;color:#c9d5e0}
.badge {font-size:12px;font-weight:800;color:#43e39d;margin-bottom:7px}
.teams {font-size:18px;font-weight:800;color:#fff;margin-bottom:8px}
[data-testid="stRadio"] label,[data-testid="stSelectbox"] label {color:#eaf3fa!important}
@media(max-width:700px){.hero-title{font-size:24px}.block-container{padding-left:12px;padding-right:12px}}
</style>""", unsafe_allow_html=True)

API_URL = "https://fixturedownload.azurewebsites.net/feed/json/super-lig-2026"
TR_TZ = ZoneInfo("Europe/Istanbul")
UTC_TZ = ZoneInfo("UTC")

@st.cache_data(ttl=3600)
def get_matches():
    req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("Beklenmeyen veri biçimi.")
    rows = []
    for item in data:
        try:
            dt_utc = datetime.strptime(item["DateUtc"], "%Y-%m-%d %H:%M:%SZ").replace(tzinfo=UTC_TZ)
            dt = dt_utc.astimezone(TR_TZ)
            home, away = str(item["HomeTeam"]).strip(), str(item["AwayTeam"]).strip()
            if not home or not away:
                continue
            hs, ass = item.get("HomeTeamScore"), item.get("AwayTeamScore")
            finished = hs is not None and ass is not None
            if finished:
                hs, ass = int(hs), int(ass)
            else:
                hs, ass = None, None
            rows.append({"id":item.get("MatchNumber"),"round":item.get("RoundNumber","-"),
                         "home":home,"away":away,"datetime":dt,"date":dt.date(),
                         "time":dt.strftime("%H:%M"),"home_goals":hs,"away_goals":ass,
                         "score":f"{hs} - {ass}" if finished else "-", "finished":finished,
                         "location":str(item.get("Location") or "")})
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
    if not rows:
        raise ValueError("İşlenebilir maç verisi bulunamadı.")
    return pd.DataFrame(rows).sort_values("datetime").reset_index(drop=True)


def match_card(row):
    dt = row["datetime"].strftime("%d.%m.%Y %H:%M")
    html = ('<div class="match-card">'
            f'<div class="badge">SÜPER LİG • HAFTA {escape(str(row["round"]))}</div>'
            f'<div class="teams">{escape(row["home"])} ⚔️ {escape(row["away"])}</div>'
            f'<div class="match-info">📅 {dt} • 🏟️ {escape(row["location"] or "Stadyum belirtilmedi")}</div>'
            f'<div class="match-info">Skor: {escape(row["score"])}</div></div>')
    st.markdown(html, unsafe_allow_html=True)


def team_history(completed, team, before_date, limit=10, venue="all"):
    df = completed[completed["datetime"] < before_date]
    if venue == "home":
        df = df[df["home"] == team]
    elif venue == "away":
        df = df[df["away"] == team]
    else:
        df = df[(df["home"] == team) | (df["away"] == team)]
    return df.sort_values("datetime", ascending=False).head(limit).copy()


def team_stats(history, team):
    total = len(history)
    if not total:
        return None
    wins = draws = losses = gf = ga = overs = btts = 0
    for _, r in history.iterrows():
        home = r["home"] == team
        scored = r["home_goals"] if home else r["away_goals"]
        conceded = r["away_goals"] if home else r["home_goals"]
        gf += scored
        ga += conceded
        wins += scored > conceded
        draws += scored == conceded
        losses += scored < conceded
        overs += scored + conceded > 2
        btts += scored > 0 and conceded > 0
    return {"Maç":total,"G":wins,"B":draws,"M":losses,
            "Attığı gol/maç":round(gf/total,2),"Yediği gol/maç":round(ga/total,2),
            "2.5 Üst %":round(100*overs/total,1),"KG Var %":round(100*btts/total,1)}



def poisson_pmf(k, lam):
    import math
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def prediction_model(completed, selected_match):
    """Simple transparent Poisson model using only matches before kickoff."""
    home = selected_match["home"]
    away = selected_match["away"]
    before = selected_match["datetime"]

    league = completed[completed["datetime"] < before].copy()
    if len(league) < 20:
        return None, "Lig ortalaması için yeterli geçmiş maç yok."

    league_home_avg = league["home_goals"].mean()
    league_away_avg = league["away_goals"].mean()
    if league_home_avg <= 0 or league_away_avg <= 0:
        return None, "Gol ortalamaları hesaplanamadı."

    # Up to 10 most recent relevant venue matches, all strictly before kickoff.
    h = team_history(completed, home, before, 10, "home")
    a = team_history(completed, away, before, 10, "away")
    if len(h) < 2 or len(a) < 2:
        return None, "Ev/deplasman modeli için en az 2'şer geçmiş maç gerekiyor."

    h_for = h["home_goals"].mean()
    h_against = h["away_goals"].mean()
    a_for = a["away_goals"].mean()
    a_against = a["home_goals"].mean()

    # Shrink small samples toward league averages.
    wh = min(len(h) / 8.0, 1.0)
    wa = min(len(a) / 8.0, 1.0)
    h_for = wh * h_for + (1-wh) * league_home_avg
    h_against = wh * h_against + (1-wh) * league_away_avg
    a_for = wa * a_for + (1-wa) * league_away_avg
    a_against = wa * a_against + (1-wa) * league_home_avg

    home_attack = h_for / league_home_avg
    away_defence = a_against / league_home_avg
    away_attack = a_for / league_away_avg
    home_defence = h_against / league_away_avg

    lam_home = max(0.20, min(4.0, league_home_avg * home_attack * away_defence))
    lam_away = max(0.20, min(4.0, league_away_avg * away_attack * home_defence))

    max_goals = 10
    probs = {}
    p1 = px = p2 = over15 = over25 = btts = 0.0
    for hg in range(max_goals + 1):
        for ag in range(max_goals + 1):
            p = poisson_pmf(hg, lam_home) * poisson_pmf(ag, lam_away)
            probs[(hg, ag)] = p
            if hg > ag: p1 += p
            elif hg == ag: px += p
            else: p2 += p
            if hg + ag >= 2: over15 += p
            if hg + ag >= 3: over25 += p
            if hg > 0 and ag > 0: btts += p

    total = sum(probs.values())
    if total <= 0:
        return None, "Model olasılıkları hesaplanamadı."
    # Normalize truncated 0..10 score grid.
    p1, px, p2 = p1/total, px/total, p2/total
    over15, over25, btts = over15/total, over25/total, btts/total

    top_scores = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]
    top_scores = [(f"{s[0]}-{s[1]}", round(100*p/total,1)) for s,p in top_scores]

    return {
        "1": round(100*p1,1), "X": round(100*px,1), "2": round(100*p2,1),
        "1X": round(100*(p1+px),1), "X2": round(100*(px+p2),1), "12": round(100*(p1+p2),1),
        "1.5 Üst": round(100*over15,1), "1.5 Alt": round(100*(1-over15),1),
        "2.5 Üst": round(100*over25,1), "2.5 Alt": round(100*(1-over25),1),
        "KG Var": round(100*btts,1), "KG Yok": round(100*(1-btts),1),
        "Ev gol beklentisi": round(lam_home,2), "Dep gol beklentisi": round(lam_away,2),
        "Ev örneklem": len(h), "Dep örneklem": len(a), "Lig maç": len(league),
        "Skorlar": top_scores
    }, None


def prediction_table(pred):
    rows = [
        ["Maç Sonucu", "1", pred["1"]],
        ["Maç Sonucu", "X", pred["X"]],
        ["Maç Sonucu", "2", pred["2"]],
        ["Çifte Şans", "1X", pred["1X"]],
        ["Çifte Şans", "X2", pred["X2"]],
        ["Çifte Şans", "12", pred["12"]],
        ["Gol", "1.5 Üst", pred["1.5 Üst"]],
        ["Gol", "1.5 Alt", pred["1.5 Alt"]],
        ["Gol", "2.5 Üst", pred["2.5 Üst"]],
        ["Gol", "2.5 Alt", pred["2.5 Alt"]],
        ["KG", "KG Var", pred["KG Var"]],
        ["KG", "KG Yok", pred["KG Yok"]],
    ]
    return pd.DataFrame(rows, columns=["Pazar", "Seçenek", "Model %"])

def display_history(df):
    if df.empty:
        st.info("Bu ölçüt için oynanmış maç bulunamadı.")
        return
    d = df.copy()
    d["Tarih"] = d["datetime"].dt.strftime("%d.%m.%Y")
    d = d[["Tarih","home","away","score"]]
    d.columns = ["Tarih","Ev Sahibi","Deplasman","Skor"]
    st.dataframe(d, hide_index=True, use_container_width=True)


def stat_box(label, value):
    st.markdown(f'<div class="stat-card"><div class="stat-number">{value}</div><div class="stat-label">{escape(label)}</div></div>', unsafe_allow_html=True)

try:
    matches = get_matches()
    error = None
except Exception as exc:
    matches = pd.DataFrame()
    error = str(exc)

now = datetime.now(TR_TZ)
if error is None:
    completed = matches[matches["finished"] & (matches["datetime"] < now)].copy()
    future = matches[(~matches["finished"]) & (matches["datetime"] >= now)].copy()
    next7 = future[future["date"] <= now.date() + timedelta(days=7)]
    next15 = future[future["date"] <= now.date() + timedelta(days=15)]
else:
    completed = future = next7 = next15 = pd.DataFrame()

st.markdown('<div class="hero"><div class="hero-title">⚽ İDDAA ANALİZ PRO</div><div class="hero-sub">Süper Lig • İstatistik ve olasılık motoru • V1.3.2</div></div>', unsafe_allow_html=True)
if error:
    st.error("Veri kaynağına bağlanılamadı: " + error)
else:
    st.success("🟢 Fikstür ve skor verileri alındı.")
    st.caption("Kaynak: Fixture Download. Maç saatleri ve sonuçları resmî kaynaklarla kontrol edilmelidir.")

c1,c2,c3 = st.columns(3)
with c1: stat_box("7 Günlük Maç",len(next7))
with c2: stat_box("15 Günlük Maç",len(next15))
with c3: stat_box("Oynanmış Maç",len(completed))

menu = st.radio("Bölüm seç",["🏠 Ana Sayfa","📅 Fikstür","📊 Maç Analizi","⚙️ Ayarlar"],horizontal=True)

if menu == "🏠 Ana Sayfa":
    st.subheader("Önümüzdeki 15 Günün Maçları")
    if next15.empty:
        st.info("Önümüzdeki 15 gün içinde kayıtlı maç yok.")
    else:
        for _, row in next15.iterrows():
            match_card(row)

elif menu == "📅 Fikstür":
    st.subheader("Süper Lig Fikstürü")
    choice = st.selectbox("Gösterilecek maçlar",["Önümüzdeki 7 Gün","Önümüzdeki 15 Gün","Tüm Gelecek Maçlar","Geçmiş Maçlar","Tüm Sezon"])
    selected = {"Önümüzdeki 7 Gün":next7,"Önümüzdeki 15 Gün":next15,"Tüm Gelecek Maçlar":future,"Geçmiş Maçlar":completed,"Tüm Sezon":matches}[choice]
    if selected.empty:
        st.info("Bu bölümde maç bulunamadı.")
    else:
        d = selected.copy()
        d["Tarih"] = d["datetime"].dt.strftime("%d.%m.%Y")
        d = d[["round","Tarih","time","home","away","score"]]
        d.columns = ["Hafta","Tarih","Saat","Ev Sahibi","Deplasman","Skor"]
        st.dataframe(d, hide_index=True, use_container_width=True)

elif menu == "📊 Maç Analizi":
    st.subheader("Maç Analizi • V1.3.2")
    if future.empty:
        st.info("Analiz için gelecekteki maç bulunamadı.")
    else:
        labels = [f'{r["home"]} - {r["away"]} | {r["datetime"].strftime("%d.%m.%Y %H:%M")}' for _,r in future.iterrows()]
        pos = st.selectbox("Maç seç",range(len(labels)),format_func=lambda i: labels[i])
        selected_match = future.iloc[pos]
        match_card(selected_match)
        n = st.radio("Son kaç maç?",[5,10],horizontal=True)
        home,away = selected_match["home"],selected_match["away"]
        before = selected_match["datetime"]
        st.caption("Yalnızca seçilen maçtan önce oynanmış ve skoru bulunan karşılaşmalar kullanılır. Son 5/10 maç; tahmin yüzdesi değildir.")
        for team,venue in [(home,"home"),(away,"away")]:
            st.markdown(f"### {team}")
            overall = team_history(completed,team,before,n)
            venue_df = team_history(completed,team,before,n,venue)
            st.markdown(f"**Son {n} maç — genel**")
            s = team_stats(overall,team)
            if s:
                st.dataframe(pd.DataFrame([s]),hide_index=True,use_container_width=True)
                display_history(overall)
            else:
                st.warning("Bu sezon için yeterli geçmiş maç bulunamadı.")
            st.markdown("**İç saha**" if venue == "home" else "**Deplasman**")
            vs = team_stats(venue_df,team)
            if vs:
                st.dataframe(pd.DataFrame([vs]),hide_index=True,use_container_width=True)
                st.caption(f"Bu satır yalnızca {vs['Maç']} maç üzerinden hesaplandı.")
            else:
                st.info("Bu saha türünde geçmiş maç yok.")
        st.markdown("### 🧠 Model Olasılıkları")
        pred, pred_error = prediction_model(completed, selected_match)
        if pred_error:
            st.warning(pred_error)
        else:
            m1,m2,m3 = st.columns(3)
            with m1: stat_box("1 • Ev sahibi", f'%{pred["1"]}')
            with m2: stat_box("X • Beraberlik", f'%{pred["X"]}')
            with m3: stat_box("2 • Deplasman", f'%{pred["2"]}')
            st.dataframe(prediction_table(pred), hide_index=True, use_container_width=True)
            st.write(
                f'**Beklenen gol:** {home} {pred["Ev gol beklentisi"]} • '
                f'{away} {pred["Dep gol beklentisi"]}'
            )
            st.write("**En olası skorlar:** " + " • ".join(
                f'{score} (%{prob})' for score,prob in pred["Skorlar"]
            ))
            st.caption(
                f'Model yalnızca maçtan önceki verileri kullanır. Ev örneklemi: {pred["Ev örneklem"]}, '
                f'deplasman örneklemi: {pred["Dep örneklem"]}, lig geçmişi: {pred["Lig maç"]} maç. '
                'Yüzdeler istatistiksel model tahminidir; garanti veya bahis tavsiyesi değildir.'
            )

else:
    st.subheader("Ayarlar")
    st.write("**Lig:** Türkiye Süper Lig")
    st.write("**Sezon:** 2026–2027")
    st.write("**Kaynak:** Fixture Download")
    st.write("**Saat dilimi:** Europe/Istanbul")
    st.write("**Önbellek:** 60 dakika")
    if st.button("🔄 Verileri Yenile"):
        st.cache_data.clear()
        st.rerun()

st.divider()
st.caption("İDDAA ANALİZ PRO V1.3.2 • Poisson tabanlı olasılık modeli • Model tahminleri garanti değildir.")
