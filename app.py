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

BASE_URL = "https://fixturedownload.azurewebsites.net/feed/json/super-lig-{}"
SEASONS = [2023, 2024, 2025, 2026]
TEAM_ALIASES = {
    "besiktas": "Besiktas", "beşiktaş": "Besiktas",
    "istanbul basaksehir": "Istanbul Basaksehir", "istanbul başakşehir": "Istanbul Basaksehir",
    "basaksehir": "Istanbul Basaksehir", "başakşehir": "Istanbul Basaksehir",
    "gaziantep fk": "Gaziantep", "gaziantep f.k.": "Gaziantep",
    "gaziantep f.k": "Gaziantep", "gaziantep": "Gaziantep",
    "rizespor": "Çaykur Rizespor", "caykur rizespor": "Çaykur Rizespor",
    "çaykur rizespor": "Çaykur Rizespor",
    "kasimpasa": "Kasimpasa", "kasımpaşa": "Kasimpasa",
    "genclerbirligi": "Gençlerbirliği", "gençlerbirliği": "Gençlerbirliği",
    "eyupspor": "Eyüpspor", "eyüpspor": "Eyüpspor",
    "amed": "Amedspor", "amedspor": "Amedspor",
    "corum": "Çorum", "çorum": "Çorum", "çorum fk": "Çorum",
    "erzurumspor fk": "Erzurumspor", "erzurumspor": "Erzurumspor",
    "samsunspor": "Samsunspor",
    "fenerbahce": "Fenerbahçe", "fenerbahçe": "Fenerbahçe",
    "galatasaray": "Galatasaray",
}

def normalize_team(name):
    name = str(name).strip()
    return TEAM_ALIASES.get(name.casefold(), name)
TR_TZ = ZoneInfo("Europe/Istanbul")
UTC_TZ = ZoneInfo("UTC")

@st.cache_data(ttl=3600)
def get_matches():
    rows = []
    failures = []
    for season in SEASONS:
        url = BASE_URL.format(season)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0", "Accept": "application/json"
            })
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            if not isinstance(data, list) or not data:
                raise ValueError("Boş veya beklenmeyen JSON")
        except Exception as exc:
            failures.append(f"{season}-{str(season+1)[-2:]}: {type(exc).__name__}")
            continue

        for item in data:
            try:
                dt_utc = datetime.strptime(item["DateUtc"], "%Y-%m-%d %H:%M:%SZ").replace(tzinfo=UTC_TZ)
                dt = dt_utc.astimezone(TR_TZ)
                home = normalize_team(item["HomeTeam"])
                away = normalize_team(item["AwayTeam"])
                if not home or not away:
                    continue
                hs, ass = item.get("HomeTeamScore"), item.get("AwayTeamScore")
                finished = hs is not None and ass is not None
                hs, ass = (int(hs), int(ass)) if finished else (None, None)
                rows.append({
                    "id": item.get("MatchNumber"), "round": item.get("RoundNumber", "-"),
                    "season": f"{season}-{str(season+1)[-2:]}",
                    "home": home, "away": away, "datetime": dt, "date": dt.date(),
                    "time": dt.strftime("%H:%M"), "home_goals": hs, "away_goals": ass,
                    "score": f"{hs} - {ass}" if finished else "-", "finished": finished,
                    "location": str(item.get("Location") or "")
                })
            except (KeyError, ValueError, TypeError, OverflowError):
                continue

    if not rows:
        raise ValueError("Hiçbir sezon indirilemedi. Bağlantıyı kontrol et.")
    df = pd.DataFrame(rows).sort_values("datetime")
    df = df.drop_duplicates(subset=["datetime", "home", "away"], keep="last")
    return df.reset_index(drop=True), failures


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



@st.cache_data(ttl=3600)
def run_backtest(matches):
    """
    Walk-forward backtest:
    each historical match is predicted using only earlier completed matches.
    """
    finished_all = matches[matches["finished"] & (matches["datetime"] < datetime.now(TR_TZ))].sort_values("datetime").copy()
    rows = []

    for _, target in finished_all.iterrows():
        prior = finished_all[finished_all["datetime"] < target["datetime"]].copy()
        pred, err = prediction_model(prior, target)
        if err or pred is None:
            continue

        hg = int(target["home_goals"])
        ag = int(target["away_goals"])
        actual_1x2 = "1" if hg > ag else ("X" if hg == ag else "2")
        predicted_1x2 = max(["1", "X", "2"], key=lambda k: pred[k])

        actual_over15 = hg + ag >= 2
        actual_over25 = hg + ag >= 3
        actual_btts = hg > 0 and ag > 0

        rows.append({
            "Tarih": target["datetime"].strftime("%d.%m.%Y"),
            "Sezon": target["season"],
            "Ev": target["home"],
            "Dep": target["away"],
            "Skor": f"{hg}-{ag}",
            "Gerçek 1X2": actual_1x2,
            "Tahmin 1X2": predicted_1x2,
            "1X2 Doğru": predicted_1x2 == actual_1x2,
            "1X2 Güven": pred[predicted_1x2],
            "1.5 Tahmin": pred["1.5 Üst"] >= 50,
            "1.5 Güven": max(pred["1.5 Üst"], pred["1.5 Alt"]),
            "1.5 Gerçek": actual_over15,
            "1.5 Doğru": (pred["1.5 Üst"] >= 50) == actual_over15,
            "2.5 Tahmin": pred["2.5 Üst"] >= 50,
            "2.5 Güven": max(pred["2.5 Üst"], pred["2.5 Alt"]),
            "2.5 Gerçek": actual_over25,
            "2.5 Doğru": (pred["2.5 Üst"] >= 50) == actual_over25,
            "KG Tahmin": pred["KG Var"] >= 50,
            "KG Güven": max(pred["KG Var"], pred["KG Yok"]),
            "KG Gerçek": actual_btts,
            "KG Doğru": (pred["KG Var"] >= 50) == actual_btts,
        })

    return pd.DataFrame(rows)


def select_signals(pred):
    """
    Conservative signal layer.
    It does not force a pick for every market. Weak/uncertain markets are PASS.
    Thresholds are intentionally stricter than 50%.
    """
    signals = []

    # 1-X-2: require a clear favorite and separation from second choice.
    one_x_two = {"1": pred["1"], "X": pred["X"], "2": pred["2"]}
    ranked = sorted(one_x_two.items(), key=lambda x: x[1], reverse=True)
    best_name, best_prob = ranked[0]
    margin = best_prob - ranked[1][1]
    if best_prob >= 48 and margin >= 8:
        signals.append(("1-X-2", best_name, best_prob, "UYGUN"))
    else:
        signals.append(("1-X-2", "PAS", best_prob, "ZAYIF"))

    # Double chance: only surface strong coverage.
    dc = {"1X": pred["1X"], "X2": pred["X2"], "12": pred["12"]}
    dc_name, dc_prob = max(dc.items(), key=lambda x: x[1])
    if dc_prob >= 72:
        signals.append(("Çifte Şans", dc_name, dc_prob, "GÜÇLÜ"))
    elif dc_prob >= 66:
        signals.append(("Çifte Şans", dc_name, dc_prob, "UYGUN"))
    else:
        signals.append(("Çifte Şans", "PAS", dc_prob, "ZAYIF"))

    # Goal markets: choose only if one side clears confidence threshold.
    for market, over_key, alt_key in [
        ("1.5 Gol", "1.5 Üst", "1.5 Alt"),
        ("2.5 Gol", "2.5 Üst", "2.5 Alt"),
    ]:
        if pred[over_key] >= pred[alt_key]:
            pick, prob = over_key, pred[over_key]
        else:
            pick, prob = alt_key, pred[alt_key]
        if prob >= 70:
            status = "GÜÇLÜ"
        elif prob >= 62:
            status = "UYGUN"
        else:
            pick, status = "PAS", "ZAYIF"
        signals.append((market, pick, prob, status))

    # KG deliberately requires a high threshold because V1.4 backtest was weak.
    if pred["KG Var"] >= pred["KG Yok"]:
        kg_pick, kg_prob = "KG Var", pred["KG Var"]
    else:
        kg_pick, kg_prob = "KG Yok", pred["KG Yok"]
    if kg_prob >= 70:
        signals.append(("KG", kg_pick, kg_prob, "DENEYSEL"))
    else:
        signals.append(("KG", "PAS", kg_prob, "KAPALI"))

    return pd.DataFrame(signals, columns=["Pazar", "Model Seçimi", "Model %", "Durum"])


def threshold_audit(bt, confidence_col, correct_col, thresholds=(50,55,60,65,70,75,80)):
    rows = []
    total = len(bt)
    for threshold in thresholds:
        sample = bt[bt[confidence_col] >= threshold]
        n = len(sample)
        if n:
            accuracy = round(100 * sample[correct_col].mean(), 1)
            coverage = round(100 * n / total, 1)
        else:
            accuracy = None
            coverage = 0.0
        rows.append([f"%{threshold}+", n, accuracy, coverage])
    return pd.DataFrame(rows, columns=["Güven Eşiği", "Maç", "İsabet %", "Kapsama %"])

def choose_threshold(training, confidence_col, correct_col, minimum=30):
    """Select once on development seasons; never inspect holdout outcomes."""
    candidates = threshold_audit(training, confidence_col, correct_col)
    eligible = candidates[candidates["Maç"] >= minimum].copy()
    if eligible.empty:
        return None
    # Prioritize observed accuracy; prefer wider coverage on a tie.
    best = eligible.sort_values(["İsabet %", "Maç"], ascending=[False, False]).iloc[0]
    return int(best["Güven Eşiği"].replace("%", "").replace("+", ""))


def evaluate_holdout(train, test, confidence_col, correct_col, minimum=30):
    threshold = choose_threshold(train, confidence_col, correct_col, minimum)
    if threshold is None:
        return {"Eşik": "Seçilemedi", "Eğitim maç": len(train), "Test maç": len(test),
                "Seçilen test": 0, "Kapsama %": None, "Test isabet %": None}
    chosen = test[test[confidence_col] >= threshold]
    return {"Eşik": f"%{threshold}+", "Eğitim maç": len(train), "Test maç": len(test),
            "Seçilen test": len(chosen),
            "Kapsama %": round(100 * len(chosen) / len(test), 1) if len(test) else None,
            "Test isabet %": round(100 * chosen[correct_col].mean(), 1) if len(chosen) else None}


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
    matches, download_failures = get_matches()
    error = None
except Exception as exc:
    matches = pd.DataFrame()
    download_failures = []
    error = str(exc)

now = datetime.now(TR_TZ)
if error is None:
    completed = matches[matches["finished"] & (matches["datetime"] < now)].copy()
    current_season = matches[matches["season"] == "2026-27"].copy()
    future = current_season[(~current_season["finished"]) & (current_season["datetime"] >= now)].copy()
    next7 = future[future["date"] <= now.date() + timedelta(days=7)]
    next15 = future[future["date"] <= now.date() + timedelta(days=15)]
else:
    completed = future = next7 = next15 = current_season = pd.DataFrame()

st.markdown('<div class="hero"><div class="hero-title">⚽ İDDAA ANALİZ PRO</div><div class="hero-sub">Süper Lig • Çok sezonlu analiz ve backtest • V1.6</div></div>', unsafe_allow_html=True)
if error:
    st.error("Veri kaynağına bağlanılamadı: " + error)
else:
    st.success("🟢 Fikstür ve skor verileri alındı.")
    st.caption("Kaynak: Fixture Download. Maç saatleri ve sonuçları resmî kaynaklarla kontrol edilmelidir.")
    if download_failures:
        st.warning("İndirilemeyen sezonlar: " + ", ".join(download_failures) + ". Test mevcut verilerle devam ediyor.")
    if current_season.empty:
        st.warning("2026-27 fikstürü indirilemedi; gelecek maçlar geçici olarak gösterilemiyor.")

c1,c2,c3 = st.columns(3)
with c1: stat_box("7 Günlük Maç",len(next7))
with c2: stat_box("15 Günlük Maç",len(next15))
with c3: stat_box("Tüm Sezonlarda Oynanmış",len(completed))

menu = st.radio("Bölüm seç",["🏠 Ana Sayfa","📅 Fikstür","📊 Maç Analizi","🧪 Backtest","⚙️ Ayarlar"],horizontal=True)

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
    selected = {"Önümüzdeki 7 Gün":next7,"Önümüzdeki 15 Gün":next15,"Tüm Gelecek Maçlar":future,"Geçmiş Maçlar":completed,"Tüm Sezon":current_season}[choice]
    if selected.empty:
        st.info("Bu bölümde maç bulunamadı.")
    else:
        d = selected.copy()
        d["Tarih"] = d["datetime"].dt.strftime("%d.%m.%Y")
        d = d[["round","Tarih","time","home","away","score"]]
        d.columns = ["Hafta","Tarih","Saat","Ev Sahibi","Deplasman","Skor"]
        st.dataframe(d, hide_index=True, use_container_width=True)

elif menu == "📊 Maç Analizi":
    st.subheader("Maç Analizi • V1.6")
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
            st.markdown("### 🚦 Güven Filtresi")
            sig = select_signals(pred)
            st.dataframe(sig, hide_index=True, use_container_width=True)
            strong_count = int(sig["Durum"].isin(["GÜÇLÜ","UYGUN"]).sum())
            if strong_count == 0:
                st.warning("Bu maçta ana filtreler yeterince güçlü sinyal bulamadı: PAS.")
            else:
                st.success(f"Bu maçta {strong_count} pazar güven filtresini geçti.")
            st.caption(
                "PAS bir hata değildir. Amaç her maça seçim üretmek yerine zayıf sinyalleri elemek. "
                "KG pazarı, V1.4 backtestinde zayıf kaldığı için daha sert eşikle ve deneysel statüde tutulur."
            )

elif menu == "🧪 Backtest":
    st.subheader("🧪 Çok Sezonlu Backtest • V1.6")
    st.caption(
        "Her geçmiş maç, yalnızca o maçtan daha önce oynanmış karşılaşmalar kullanılarak yeniden tahmin edilir. "
        "Bu test oran/kârlılık testi değil; modelin sonuç sınıflandırma isabetini ölçer. "
        "Önceki sezon kadroları farklı olabilir; model bunu henüz dikkate almıyor."
    )

    if not completed.empty:
        season_counts = completed.groupby("season").size().reset_index(name="Oynanmış Maç")
        season_counts.columns = ["Sezon", "Oynanmış Maç"]
        st.dataframe(season_counts, hide_index=True, use_container_width=True)

    bt = run_backtest(completed)

    if bt.empty:
        st.warning("Backtest için yeterli geçmiş veri oluşmadı.")
    else:
        total = len(bt)
        acc_1x2 = round(100 * bt["1X2 Doğru"].mean(), 1)
        acc_15 = round(100 * bt["1.5 Doğru"].mean(), 1)
        acc_25 = round(100 * bt["2.5 Doğru"].mean(), 1)
        acc_kg = round(100 * bt["KG Doğru"].mean(), 1)

        b1,b2,b3,b4 = st.columns(4)
        with b1: stat_box("Test Edilen Maç", total)
        with b2: stat_box("1-X-2 İsabet", f"%{acc_1x2}")
        with b3: stat_box("2.5 Alt/Üst İsabet", f"%{acc_25}")
        with b4: stat_box("KG Var/Yok İsabet", f"%{acc_kg}")

        st.markdown("### Pazar Bazında Sonuç")
        summary = pd.DataFrame([
            ["1-X-2", total, acc_1x2],
            ["1.5 Alt/Üst", total, acc_15],
            ["2.5 Alt/Üst", total, acc_25],
            ["KG Var/Yok", total, acc_kg],
        ], columns=["Pazar", "Test Maçı", "İsabet %"])
        st.dataframe(summary, hide_index=True, use_container_width=True)

        st.markdown("### 🔒 Bağımsız Sezon Doğrulaması")
        st.caption(
            "Geliştirme: 2023-24, 2024-25, 2025-26. Ayrılmış test: 2026-27. "
            "Eşikler yalnızca geliştirme sezonlarında seçilir; test sezonunun sonuçları "
            "eşik belirlemek için kullanılmaz. Test sezonundaki tahminler maçtan önceki "
            "sonuçlardan yararlanabilir (walk-forward)."
        )
        train = bt[bt["Sezon"].isin(["2023-24", "2024-25", "2025-26"])].copy()
        test = bt[bt["Sezon"] == "2026-27"].copy()
        if train.empty or test.empty:
            st.warning("Geliştirme veya 2026-27 test sezonunda yeterli veri bulunamadı.")
        else:
            markets = {
                "1-X-2": ("1X2 Güven", "1X2 Doğru"),
                "1.5 Alt/Üst": ("1.5 Güven", "1.5 Doğru"),
                "2.5 Alt/Üst": ("2.5 Güven", "2.5 Doğru"),
                "KG Var/Yok": ("KG Güven", "KG Doğru"),
            }
            result_rows = []
            for label, (confidence, correct) in markets.items():
                r = evaluate_holdout(train, test, confidence, correct, minimum=30)
                r["Pazar"] = label
                r["Test genel isabet %"] = round(100 * test[correct].mean(), 1)
                result_rows.append(r)
            cols = ["Pazar", "Eşik", "Eğitim maç", "Test maç", "Seçilen test", "Kapsama %", "Test isabet %", "Test genel isabet %"]
            st.dataframe(pd.DataFrame(result_rows)[cols], hide_index=True, use_container_width=True)
            st.warning(
                "2026-27 sezonu henüz tamamlanmadı. Bağımsız test sayısı düşükse sonuç "
                "kesin değildir. Eşik seçimi geliştirme verisinde yapılmış olsa bile, "
                "bu ekrana bakarak eşikleri değiştirmek test bağımsızlığını bozar. "
                "İsabet oranı kârlılık veya gelecekte başarı garantisi değildir."
            )
            st.markdown("#### 1.5 Alt/Üst: test sezonunda sabit eşikler")
            st.dataframe(threshold_audit(test, "1.5 Güven", "1.5 Doğru"),
                         hide_index=True, use_container_width=True)

        st.markdown("### 🎯 Güven Eşiği Analizi")
        st.caption(
            "Aşağıdaki tablolar, model güveni yükseldikçe isabetin gerçekten yükselip yükselmediğini gösterir. "
            "Az maçlı satırlar yanıltıcı olabilir; Maç ve Kapsama sütunlarını birlikte değerlendir."
        )

        audit_market = st.radio(
            "Pazar seç",
            ["1-X-2", "1.5 Alt/Üst", "2.5 Alt/Üst", "KG Var/Yok"],
            horizontal=True,
            key="audit_market"
        )
        audit_map = {
            "1-X-2": ("1X2 Güven", "1X2 Doğru"),
            "1.5 Alt/Üst": ("1.5 Güven", "1.5 Doğru"),
            "2.5 Alt/Üst": ("2.5 Güven", "2.5 Doğru"),
            "KG Var/Yok": ("KG Güven", "KG Doğru"),
        }
        conf_col, correct_col = audit_map[audit_market]
        audit_df = threshold_audit(bt, conf_col, correct_col)
        st.dataframe(audit_df, hide_index=True, use_container_width=True)

        usable = audit_df[(audit_df["Maç"] >= 5) & audit_df["İsabet %"].notna()].copy()
        if not usable.empty:
            # Prefer accuracy; on ties prefer more coverage.
            best = usable.sort_values(["İsabet %", "Kapsama %"], ascending=False).iloc[0]
            st.info(
                f'Bu küçük örneklemde {audit_market} için en iyi görünen eşik '
                f'{best["Güven Eşiği"]}: {int(best["Maç"])} maç, '
                f'%{best["İsabet %"]} isabet, %{best["Kapsama %"]} kapsama.'
            )
        else:
            st.warning("Bu pazar/eşik için yorum yapmaya yetecek en az 5 maçlık örneklem yok.")

        st.warning(
            "Eşikler bu veri üzerinde karşılaştırılıyor. Aynı veride en iyi eşiği seçmek, "
            "bağımsız doğrulama olmadan gerçek performans kanıtı değildir."
        )

        st.markdown("### Son Backtest Maçları")
        recent_bt = bt.sort_index(ascending=False).head(20).copy()
        recent_bt["1-X-2"] = recent_bt.apply(
            lambda r: f'{r["Tahmin 1X2"]} {"✅" if r["1X2 Doğru"] else "❌"}', axis=1
        )
        recent_bt["2.5"] = recent_bt.apply(
            lambda r: f'{"Üst" if r["2.5 Tahmin"] else "Alt"} {"✅" if r["2.5 Doğru"] else "❌"}', axis=1
        )
        recent_bt["KG"] = recent_bt.apply(
            lambda r: f'{"Var" if r["KG Tahmin"] else "Yok"} {"✅" if r["KG Doğru"] else "❌"}', axis=1
        )
        st.dataframe(
            recent_bt[["Tarih","Ev","Dep","Skor","1-X-2","2.5","KG"]],
            hide_index=True,
            use_container_width=True
        )

        st.info(
            "Test birden fazla sezondaki maçları tarih sırasıyla kullanır. "
            "Her tahmin yalnızca kendi maçından önceki sonuçları görür. "
            "Yukarıdaki ayrılmış sezon testi kupon motorundan önce değerlendirilmelidir."
        )

else:
    st.subheader("Ayarlar")
    st.write("**Lig:** Türkiye Süper Lig")
    st.write("**Sezonlar:** 2023–24, 2024–25, 2025–26, 2026–27")
    if error is None:
        st.write("**Yüklenen sezonlar:** " + ", ".join(sorted(matches["season"].unique())))
    st.write("**Kaynak:** Fixture Download")
    st.write("**Saat dilimi:** Europe/Istanbul")
    st.write("**Önbellek:** 60 dakika")
    if st.button("🔄 Verileri Yenile"):
        st.cache_data.clear()
        st.rerun()

st.divider()
st.caption("İDDAA ANALİZ PRO V1.6 • Çok sezonlu backtest • Model tahminleri garanti değildir.")
