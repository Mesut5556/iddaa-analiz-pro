import json
import urllib.request
import urllib.parse
import unicodedata
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
/* V3.14 mobile button contrast */
.stButton > button, .stDownloadButton > button {
  background:#17324f!important; color:#ffffff!important; border:1px solid #315778!important;
  font-weight:700!important; opacity:1!important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  background:#1f466c!important; color:#ffffff!important; border-color:#43e39d!important;
}
.stButton > button:active, .stDownloadButton > button:active {
  background:#0f7a5c!important; color:#ffffff!important;
}
.stButton > button:disabled {
  background:#21364b!important; color:#aebdca!important; opacity:.72!important;
}
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




def weighted_form(history, team):
    """Recency-weighted form: newest match gets the largest weight."""
    if history.empty:
        return None
    h = history.sort_values("datetime").copy()
    weights = list(range(1, len(h)+1))
    pts = gf = ga = 0.0
    sw = float(sum(weights))
    for w, (_, r) in zip(weights, h.iterrows()):
        is_home = r["home"] == team
        scored = float(r["home_goals"] if is_home else r["away_goals"])
        conceded = float(r["away_goals"] if is_home else r["home_goals"])
        gf += w * scored; ga += w * conceded
        pts += w * (3 if scored > conceded else 1 if scored == conceded else 0)
    return {"Ağırlıklı form %": round(100*pts/(3*sw),1),
            "Ağırlıklı gol/maç": round(gf/sw,2), "Ağırlıklı yenen/maç": round(ga/sw,2)}

def h2h_stats(completed, home, away, before, limit=8):
    d=completed[(completed["datetime"]<before) & (((completed["home"]==home)&(completed["away"]==away))|((completed["home"]==away)&(completed["away"]==home)))].sort_values("datetime",ascending=False).head(limit)
    if d.empty: return None, d
    hw=dr=aw=over25=btts=0
    for _,r in d.iterrows():
        hg,ag=int(r["home_goals"]),int(r["away_goals"])
        # result from selected home team's perspective
        sf = hg if r["home"]==home else ag; sa = ag if r["home"]==home else hg
        hw += sf>sa; dr += sf==sa; aw += sf<sa
        over25 += hg+ag>=3; btts += hg>0 and ag>0
    n=len(d)
    return {"H2H maç":n, f"{home} G":hw,"B":dr,f"{away} G":aw,"2.5 Üst %":round(100*over25/n,1),"KG Var %":round(100*btts/n,1)}, d

def league_table_before(completed, before):
    d=completed[completed["datetime"]<before]
    teams=sorted(set(d["home"])|set(d["away"]))
    rows=[]
    for t in teams:
        m=d[(d["home"]==t)|(d["away"]==t)]; pts=gf=ga=w=dr=l=0
        for _,r in m.iterrows():
            ih=r["home"]==t; a=int(r["home_goals"] if ih else r["away_goals"]); b=int(r["away_goals"] if ih else r["home_goals"])
            gf+=a; ga+=b
            if a>b: w+=1; pts+=3
            elif a==b: dr+=1; pts+=1
            else: l+=1
        rows.append({"Takım":t,"O":len(m),"G":w,"B":dr,"M":l,"AG":gf,"YG":ga,"AV":gf-ga,"P":pts})
    tab=pd.DataFrame(rows)
    if tab.empty:return tab
    return tab.sort_values(["P","AV","AG"],ascending=[False,False,False]).reset_index(drop=True).assign(Sıra=lambda x: range(1,len(x)+1))[["Sıra","Takım","O","G","B","M","AG","YG","AV","P"]]

def market_backtest_reliability(bt, market, confidence):
    """Historical classification reliability at a comparable confidence level.
    Uses only matches already available in the supplied walk-forward backtest.
    This is not an odds/profit backtest.
    """
    mapping = {
        "1-X-2": ("1X2 Güven", "1X2 Doğru"),
        "Çifte Şans": ("ÇS Güven", "ÇS Doğru"),
        "1.5 Gol": ("1.5 Güven", "1.5 Doğru"),
        "2.5 Gol": ("2.5 Güven", "2.5 Doğru"),
        "KG": ("KG Güven", "KG Doğru"),
    }
    if bt is None or bt.empty or market not in mapping:
        return None
    ccol, okcol = mapping[market]
    if ccol not in bt.columns or okcol not in bt.columns:
        return None
    # Comparable band: current confidence or higher, but never below 60.
    threshold = max(60.0, float(confidence) - 3.0)
    sample = bt[bt[ccol] >= threshold]
    # If too sparse, broaden once; still report sample size explicitly.
    if len(sample) < 30:
        threshold = max(55.0, float(confidence) - 8.0)
        sample = bt[bt[ccol] >= threshold]
    if sample.empty:
        return None
    return {
        "Eşik": round(threshold, 1),
        "Örnek": int(len(sample)),
        "İsabet %": round(100 * sample[okcol].mean(), 1),
    }


def smart_final_decision(pred, signals, bt_prior, home, away, wf_home=None, wf_away=None, h2h=None):
    """V3.14 transparent final decision layer.
    Model probability is NOT recalibrated. Historical reliability and context are
    used as support/veto checks rather than being blended into a fake probability.
    """
    rows = []
    for _, r in signals.iterrows():
        pick = r["Model Seçimi"]
        market = r["Pazar"]
        conf = float(r["Model %"])
        if pick == "PAS":
            continue
        rel = market_backtest_reliability(bt_prior, market, conf)
        hist_acc = rel["İsabet %"] if rel else None
        n = rel["Örnek"] if rel else 0

        support = 0
        notes = []
        # Backtest is the main validation gate; require meaningful sample.
        if rel and n >= 30:
            if hist_acc >= 70:
                support += 2; notes.append(f"geçmiş isabet %{hist_acc} (n={n})")
            elif hist_acc >= 60:
                support += 1; notes.append(f"geçmiş isabet %{hist_acc} (n={n})")
            else:
                support -= 2; notes.append(f"zayıf geçmiş isabet %{hist_acc} (n={n})")
        else:
            support -= 1; notes.append("backtest örneği yetersiz")

        # Context is only a confirmation/veto signal; it never changes Model %.
        if wf_home and wf_away and market in ("1-X-2", "Çifte Şans"):
            hf=float(wf_home["Ağırlıklı form %"]); af=float(wf_away["Ağırlıklı form %"])
            if pick in ("1", "1X") and hf >= af + 8:
                support += 1; notes.append("ağırlıklı form ev yönünü destekliyor")
            elif pick in ("2", "X2") and af >= hf + 8:
                support += 1; notes.append("ağırlıklı form deplasman yönünü destekliyor")
            elif pick == "12" and abs(hf-af) <= 12:
                notes.append("formlar yakın")
        h2h_ctx = h2h
        if isinstance(h2h_ctx, tuple):
            h2h_ctx = h2h_ctx[0] if h2h_ctx else None
        if isinstance(h2h_ctx, pd.Series):
            h2h_ctx = h2h_ctx.to_dict()
        if isinstance(h2h_ctx, dict) and h2h_ctx.get("H2H maç", 0) >= 3:
            if market == "2.5 Gol":
                rate=float(h2h_ctx["2.5 Üst %"])
                agrees = ("Üst" in pick and rate >= 60) or ("Alt" in pick and rate <= 40)
                if agrees: support += 1; notes.append("H2H gol yönünü destekliyor")
            elif market == "KG":
                rate=float(h2h_ctx["KG Var %"])
                agrees = (pick == "KG Var" and rate >= 60) or (pick == "KG Yok" and rate <= 40)
                if agrees: support += 1; notes.append("H2H KG yönünü destekliyor")

        # Conservative classification. KG remains experimental unless evidence is exceptional.
        if market == "KG":
            decision = "PAS" if support < 3 or conf < 75 else "ALTERNATİF"
        elif support >= 3 and conf >= 70 and n >= 30:
            decision = "ANA SEÇİM"
        elif support >= 1 and conf >= 62 and n >= 30:
            decision = "ALTERNATİF"
        else:
            decision = "PAS"
        rows.append({"Pazar":market,"Seçim":pick,"Model %":round(conf,1),
                     "Backtest %":hist_acc,"Backtest n":n,"Destek":support,
                     "Karar":decision,"Gerekçe":"; ".join(notes)})
    out=pd.DataFrame(rows)
    if out.empty: return out
    rank={"ANA SEÇİM":0,"ALTERNATİF":1,"PAS":2}
    out["_rank"]=out["Karar"].map(rank)
    return out.sort_values(["_rank","Destek","Model %"],ascending=[True,False,False]).drop(columns="_rank")


def match_report(pred, signals, home, away, wf_home=None, wf_away=None, h2h=None):
    candidates=[]
    for _,r in signals.iterrows():
        if r["Model Seçimi"] != "PAS" and r["Durum"] in ("GÜÇLÜ","UYGUN"):
            candidates.append((float(r["Model %"]), r["Pazar"], r["Model Seçimi"], r["Durum"]))
    candidates.sort(reverse=True)
    best=candidates[0] if candidates else None; alt=candidates[1] if len(candidates)>1 else None
    reasons=[]
    if wf_home and wf_away:
        reasons.append(f'Ağırlıklı form: {home} %{wf_home["Ağırlıklı form %"]}, {away} %{wf_away["Ağırlıklı form %"]}.')
    if h2h: reasons.append(f'Son {h2h["H2H maç"]} H2H: 2.5 Üst %{h2h["2.5 Üst %"]}, KG Var %{h2h["KG Var %"]}.')
    reasons.append(f'Beklenen gol: {home} {pred["Ev gol beklentisi"]} - {away} {pred["Dep gol beklentisi"]}.')
    return best, alt, reasons

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
@st.cache_data(show_spinner=False)
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

        dc_probs = {"1X": pred["1X"], "X2": pred["X2"], "12": pred["12"]}
        dc_pick = max(dc_probs, key=dc_probs.get)
        dc_correct = ((dc_pick == "1X" and actual_1x2 in ("1", "X")) or
                      (dc_pick == "X2" and actual_1x2 in ("X", "2")) or
                      (dc_pick == "12" and actual_1x2 in ("1", "2")))

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
            "ÇS Tahmin": dc_pick,
            "ÇS Güven": dc_probs[dc_pick],
            "ÇS Doğru": dc_correct,
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



@st.cache_data(ttl=3600)
@st.cache_data(show_spinner=False)
def run_final_decision_backtest(matches):
    """True walk-forward audit of the final decision engine.

    For every historical target match, both the Poisson prediction and the
    reliability evidence are restricted to information available before kickoff.
    No bookmaker odds are used; this measures classification hit-rate only.
    """
    finished = matches[matches["finished"] & (matches["datetime"] < datetime.now(TR_TZ))].sort_values("datetime").copy()
    base_bt_rows = []
    decision_rows = []

    for _, target in finished.iterrows():
        prior = finished[finished["datetime"] < target["datetime"]].copy()
        pred, err = prediction_model(prior, target)
        if err or pred is None:
            continue

        hg, ag = int(target["home_goals"]), int(target["away_goals"])
        actual_1x2 = "1" if hg > ag else ("X" if hg == ag else "2")
        actual_over15 = hg + ag >= 2
        actual_over25 = hg + ag >= 3
        actual_btts = hg > 0 and ag > 0
        predicted_1x2 = max(["1","X","2"], key=lambda k: pred[k])
        dc_probs = {"1X":pred["1X"], "X2":pred["X2"], "12":pred["12"]}
        dc_pick = max(dc_probs, key=dc_probs.get)
        dc_correct = ((dc_pick=="1X" and actual_1x2 in ("1","X")) or
                      (dc_pick=="X2" and actual_1x2 in ("X","2")) or
                      (dc_pick=="12" and actual_1x2 in ("1","2")))

        # Final-decision engine sees only earlier walk-forward outcomes.
        bt_prior = pd.DataFrame(base_bt_rows)
        signals = select_signals(pred)
        home, away = target["home"], target["away"]
        hhist = team_history(prior, home, target["datetime"], limit=10)
        ahist = team_history(prior, away, target["datetime"], limit=10)
        wf_h, wf_a = weighted_form(hhist, home), weighted_form(ahist, away)
        h2h, _ = h2h_stats(prior, home, away, target["datetime"])
        decisions = smart_final_decision(pred, signals, bt_prior, home, away, wf_h, wf_a, h2h)

        # V3.14: Gerçek kupon mantığıyla maç başına yalnızca TEK ANA SEÇİM.
        # Sıralama Kupon Merkezi ile aynıdır: Destek > Backtest % > Model %.
        if not decisions.empty:
            ana_pool = decisions[decisions["Karar"] == "ANA SEÇİM"].copy()
            if len(ana_pool) > 1:
                ana_pool = ana_pool.sort_values(
                    ["Destek", "Backtest %", "Model %"],
                    ascending=[False, False, False],
                    na_position="last",
                )
                keep_idx = ana_pool.index[0]
                decisions.loc[(decisions["Karar"] == "ANA SEÇİM") & (decisions.index != keep_idx), "Karar"] = "ALTERNATİF"

        for _, d in decisions.iterrows():
            if d["Karar"] not in ("ANA SEÇİM", "ALTERNATİF"):
                continue
            market, pick = d["Pazar"], d["Seçim"]
            if market == "1-X-2":
                correct = pick == actual_1x2
            elif market == "Çifte Şans":
                correct = ((pick=="1X" and actual_1x2 in ("1","X")) or
                           (pick=="X2" and actual_1x2 in ("X","2")) or
                           (pick=="12" and actual_1x2 in ("1","2")))
            elif market == "1.5 Gol":
                correct = (pick=="1.5 Üst") == actual_over15
            elif market == "2.5 Gol":
                correct = (pick=="2.5 Üst") == actual_over25
            elif market == "KG":
                correct = (pick=="KG Var") == actual_btts
            else:
                continue
            decision_rows.append({
                "Tarih":target["datetime"], "Sezon":target["season"],
                "Maç":f"{home} - {away}", "Skor":f"{hg}-{ag}",
                "Karar":d["Karar"], "Pazar":market, "Seçim":pick,
                "Model %":float(d["Model %"]), "Backtest %":d["Backtest %"],
                "Backtest n":int(d["Backtest n"]), "Destek":int(d["Destek"]),
                "Doğru":bool(correct)
            })

        # Add target outcome only AFTER decisions for this target were made.
        base_bt_rows.append({
            "Tarih":target["datetime"].strftime("%d.%m.%Y"), "Sezon":target["season"],
            "Ev":home, "Dep":away, "Skor":f"{hg}-{ag}",
            "Gerçek 1X2":actual_1x2, "Tahmin 1X2":predicted_1x2,
            "1X2 Doğru":predicted_1x2==actual_1x2, "1X2 Güven":pred[predicted_1x2],
            "ÇS Tahmin":dc_pick, "ÇS Güven":dc_probs[dc_pick], "ÇS Doğru":dc_correct,
            "1.5 Tahmin":pred["1.5 Üst"]>=50, "1.5 Güven":max(pred["1.5 Üst"],pred["1.5 Alt"]),
            "1.5 Gerçek":actual_over15, "1.5 Doğru":((pred["1.5 Üst"]>=50)==actual_over15),
            "2.5 Tahmin":pred["2.5 Üst"]>=50, "2.5 Güven":max(pred["2.5 Üst"],pred["2.5 Alt"]),
            "2.5 Gerçek":actual_over25, "2.5 Doğru":((pred["2.5 Üst"]>=50)==actual_over25),
            "KG Tahmin":pred["KG Var"]>=50, "KG Güven":max(pred["KG Var"],pred["KG Yok"]),
            "KG Gerçek":actual_btts, "KG Doğru":((pred["KG Var"]>=50)==actual_btts),
        })

    return pd.DataFrame(decision_rows)

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

st.markdown('<div class="hero"><div class="hero-title">⚽ İDDAA ANALİZ PRO</div><div class="hero-sub">Süper Lig • Doğrulanmış sinyaller + Kupon Merkezi + Kullanıcı Hesapları + Kupon Sonuçlandırma + Profesyonel Hesap Paneli + Gerçek Oranlı Kupon + Haftalık Kupon Performansı + Kupon Sonuç Audit • V3.47.7</div></div>', unsafe_allow_html=True)
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


@st.cache_data(ttl=900, show_spinner=False)
def build_coupon_candidates(upcoming, completed):
    """V3.14 coupon layer: only V3.14 final-engine ANA SEÇİM rows enter the pool.

    All completed matches are earlier than the upcoming scan window, so a single
    walk-forward backtest can be reused without looking into future outcomes.
    Context (weighted form/H2H) is recomputed as-of each fixture date.
    """
    rows = []
    if upcoming.empty or completed.empty:
        return pd.DataFrame(columns=["Tarih","Maç","Pazar","Model %","Backtest %","Backtest n","Destek","Seviye","Not"])

    bt_prior = run_backtest(completed.copy())
    for _, match in upcoming.sort_values("datetime").iterrows():
        pred, err = prediction_model(completed, match)
        if pred is None:
            continue
        home, away, before = match["home"], match["away"], match["datetime"]
        sig = select_signals(pred)
        h_all = team_history(completed, home, before, 10, "all")
        a_all = team_history(completed, away, before, 10, "all")
        wf_h = weighted_form(h_all, home) if not h_all.empty else None
        wf_a = weighted_form(a_all, away) if not a_all.empty else None
        h2h, _ = h2h_stats(completed, home, away, before, 8)
        decisions = smart_final_decision(pred, sig, bt_prior, home, away, wf_h, wf_a, h2h)
        if decisions.empty:
            continue
        ana = decisions[decisions["Karar"] == "ANA SEÇİM"].copy()
        if ana.empty:
            continue
        # One main leg per match: prevents correlated markets from the same fixture.
        r = ana.sort_values(["Destek","Backtest %","Model %"], ascending=[False,False,False]).iloc[0]
        rows.append({
            "Tarih": before,
            "Maç": f"{home} - {away}",
            "Pazar": r["Seçim"],
            "Pazar Grubu": r["Pazar"],
            "Model %": float(r["Model %"]),
            "Backtest %": float(r["Backtest %"]) if pd.notna(r["Backtest %"]) else None,
            "Backtest n": int(r["Backtest n"]),
            "Destek": int(r["Destek"]),
            "Seviye": "ANA SEÇİM",
            "Not": r["Gerekçe"],
        })
    if not rows:
        return pd.DataFrame(columns=["Tarih","Maç","Pazar","Pazar Grubu","Model %","Backtest %","Backtest n","Destek","Seviye","Not"])
    return pd.DataFrame(rows).sort_values(["Destek","Backtest %","Model %","Tarih"], ascending=[False,False,False,True]).reset_index(drop=True)


def make_coupon(candidates, mode):
    """V3.14 profiles rank only final-engine ANA SEÇİM candidates."""
    if candidates.empty:
        return candidates.copy()
    primary = candidates[candidates["Seviye"] == "ANA SEÇİM"].copy()
    if primary.empty:
        return primary
    if mode == "🛡️ Yüksek Olasılık":
        threshold, legs, min_bt = 75, 2, 75
    elif mode == "⚖️ Dengeli":
        threshold, legs, min_bt = 70, 3, 70
    else:
        threshold, legs, min_bt = 65, 4, 65
    selected = primary[(primary["Model %"] >= threshold) & (primary["Backtest %"] >= min_bt)].copy()
    return selected.sort_values(["Destek","Backtest %","Model %"], ascending=[False,False,False]).head(legs)



st.markdown("""
<style>
/* V1.9 contrast patch */
.stApp, .stApp p, .stApp li, .stApp label { color:#F4F7FB; }
.stApp h1, .stApp h2, .stApp h3 { color:#FFFFFF !important; }
[data-testid="stCaptionContainer"] p { color:#C7D2E0 !important; }
[data-testid="stMetricLabel"] p { color:#D9E2EC !important; }
[data-testid="stMetricValue"] { color:#57E6A5 !important; }
div[data-testid="stAlert"] p { color:#F5F7FA !important; }
div[data-baseweb="input"] input {
  color:#111827 !important;
  background:#F8FAFC !important;
  font-weight:700;
}
div[data-baseweb="input"] input::placeholder { color:#64748B !important; }
</style>
""", unsafe_allow_html=True)


# OddsPapi v4: key only in Streamlit Secrets; never display it.
def api_key():
    try:
        return str(st.secrets.get("ODDSPAPI_KEY", "")).strip()
    except Exception:
        return ""

@st.cache_data(ttl=3600, show_spinner=False)
def odds_papi_get(endpoint, params, key):
    import urllib.error
    query = urllib.parse.urlencode({**params, "apiKey": key})
    req = urllib.request.Request("https://api.oddspapi.io/v4/" + endpoint + "?" + query,
        headers={"Accept": "application/json", "User-Agent": "IddaaAnalizPro/1.8.6"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        # Do not leak API key in error messages or URLs.
        raise ValueError(f"OddsPapi HTTP {exc.code} (erişim veya kota kısıtı olabilir)") from None
    except urllib.error.URLError:
        raise ValueError("OddsPapi sunucusuna erişilemedi") from None


def team_token(value):
    """Canonical club ID for fixture-source and OddsPapi naming variants."""
    import re
    value = unicodedata.normalize("NFKD", str(value).casefold().replace("ı", "i"))
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    # Exact aliases only: avoid accidental substring matches between clubs.
    aliases = {
        "fenerbahce": "fenerbahce", "fenerbahce istanbul": "fenerbahce",
        "galatasaray": "galatasaray", "galatasaray istanbul": "galatasaray",
        "besiktas": "besiktas", "besiktas istanbul": "besiktas",
        "istanbul basaksehir": "basaksehir", "basaksehir": "basaksehir",
        "gaziantep": "gaziantep", "gaziantep fk": "gaziantep",
        "amedspor": "amedspor", "amed": "amedspor",
        "amed sportif faaliyetler": "amedspor",
        "corum": "corum", "corum fk": "corum", "corumspor": "corum",
        "caykur rizespor": "rizespor", "rizespor": "rizespor",
        "genclerbirligi": "genclerbirligi", "genclerbirligi sk": "genclerbirligi",
        "erzurumspor": "erzurumspor", "erzurumspor fk": "erzurumspor",
        "eyupspor": "eyupspor", "samsunspor": "samsunspor",
        "trabzonspor": "trabzonspor", "alanyaspor": "alanyaspor",
        "konyaspor": "konyaspor", "kasimpasa": "kasimpasa",
        "kasimpasa istanbul": "kasimpasa", "goztepe": "goztepe",
        "goztepe izmir": "goztepe", "kocaelispor": "kocaelispor",
        "antalyaspor": "antalyaspor", "hatayspor": "hatayspor",
        "hatayspor antakya": "hatayspor", "adana demirspor": "adanademirspor",
    }
    return aliases.get(value, value.replace(" ", ""))


def odds_papi_tournament(key):
    rows = odds_papi_get("tournaments", {"sportId": 10, "language": "en"}, key)
    if not isinstance(rows, list):
        raise ValueError("Turnuva yanıtı beklenen biçimde değil")
    matches = [r for r in rows if isinstance(r, dict)
               and str(r.get("categorySlug", "")).lower() in ("turkey", "turkiye", "türkiye")
               and (str(r.get("tournamentSlug", "")).lower() in ("super-lig", "superlig", "super-lig-turkey")
                    or str(r.get("tournamentName", "")).lower() in ("super lig", "süper lig"))]
    return matches[0].get("tournamentId") if len(matches) == 1 else None


def find_exact_fixture(item, fixtures):
    try:
        home, away = str(item["Maç"]).split(" - ", 1)
        # Coupon timestamps are Europe/Istanbul-aware; compare both sides in the same timezone.
        wanted = pd.Timestamp(item["Tarih"])
        if wanted.tzinfo is None:
            wanted = wanted.tz_localize("Europe/Istanbul")
        else:
            wanted = wanted.tz_convert("Europe/Istanbul")
        matches = []
        for obj in fixtures:
            if not isinstance(obj, dict) or str(obj.get("statusId", "0")) not in ("0", "1"):
                continue
            if (team_token(obj.get("participant1Name", "")) != team_token(home) or
                team_token(obj.get("participant2Name", "")) != team_token(away)):
                continue
            when = pd.Timestamp(obj["startTime"])
            if when.tzinfo is None:
                # OddsPapi startTime is UTC in this endpoint; make that explicit if offset is absent.
                when = when.tz_localize("UTC")
            when = when.tz_convert("Europe/Istanbul")
            if abs((when - wanted).total_seconds()) <= 10800:
                matches.append(obj.get("fixtureId"))
        return matches[0] if len(matches) == 1 else None
    except Exception:
        return None


def extract_market_odds(data, market):
    # OddsPapi bookmakerOutcomeId is a strict line+side, e.g. 1.5/over.
    target = "1.5/over" if market == "1.5 Üst" else "1.5/under" if market == "1.5 Alt" else None
    if not target or not isinstance(data, dict):
        return None
    found = []
    for bookmaker, book in data.get("bookmakerOdds", {}).items():
        if not isinstance(book, dict) or book.get("suspended") or not book.get("bookmakerIsActive", False):
            continue
        for m in book.get("markets", {}).values():
            if not isinstance(m, dict) or not m.get("marketActive", False):
                continue
            for outcome in m.get("outcomes", {}).values():
                for player in outcome.get("players", {}).values():
                    if not isinstance(player, dict) or not player.get("active", False):
                        continue
                    if str(player.get("bookmakerOutcomeId", "")).lower().strip() != target:
                        continue
                    try:
                        odd = float(player["price"])
                        if 1.01 <= odd <= 100:
                            found.append((odd, bookmaker))
                    except (ValueError, TypeError, KeyError):
                        pass
    return max(found, key=lambda x: x[0]) if found else None

def _v333_open_match_analysis(home, away, dt_iso):
    """Kupon Merkezinden seçilen maçı Maç Analizine taşır; karar motoruna dokunmaz."""
    st.session_state["v333_target_match"] = {
        "home": str(home),
        "away": str(away),
        "datetime": str(dt_iso),
    }
    st.session_state["main_menu"] = "📊 Maç Analizi"
    st.session_state.pop("v333_match_selector", None)

menu = st.radio("Bölüm seç",["🏠 Ana Sayfa","📅 Fikstür","📊 Maç Analizi","🛡️ Takım Analizi","🎟️ Kupon Merkezi","👤 Hesabım","📒 Canlı Takip","📈 Model Performansı","🧪 Backtest","⚙️ Ayarlar"],horizontal=True,key="main_menu")

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
    st.subheader("📊 Maç Analiz Merkezi • V3.47.7")
    st.caption("Tek ekranda form, saha performansı, gol eğilimleri, Poisson modeli, güven filtresi ve isteğe bağlı canlı 1.5 gol oranı.")
    if future.empty:
        st.info("Analiz için gelecekteki maç bulunamadı.")
    else:
        labels = [f'{r["home"]} - {r["away"]} | {r["datetime"].strftime("%d.%m.%Y %H:%M")}' for _,r in future.iterrows()]

        # V3.34: Kupon Merkezinden gelen maç varsa aynı maçı otomatik seç.
        default_pos = 0
        target = st.session_state.pop("v333_target_match", None)
        if target:
            target_dt = pd.to_datetime(target.get("datetime"), errors="coerce")
            for i, (_, r) in enumerate(future.iterrows()):
                same_teams = str(r["home"]) == target.get("home") and str(r["away"]) == target.get("away")
                row_dt = pd.to_datetime(r["datetime"], errors="coerce")
                same_dt = pd.notna(target_dt) and pd.notna(row_dt) and row_dt == target_dt
                if same_teams and (same_dt or pd.isna(target_dt)):
                    default_pos = i
                    break

        pos = st.selectbox(
            "Maç seç", range(len(labels)), index=default_pos,
            format_func=lambda i: labels[i], key="v333_match_selector"
        )
        selected_match = future.iloc[pos]
        match_card(selected_match)
        home, away = selected_match["home"], selected_match["away"]
        before = selected_match["datetime"]

        from match_team_bridge_v331 import render as render_match_team_bridge
        render_match_team_bridge(completed, selected_match, prediction_model)

        st.markdown("### ⚡ Hızlı görünüm")
        h5 = team_stats(team_history(completed, home, before, 5), home)
        a5 = team_stats(team_history(completed, away, before, 5), away)
        quick=[]
        for team,stats in [(home,h5),(away,a5)]:
            if stats:
                quick.append({"Takım":team,"Son 5":stats["Maç"],"G-B-M":f'{stats["G"]}-{stats["B"]}-{stats["M"]}',
                              "Gol/maç":stats["Attığı gol/maç"],"Yenen/maç":stats["Yediği gol/maç"],
                              "2.5 Üst %":stats["2.5 Üst %"],"KG Var %":stats["KG Var %"]})
        if quick: st.dataframe(pd.DataFrame(quick), hide_index=True, use_container_width=True)

        n = st.radio("Detay için son kaç maç?", [5,10], horizontal=True)
        st.caption("Tüm istatistikler yalnızca seçilen maçtan önce oynanmış ve skoru bulunan karşılaşmalardan hesaplanır.")

        # V3.14 bağlamsal veri katmanı: seçilen maçtan ÖNCEKİ veriler בלבד.
        home_hist10 = team_history(completed, home, before, 10)
        away_hist10 = team_history(completed, away, before, 10)
        wf_h = weighted_form(home_hist10, home)
        wf_a = weighted_form(away_hist10, away)
        h2h, h2h_df = h2h_stats(completed, home, away, before, limit=8)
        table_before = league_table_before(completed, before)

        st.markdown("### 🧭 V3.14 bağlamsal veri")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Ağırlıklı son form**")
            form_rows=[]
            if wf_h: form_rows.append({"Takım":home, **wf_h})
            if wf_a: form_rows.append({"Takım":away, **wf_a})
            if form_rows: st.dataframe(pd.DataFrame(form_rows), hide_index=True, use_container_width=True)
            else: st.info("Ağırlıklı form için yeterli veri yok.")
        with c2:
            st.markdown("**Maç öncesi lig konumu**")
            if not table_before.empty:
                ctx = table_before[table_before["Takım"].isin([home,away])]
                st.dataframe(ctx, hide_index=True, use_container_width=True)
            else: st.info("Lig tablosu hesaplanamadı.")

        st.markdown("**Karşılıklı geçmiş (H2H)**")
        if h2h:
            st.dataframe(pd.DataFrame([h2h]), hide_index=True, use_container_width=True)
            with st.expander("H2H maçlarını göster"):
                display_history(h2h_df)
        else:
            st.info("Bu iki takım için geçmiş H2H bulunamadı.")
        for team,venue in [(home,"home"),(away,"away")]:
            st.markdown(f"### {team}")
            overall = team_history(completed,team,before,n)
            venue_df = team_history(completed,team,before,n,venue)
            c1,c2 = st.columns(2)
            with c1:
                st.markdown(f"**Son {n} maç — genel**")
                stats = team_stats(overall,team)
                if stats: st.dataframe(pd.DataFrame([stats]),hide_index=True,use_container_width=True)
                else: st.warning("Yeterli geçmiş maç yok.")
            with c2:
                st.markdown("**İç saha**" if venue == "home" else "**Deplasman**")
                stats_v = team_stats(venue_df,team)
                if stats_v: st.dataframe(pd.DataFrame([stats_v]),hide_index=True,use_container_width=True)
                else: st.info("Bu saha türünde geçmiş maç yok.")
            with st.expander(f"{team} son maçlarını göster"):
                display_history(overall)

        st.markdown("### 🧠 Poisson model merkezi")
        pred, pred_error = prediction_model(completed, selected_match)
        if pred_error:
            st.warning(pred_error)
        else:
            c1,c2,c3 = st.columns(3)
            c1.metric("1 • Ev", f'%{pred["1"]}')
            c2.metric("X", f'%{pred["X"]}')
            c3.metric("2 • Dep", f'%{pred["2"]}')
            g1,g2 = st.columns(2)
            g1.metric(f"{home} beklenen gol", pred["Ev gol beklentisi"])
            g2.metric(f"{away} beklenen gol", pred["Dep gol beklentisi"])
            st.dataframe(prediction_table(pred), hide_index=True, use_container_width=True)
            st.write("**En olası skorlar:** " + " • ".join(f'{score} (%{prob})' for score,prob in pred["Skorlar"]))

            st.markdown("### 🚦 Güven filtresi")
            sig = select_signals(pred)
            st.dataframe(sig, hide_index=True, use_container_width=True)
            strong_count = int(sig["Durum"].isin(["GÜÇLÜ","UYGUN"]).sum())
            if strong_count == 0: st.warning("Ana filtreler güçlü sinyal bulamadı: PAS.")
            else: st.success(f"{strong_count} pazar güven filtresini geçti.")

            st.markdown("### 📝 V3.14 maç raporu")
            best, alt, report_reasons = match_report(pred, sig, home, away, wf_h, wf_a, h2h)
            if best:
                st.success(f"En güçlü pazar: {best[1]} • {best[2]} • model %{best[0]:.1f} • {best[3]}")
                if alt: st.info(f"Alternatif: {alt[1]} • {alt[2]} • model %{alt[0]:.1f}")
            else:
                st.warning("Ana filtrelerde yeterince güçlü pazar yok: PAS.")
            st.caption(" ".join(report_reasons))
            st.caption("H2H ve ağırlıklı form bağlamsal göstergedir; ana Poisson yüzdesine doğrudan eklenmez. Böylece doğrulanmamış ağırlıklarla modeli yapay olarak şişirmeyiz.")

            st.markdown("### 🧭 V3.14 Akıllı Nihai Karar Motoru")
            st.caption("Karar motoru Model % değerini değiştirmez. Seçilen maçtan önceki walk-forward backtest güvenilirliğini ana doğrulama kapısı; ağırlıklı form ve H2H'yi yalnızca destek/veto sinyali olarak kullanır.")
            prior_for_bt = completed[completed["datetime"] < before].copy()
            bt_prior = run_backtest(prior_for_bt)
            final_decisions = smart_final_decision(pred, sig, bt_prior, home, away, wf_h, wf_a, h2h)
            if final_decisions.empty:
                st.warning("Nihai karar motoru değerlendirilebilir pazar bulamadı: PAS.")
            else:
                st.dataframe(final_decisions, hide_index=True, use_container_width=True)
                ana = final_decisions[final_decisions["Karar"] == "ANA SEÇİM"]
                alt2 = final_decisions[final_decisions["Karar"] == "ALTERNATİF"]
                if not ana.empty:
                    r0=ana.iloc[0]
                    st.success(f'ANA SEÇİM: {r0["Pazar"]} • {r0["Seçim"]} • model %{r0["Model %"]} • geçmiş isabet %{r0["Backtest %"]} (n={int(r0["Backtest n"])})')
                elif not alt2.empty:
                    r0=alt2.iloc[0]
                    st.info(f'ANA SEÇİM yok. En iyi ALTERNATİF: {r0["Pazar"]} • {r0["Seçim"]} • model %{r0["Model %"]}')
                else:
                    st.warning("Tüm pazarlar: PAS. Model sinyali var olsa bile tarihsel doğrulama/bağlam yeterli değil.")
            st.caption("Backtest yüzdesi sonuç sınıflandırma isabetidir; bookmaker oranı veya kârlılık testi değildir.")

            # V3.32: mevcut V3.14 kararını değiştirmeden tek kutuda özetle.
            st.markdown("### 🎯 V3.41 Nihai Karar Özeti")
            st.caption("Bu kutu yalnızca V3.14 Nihai Karar Motorunun yukarıda ürettiği sonucu özetler; yeni karar üretmez ve eşikleri değiştirmez.")
            if final_decisions.empty:
                st.warning("⛔ PAS • Değerlendirilebilir pazar bulunamadı.")
            else:
                ana_rows = final_decisions[final_decisions["Karar"] == "ANA SEÇİM"]
                alt_rows = final_decisions[final_decisions["Karar"] == "ALTERNATİF"]
                chosen = ana_rows.iloc[0] if not ana_rows.empty else (alt_rows.iloc[0] if not alt_rows.empty else None)
                if chosen is None:
                    st.warning("⛔ PAS • V3.14 motoru bu maç için oynanabilir seçim üretmedi.")
                else:
                    karar = str(chosen["Karar"])
                    pazar = str(chosen["Pazar"])
                    secim = str(chosen["Seçim"])
                    model_pct = float(chosen["Model %"])
                    bt_pct = float(chosen["Backtest %"])
                    destek = int(chosen["Destek"])
                    bt_n = int(chosen["Backtest n"])

                    locked_odd = None
                    locked_source = None
                    try:
                        from coupon_odds_v318 import enrich_coupon
                        one = pd.DataFrame([{
                            "Tarih": before,
                            "Maç": f"{home} - {away}",
                            "Pazar": secim,
                        }])
                        one, _odd_info = enrich_coupon(one)
                        if not one.empty and pd.notna(one.iloc[0].get("Maç Önü Oran")):
                            locked_odd = float(one.iloc[0]["Maç Önü Oran"])
                            locked_source = str(one.iloc[0].get("Oran Kaynağı") or "—")
                    except Exception:
                        pass

                    if karar == "ANA SEÇİM":
                        st.success(f"✅ ANA SEÇİM • {pazar} → {secim}")
                    else:
                        st.info(f"ℹ️ ALTERNATİF • {pazar} → {secim}")
                    q1,q2,q3,q4 = st.columns(4)
                    q1.metric("Model", f"%{model_pct:.1f}")
                    q2.metric("Backtest", f"%{bt_pct:.1f}", help=f"Geçmiş örnek sayısı: {bt_n}")
                    q3.metric("Destek", str(destek))
                    q4.metric("Kilitli oran", f"{locked_odd:.3f}" if locked_odd is not None else "—")
                    if locked_odd is not None:
                        st.caption(f"🔒 Maç önü oranı daha önce kilitlenmiş: {locked_odd:.3f} • Kaynak: {locked_source}. Bu kutu oranı değiştirmez.")
                    else:
                        st.caption("Bu seçim için kilitli maç önü oranı bulunamadı. Oran uydurulmaz ve burada yeni oran kilitlenmez.")

            st.markdown("### 💹 OddsPapi • seçili maçın 1.5 gol oranı")
            st.caption("Canlı oran sorgusu isteğe bağlıdır ve API kotası kullanır. Oran yoksa değer uydurulmaz.")
            live_key = api_key()
            analysis_key = f'{home}-{away}-{before.isoformat()}'
            if not live_key:
                st.info("ODDSPAPI_KEY bulunamadı.")
            elif st.button("🔄 Bu maçın 1.5 oranını getir", key="analysis_live_odds"):
                try:
                    tournament = odds_papi_tournament(live_key)
                    if tournament is None: raise ValueError("Türkiye Süper Lig turnuvası bulunamadı")
                    utc_day = pd.Timestamp(before).tz_convert("UTC")
                    start_q = (utc_day - pd.Timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
                    end_q = (utc_day + pd.Timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
                    fixtures = odds_papi_get("fixtures", {"tournamentId": tournament, "from": start_q, "to": end_q, "language":"en", "statusId":0}, live_key)
                    probe = {"Maç":f"{home} - {away}", "Tarih":before}
                    fixture_id = find_exact_fixture(probe, fixtures if isinstance(fixtures,list) else [])
                    if not fixture_id: raise ValueError("Maç OddsPapi fikstüründe doğrulanamadı")
                    odds_data = odds_papi_get("odds", {"fixtureId":fixture_id,"oddsFormat":"decimal","language":"en"}, live_key)
                    over = extract_market_odds(odds_data,"1.5 Üst")
                    under = extract_market_odds(odds_data,"1.5 Alt")
                    st.session_state["analysis_odds"] = {"key":analysis_key,"over":over,"under":under}
                except Exception as exc:
                    st.session_state["analysis_odds"] = {"key":analysis_key,"error":str(exc)[:130]}
            live = st.session_state.get("analysis_odds",{})
            if live.get("key") == analysis_key:
                if live.get("error"): st.warning(live["error"])
                else:
                    o1,o2=st.columns(2)
                    over,under=live.get("over"),live.get("under")
                    o1.metric("1.5 Üst gerçek oran", f'{over[0]:.2f}' if over else "—")
                    o2.metric("1.5 Alt gerçek oran", f'{under[0]:.2f}' if under else "—")
                    src=[]
                    if over: src.append(f"Üst: {over[1]}")
                    if under: src.append(f"Alt: {under[1]}")
                    if src: st.caption("Kaynak • " + " • ".join(src))
                    else: st.info("Maç eşleşti ancak aktif 1.5 fiyatı bulunamadı.")

            st.info(f'Model örneklemi: ev {pred["Ev örneklem"]} maç • deplasman {pred["Dep örneklem"]} maç • lig geçmişi {pred["Lig maç"]} maç.')
            st.warning("Model yüzdeleri kalibre edilmiş kesin olasılıklar değildir; oran karşılaştırması kâr garantisi veya bahis tavsiyesi değildir.")

elif menu == "🛡️ Takım Analizi":
    from team_analysis_v330 import render as render_team_analysis
    render_team_analysis(matches, completed, current_season, future, league_table_before)

elif menu == "🎟️ Kupon Merkezi":
    st.subheader("🎟️ Kupon Merkezi • V3.47.7")
    st.markdown("""<style>
    /* V3.46 Kupon Merkezi - mobile-first presentation only */
    .coupon-kicker{font-size:.78rem;font-weight:800;letter-spacing:.08em;color:#43e39d;text-transform:uppercase;margin-bottom:.25rem}
    .coupon-title{font-size:1.28rem;font-weight:850;color:#fff;margin:.2rem 0 .8rem}
    .coupon-leg{background:linear-gradient(135deg,#10253c,#0d2035);border:1px solid #284763;border-radius:14px;padding:14px;margin:9px 0}
    .coupon-leg-top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
    .coupon-match{font-size:1rem;font-weight:800;color:#fff;line-height:1.3}
    .coupon-date{font-size:.78rem;color:#9fb1c2;margin-top:4px}
    .coupon-pick{display:inline-block;background:#0f7a5c;color:#fff;font-size:1rem;font-weight:900;padding:7px 12px;border-radius:10px;white-space:nowrap}
    .coupon-meta{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px;font-size:.8rem;color:#c9d5e0}
    .coupon-meta b{color:#fff}
    .coupon-odd{color:#43e39d!important}
    .coupon-rule{background:#0d2943;border-left:4px solid #43e39d;border-radius:10px;padding:11px 13px;margin:8px 0 14px;color:#dce8f2;font-size:.88rem}
    .coupon-note{font-size:.78rem;color:#9fb1c2;line-height:1.45}
    @media(max-width:700px){
      .coupon-title{font-size:1.12rem}
      .coupon-leg{padding:12px}
      .coupon-match{font-size:.94rem}
      .coupon-pick{font-size:.94rem;padding:6px 10px}
      div[data-testid="stMetricValue"]{font-size:1.75rem!important}
      div[data-testid="stMetricLabel"] p{font-size:.78rem!important}
      .stButton>button{min-height:44px;font-size:.9rem!important}
    }
    </style>""", unsafe_allow_html=True)
    st.caption(
        "Motor önümüzdeki 7 günün maçlarını V3.14 Nihai Karar Motorundan geçirir. Kupona yalnızca ANA SEÇİM çıkan maçlar girebilir; aynı maçtan en fazla bir pazar alınır. Motor yeterli seçim bulamazsa kuponu zorla doldurmaz."
    )

    candidates = build_coupon_candidates(next7, completed)

    mode = st.radio(
        "Kupon tipi",
        ["🛡️ Yüksek Olasılık", "⚖️ Dengeli", "🔥 Yüksek Risk"],
        horizontal=True
    )
    coupon = make_coupon(candidates, mode)

    if mode == "🛡️ Yüksek Olasılık":
        rule_text = "ANA SEÇİM • model ≥ %75 • backtest ≥ %75 • en fazla 2 ayak"
    elif mode == "⚖️ Dengeli":
        rule_text = "ANA SEÇİM • model ≥ %70 • backtest ≥ %70 • en fazla 3 ayak"
    else:
        rule_text = "ANA SEÇİM • model ≥ %65 • backtest ≥ %65 • en fazla 4 ayak • toplam risk daha yüksek"
    st.markdown(f'<div class="coupon-rule"><b>{escape(mode)}</b><br>{escape(rule_text)}</div>', unsafe_allow_html=True)

    if coupon.empty:
        st.warning("Bu hafta seçtiğin profil için yeterince güçlü doğrulanmış sinyal yok. Motor kuponu zorla doldurmadı: PAS.")
    else:
        st.markdown('<div class="coupon-kicker">Haftalık otomatik seçim</div><div class="coupon-title">🎟️ Bu Haftanın Otomatik Kuponu</div>', unsafe_allow_html=True)
        # V3.46: aynı veriyi mobilde okunaklı kartlarla sunar; seçim mantığı değişmez.
        for _, row in coupon.iterrows():
            dt = pd.to_datetime(row.get("Tarih"), errors="coerce")
            date_text = dt.strftime("%d.%m.%Y • %H:%M") if not pd.isna(dt) else "—"
            match_text = escape(str(row.get("Maç", "—")))
            pick_text = escape(str(row.get("Pazar", "—")))
            group_text = escape(str(row.get("Pazar Grubu", "—")))
            model_text = f"%{float(row.get('Model %', 0)):.1f}"
            bt_val = row.get("Backtest %")
            bt_text = "—" if pd.isna(bt_val) else f"%{float(bt_val):.1f}"
            support_text = str(int(row.get("Destek", 0)))
            st.markdown(
                f'<div class="coupon-leg"><div class="coupon-leg-top">'
                f'<div><div class="coupon-match">{match_text}</div><div class="coupon-date">📅 {date_text} • {group_text}</div></div>'
                f'<div class="coupon-pick">{pick_text}</div></div>'
                f'<div class="coupon-meta"><span>Model <b>{model_text}</b></span><span>Backtest <b>{bt_text}</b></span><span>Destek <b>{support_text}</b></span></div></div>',
                unsafe_allow_html=True
            )

        # V3.34: Kupondaki maçı tek dokunuşla ayrıntılı Maç Analizine aç.
        st.markdown("#### 🔗 Maç detayını aç")
        coupon_nav_options = list(range(len(coupon)))
        nav_i = st.selectbox(
            "Analizini açacağın maç",
            coupon_nav_options,
            format_func=lambda i: str(coupon.iloc[i].get("Maç", "—")),
            key=f"v333_coupon_match_{mode}",
        )
        nav_row = coupon.iloc[nav_i]
        nav_match = str(nav_row.get("Maç", ""))
        nav_home, nav_away = (nav_match.split(" - ", 1) + [""])[:2] if " - " in nav_match else ("", "")
        nav_dt = pd.to_datetime(nav_row.get("Tarih"), errors="coerce")
        if nav_home and nav_away and pd.notna(nav_dt):
            st.button(
                "🔎 Seçili maçı Maç Analizinde aç",
                use_container_width=True,
                key=f"v333_open_{mode}",
                on_click=_v333_open_match_analysis,
                args=(nav_home, nav_away, nav_dt.isoformat()),
            )
            st.caption("Maç Analizi açıldığında aynı maç otomatik seçilir; V3.14 Nihai Karar Motorunun kararı değişmez.")
        else:
            st.caption("Bu kupon satırı Maç Analizi ile eşleştirilemedi.")

        probs = coupon["Model %"].astype(float) / 100.0
        combined = 100.0
        for p in probs:
            combined *= p
        st.metric("Yaklaşık birleşik model olasılığı*", f"%{combined:.1f}")
        st.caption(
            "*Maçları bağımsız varsayan kaba çarpımdır; gerçek kupon kazanma olasılığı olarak garanti edilemez. "
            "Aşağıdaki bookmaker oranları model yüzdelerinden ayrıdır."
        )

        # V3.36: locked pre-match odds -> combined coupon odds -> virtual return panel.
        # Read-only: this screen NEVER creates, refreshes or overwrites a locked odd.
        total_odd = None
        stake = None
        try:
            from coupon_odds_v318 import enrich_coupon, combined_odds
            coupon, odds_info = enrich_coupon(coupon)
            st.markdown("#### 💰 Gerçek oranlı kupon")
            if odds_info.get("error"):
                st.caption(odds_info["error"])

            odds_view = coupon[["Maç", "Pazar", "Maç Önü Oran", "Oran Kaynağı"]].copy()
            odds_view["Durum"] = odds_view["Maç Önü Oran"].map(
                lambda x: "🔒 Kilitli" if pd.notna(x) and float(x) >= 1.01 else "⏳ Oran bekleniyor"
            )
            odds_view["Maç Önü Oran"] = odds_view["Maç Önü Oran"].map(
                lambda x: "—" if pd.isna(x) else f"{float(x):.3f}"
            )
            odds_view["Oran Kaynağı"] = odds_view["Oran Kaynağı"].fillna("—")
            st.dataframe(odds_view, hide_index=True, use_container_width=True)

            matched = int(odds_info.get("matched", 0))
            total_legs = int(odds_info.get("total", len(coupon)))
            total_odd = combined_odds(coupon)
            k1, k2, k3 = st.columns(3)
            k1.metric("Kupon ayağı", total_legs)
            k2.metric("Kilitli oran", f"{matched}/{total_legs}")
            k3.metric("Toplam oran", f"{total_odd:.2f}" if total_odd is not None else "—")

            if total_odd is not None:
                stake = st.number_input(
                    "Sanal kupon tutarı (TL)", min_value=10.0, max_value=100000.0,
                    value=100.0, step=10.0, key=f"v334_stake_{mode}"
                )
                gross_return = float(stake) * float(total_odd)
                gross_profit = gross_return - float(stake)
                r1, r2, r3 = st.columns(3)
                r1.metric("Sanal tutar", f"{stake:,.2f} TL")
                r2.metric("Olası brüt dönüş", f"{gross_return:,.2f} TL")
                r3.metric("Olası brüt fark", f"{gross_profit:,.2f} TL")
                st.success("Kupondaki tüm ayakların kilitli maç önü oranı bulundu; toplam oran sabit kayıtların çarpımıyla hesaplandı.")
                st.caption(
                    "Kilitli oranlar Supabase oran defterinden yalnızca okunur; bu panel oranı değiştirmez. "
                    "Brüt dönüş ve brüt fark sanal hesaptır; vergi/kesinti ve bahis kuralları dahil değildir, kâr garantisi değildir."
                )
            else:
                missing = max(total_legs - matched, 0)
                st.info(f"{matched}/{total_legs} ayakta kilitli gerçek oran bulundu. {missing} ayak daha kilitlenmeden toplam kupon oranı ve dönüş hesabı yapılmayacak.")
        except Exception as exc:
            st.warning("V3.47.7 gerçek oranlı kupon paneli geçici olarak hazırlanamadı: " + str(exc)[:160])

        # Authenticated users persist the exact coupon, including locked odds when available.
        try:
            from account_v3477 import current_user, save_coupon
            if current_user():
                save_title = st.text_input("Kupon adı (isteğe bağlı)", key=f"v317_title_{mode}")
                if st.button("💾 Bu kuponu hesabıma kaydet", key=f"v342_save_{mode}", use_container_width=True):
                    saved = save_coupon(coupon, mode, save_title, stake=stake if total_odd is not None else None, total_odds=total_odd)
                    if saved.get("_v342_duplicate"):
                        st.warning(f"Bu kupon zaten hesabında kayıtlı: {saved.get('title') or 'Kayıtlı kupon'}. İkinci kez kaydedilmedi.")
                    elif saved.get("_v342_verified"):
                        st.success("✅ Kupon hesabına kaydedildi ve Hesabım kayıtlarında doğrulandı.")
                    else:
                        st.success("Kupon kaydetme isteği tamamlandı.")
                        st.info("Kayıt doğrulaması henüz listede görünmedi; sayfa yenilendiğinde Hesabım bölümünden kontrol edebilirsin.")
                if st.button("👤 Hesabımda kayıtlı kuponları aç", key=f"v342_account_{mode}", use_container_width=True):
                    st.session_state["main_menu"] = "👤 Hesabım"
                    st.rerun()
            else:
                st.info("💾 Kuponu kalıcı kaydetmek için 👤 Hesabım bölümünden giriş yap.")
        except Exception as exc:
            st.warning("V3.21 kupon kaydı: " + str(exc)[:180])

    with st.expander("📋 Tüm uygun ANA SEÇİMLER", expanded=False):
        if candidates.empty:
            st.write("Önümüzdeki 7 günde V3.14 motorundan geçen ANA SEÇİM bulunamadı.")
        else:
            show_all = candidates.copy()
            show_all["Tarih"] = show_all["Tarih"].dt.strftime("%d.%m.%Y %H:%M")
            show_all["Model %"] = show_all["Model %"].map(lambda x: f"%{x:.1f}")
            compact_cols = [c for c in ["Tarih","Maç","Pazar","Model %","Backtest %","Destek"] if c in show_all.columns]
            st.dataframe(show_all[compact_cols], hide_index=True, use_container_width=True)

    st.warning(
        "Model olasılık üretir; garanti vermez. Backtest isabeti kârlılık değildir. "
        "Otomatik oran OddsPapi ile yalnızca doğrulanmış maç ve pazarlarda denenir; geçmiş kârlılık doğrulanmadı."
    )

    with st.expander("🧪 Gelişmiş / deneysel AL-PAS araçları", expanded=False):
        st.caption("Bu bölüm ileri düzey kontrol içindir; ana kupon ve kilitli oran sisteminden ayrıdır.")
        st.caption("OddsPapi bağlantısı isteğe bağlıdır. Oranlar yalnızca doğrulanan maç ve tam 1.5 gol pazarı için kullanılır; veri yoksa oran uydurulmaz.")
        key = api_key()
        if not key:
            st.info("Otomatik oran için Streamlit Secrets içine ODDSPAPI_KEY ekle. Şimdilik elle oran girebilirsin.")
        elif st.button("🔄 Güncel oranları sorgula (API kotası kullanır)", key="load_live_odds"):
            st.session_state["auto_odds"] = {}
            st.session_state["auto_status"] = {}
            with st.spinner("OddsPapi Süper Lig ve maç eşleşmeleri kontrol ediliyor..."):
                try:
                    tournament = odds_papi_tournament(key)
                    if tournament is None:
                        st.warning("OddsPapi hesabında Türkiye Süper Lig turnuvası bulunamadı. Oran uydurulmadı.")
                    else:
                        # Limit to coupon dates: unbounded endpoint includes old seasons (2024+).
                        if coupon.empty:
                            st.info("Kuponda maç olmadığı için oran sorgulanmadı.")
                            fixtures = []
                        else:
                            date_values = pd.to_datetime(coupon["Tarih"], dayfirst=True, errors="coerce").dropna()
                            if date_values.empty:
                                raise ValueError("Kupon maç tarihleri okunamadı")
                            start = (date_values.min() - pd.Timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
                            end = (date_values.max() + pd.Timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
                            fixtures = odds_papi_get("fixtures", {"tournamentId": tournament, "from": start, "to": end, "language": "en", "statusId": 0}, key)
                        if not isinstance(fixtures, list):
                            raise ValueError("Fikstür yanıtı beklenen biçimde değil")
                        st.session_state["odds_diag"] = {
                            "turnuva": tournament,
                            "mac_sayisi": len(fixtures),
                            "ornekler": [
                                {"Tarih (UTC)": str(f.get("startTime", ""))[:16],
                                 "Ev": f.get("participant1Name", ""),
                                 "Deplasman": f.get("participant2Name", ""),
                                 "Oran verisi işareti": f.get("hasOdds", ""),
                                 "Durum": f.get("statusId", "")}
                                for f in fixtures if isinstance(f, dict)
                            ][:80],
                        }
                        st.session_state["odds_diag"]["aralik"] = f"{start} → {end}" if not coupon.empty else "Kupon boş"
                        st.session_state["odds_diag"]["eslesme"] = []
                        for _, item in coupon.iterrows():
                            item_key = f'{item["Maç"]}|{item["Pazar"]}'
                            if item.get("Pazar Grubu", "") != "1.5 Gol":
                                st.session_state["auto_status"][item_key] = "Otomatik oran entegrasyonu şimdilik yalnızca 1.5 gol pazarı için açık."
                                continue
                            fixture = find_exact_fixture(item, fixtures)
                            if fixture is None:
                                st.session_state["auto_status"][item_key] = "2026 tarih aralığında doğrulanmış maç bulunamadı; oran yok."
                                continue
                            st.session_state["odds_diag"]["eslesme"].append(item["Maç"])
                            try:
                                odds = odds_papi_get("odds", {"fixtureId": fixture, "oddsFormat": "decimal", "language": "en"}, key)
                                match_odd = extract_market_odds(odds, item["Pazar"])
                                if match_odd:
                                    st.session_state["auto_odds"][item_key] = match_odd
                                    st.session_state["auto_status"][item_key] = "Doğrulanmış 1.5 gol oranı bulundu"
                                else:
                                    st.session_state["auto_status"][item_key] = "Maç eşleşti ancak aktif 1.5 gol fiyatı bulunamadı (hasOdds diğer pazarları da kapsar)."
                            except Exception as exc:
                                st.session_state["auto_status"][item_key] = str(exc)[:110]
                except Exception as exc:
                    st.error("OddsPapi bağlantısı: " + str(exc)[:130])
        if st.session_state.get("odds_diag"):
            with st.expander("🔎 OddsPapi tanılama – API gerçekten hangi maçları gönderiyor?", expanded=True):
                diag = st.session_state["odds_diag"]
                st.write(f"Türkiye turnuva ID: {diag['turnuva']} | API maç sayısı: {diag['mac_sayisi']}")
                st.caption("Sorgu aralığı (UTC): " + diag.get("aralik", "—"))
                st.caption("Eşleşen kupon maçları: " + (", ".join(diag.get("eslesme", [])) or "Henüz yok"))
                if diag["ornekler"]:
                    st.dataframe(pd.DataFrame(diag["ornekler"]), hide_index=True, use_container_width=True)
                    st.caption("Bu tabloda API anahtarı veya gizli bilgi bulunmaz. Ekran görüntüsünü paylaşabilirsin.")
                else:
                    st.warning("API turnuvayı buldu ancak maç listesi boş. Bu durumda isim eşleştirme değişikliği çözüm olmaz.")
        if coupon.empty:
            st.info("Önce kupon için uygun maç bulunmalı.")
        else:
            value_rows = []
            for pos, (_, item) in enumerate(coupon.iterrows(), start=1):
                item_key = f'{item["Maç"]}|{item["Pazar"]}'
                auto = st.session_state.get("auto_odds", {}).get(item_key)
                status = st.session_state.get("auto_status", {}).get(item_key)
                if auto:
                    st.success(f'{item["Maç"]} • {item["Pazar"]}: {auto[0]:.2f} ({auto[1]}) • API kaynağı')
                elif status:
                    st.caption(f'{item["Maç"]}: {status}')
                label = f'{pos}. {item["Maç"]} — {item["Pazar"]} (model %{item["Model %"]:.1f})'
                manual = st.number_input(label + " | Elle oran (0 = otomatik varsa onu kullan)",
                                         min_value=0.0, max_value=100.0, value=0.0, step=0.01,
                                         format="%.2f", key=f'odd_{mode}_{item["Maç"]}_{item["Pazar"]}')
                odd = manual if manual >= 1.01 else (auto[0] if auto else 0.0)
                if 0 < manual < 1.01:
                    st.warning("Oran en az 1,01 olmalı.")
                if odd >= 1.01:
                    prob = float(item["Model %"]) / 100
                    fair_odd = 1 / prob
                    implied = 1 / odd
                    edge_pp = (prob - implied) * 100
                    ev_pct = (prob * odd - 1) * 100

                    # V1.9 karar kuralı: yalnızca modelin zaten bağımsız testte
                    # doğrulanmış ana 1.5 pazarını değerlendir. Model yüzdesi kalibre
                    # edilmiş gerçek olasılık olmadığı için agresif eşikler kullanılır.
                    if item["Pazar"] not in ("1.5 Üst", "1.5 Alt"):
                        decision, reason = "PAS", "Ana doğrulanmış 1.5 pazarı değil"
                    elif prob < 0.65:
                        decision, reason = "PAS", "Model güveni %65 altında"
                    elif ev_pct >= 15 and edge_pp >= 7:
                        decision, reason = "AL ADAYI", "EV ≥ %15 ve model-piyasa farkı ≥ 7 puan"
                    else:
                        decision, reason = "PAS", "Value eşiği sağlanmadı"

                    value_rows.append({"Maç": item["Maç"], "Seçim": item["Pazar"],
                        "Model %": round(prob * 100, 1), "Oran": round(odd, 2),
                        "Kaynak": "Elle" if manual >= 1.01 else "OddsPapi",
                        "Adil oran*": round(fair_odd, 2), "Piyasa ima %": round(implied * 100, 1),
                        "Fark (puan)*": round(edge_pp, 1), "Teorik EV %*": round(ev_pct, 1),
                        "Karar*": decision, "Neden": reason})
            if value_rows:
                value_df = pd.DataFrame(value_rows)
                st.markdown("#### 🎯 V3.14 kararları")
                st.dataframe(value_df, hide_index=True, use_container_width=True)
                al_count = int((value_df["Karar*"] == "AL ADAYI").sum())
                pas_count = int((value_df["Karar*"] == "PAS").sum())
                c1, c2 = st.columns(2)
                c1.metric("AL adayı", al_count)
                c2.metric("PAS", pas_count)
                if al_count:
                    st.success("AL ADAYI = model ve mevcut oran V3.14 value eşiğini geçti. Bu bir bahis tavsiyesi veya kâr garantisi değildir.")
                else:
                    st.info("Bu kuponda V3.14 value eşiğini geçen seçim yok: PAS.")
                if len(value_rows) == len(coupon):
                    combined_odds = 1.0
                    for row in value_rows:
                        combined_odds *= row["Oran"]
                    st.metric("Toplam kupon oranı", f"{combined_odds:.2f}")
                    st.caption("Birleşik teorik EV gösterimi V3.14'da kaldırıldı; model yüzdeleri kalibre edilmiş kesin olasılıklar değildir.")
                else:
                    st.caption("Toplam oran için tüm seçimlerde gerçek oran bulunmalı.")
            else:
                st.info("Otomatik oran bulunamadı. OddsPapi erişimini kontrol et veya gerçek oranı elle gir.")
            st.warning("*V3.14 AL/PAS etiketi deneysel bir filtre olup geçmiş bookmaker oranlarıyla kârlılık backtestinden geçmemiştir. Model yüzdeleri kalibre edilmiş kesin olasılıklar değildir. Pozitif EV kâr garantisi değildir. "
                       "API oranı farklı bahis şirketlerinden gelebilir ve Türkiye'de erişilebilir olmayabilir. "
                       "Oranlar değişebilir; kupon birleşik hesabı bağımsızlık varsayar.")

elif menu == "👤 Hesabım":
    from account_v3477 import render_account
    render_account(matches)

elif menu == "📒 Canlı Takip":
    from tracking_v313 import render as render_tracking_v31
    st.subheader("📒 Canlı Takip Merkezi • V3.14")
    st.caption(
        "Karar motoru donduruldu. Bu ekran 13.10.2026'dan itibaren sonuçlanan maçları walk-forward mantığıyla "
        "yeniden üretir ve her maçta yalnızca tek ANA SEÇİMİ takip eder. Böylece kayıt silinse bile seçim geçmişi "
        "fikstür sonuçlarından yeniden kurulabilir."
    )

    # V3.14: Supabase test panel removed after read/write verification.


    TRACK_START = pd.Timestamp("2026-10-13 00:00:00", tz="Europe/Istanbul")

    with st.spinner("V3.14 takip defteri hazırlanıyor..."):
        tracking_bt = run_final_decision_backtest(matches)

    if tracking_bt.empty:
        settled = pd.DataFrame()
    else:
        tracking_bt = tracking_bt.copy()
        tracking_bt["Tarih"] = pd.to_datetime(tracking_bt["Tarih"], errors="coerce", utc=True).dt.tz_convert(TR_TZ)
        settled = tracking_bt[
            (tracking_bt["Karar"] == "ANA SEÇİM") &
            (tracking_bt["Tarih"] >= TRACK_START)
        ].sort_values("Tarih", ascending=False).copy()

    open_candidates = build_coupon_candidates(next7, completed)
    if not open_candidates.empty:
        open_candidates = open_candidates.copy()
        open_candidates["Durum"] = "BEKLİYOR"

    # V3.14: Kilitli Supabase oranlarını, Fixture Download'dan gelen kesin skorlarla
    # otomatik sonuçlandır. Kilitli oran asla değiştirilmez.
    try:
        from settlement_v314 import settle_locked_records
        settle_summary = settle_locked_records(completed)
        if settle_summary.get("settled", 0):
            st.success(
                f'✅ V3.14 otomatik sonuçlandırma: {settle_summary["settled"]} kayıt kapatıldı • '
                f'{settle_summary.get("wins",0)} bildi • {settle_summary.get("losses",0)} bilemedi • '
                f'Net {settle_summary.get("net",0):+.2f} TL'
            )
        elif settle_summary.get("error"):
            st.warning("V3.14 sonuçlandırma kontrolü: " + settle_summary["error"])
    except Exception as exc:
        st.warning("V3.14 sonuçlandırma modülü çalıştırılamadı: " + str(exc)[:180])

    c1, c2, c3 = st.columns(3)
    c1.metric("Sonuçlanan takip", len(settled))
    c2.metric("İsabet", f"%{100*settled['Doğru'].mean():.1f}" if len(settled) else "—")
    c3.metric("Açık sinyal", len(open_candidates))

    st.markdown("### ⏳ Açık V3.14 sinyalleri")
    if open_candidates.empty:
        st.info("Önümüzdeki 7 günde ANA SEÇİM şartlarını geçen açık maç yok.")
    else:
        show_open = open_candidates.copy()
        st.dataframe(
            show_open[["Tarih","Maç","Pazar Grubu","Pazar","Model %","Backtest %","Destek","Durum"]],
            hide_index=True, use_container_width=True
        )
        st.caption("Açık sinyaller maç sonucu gelene kadar başarı hesabına katılmaz.")

    st.markdown("### ✅ Sonuçlanan V3.14 takip kayıtları")
    if settled.empty:
        st.info("13.10.2026'dan sonra henüz sonuçlanmış V3.14 ANA SEÇİM kaydı yok. Maçlar oynandıkça burası otomatik dolacak.")
    else:
        out = settled.copy()
        out["Tarih"] = out["Tarih"].dt.strftime("%d.%m.%Y %H:%M")
        out["Sonuç"] = out["Doğru"].map({True:"✅ BİLDİ", False:"❌ BİLEMEDİ"})
        st.dataframe(
            out[["Tarih","Maç","Skor","Pazar","Seçim","Model %","Backtest %","Destek","Sonuç"]],
            hide_index=True, use_container_width=True
        )
        csv = out[["Tarih","Maç","Skor","Pazar","Seçim","Model %","Backtest %","Destek","Sonuç"]].to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ Takip kayıtlarını CSV indir", csv, "iddaa_v3_takip.csv", "text/csv")

    st.info(
        "V3.14 sınıflandırma başarısını takip eder. ROI yalnızca maç öncesi oranı CSV defterine kaydedilmiş seçimlerde hesaplanır; "
        "kayıtsız seçimlerde ROI hesaplanmaz."
    )
    render_tracking_v31(open_candidates, settled)
    from odds_auto_v312 import render as render_odds_auto_v34
    render_odds_auto_v34(open_candidates, api_key(), odds_papi_get,
                         odds_papi_tournament, find_exact_fixture)

    st.warning(
        "Bu takip sistemi bahis tavsiyesi değildir. Geçmiş isabet gelecekteki sonucu garanti etmez. "
        "Supabase bağlıysa oran kayıtları kalıcıdır; CSV yalnızca ek yedektir."
    )

elif menu == "📈 Model Performansı":
    from model_performance_v323 import render as render_model_performance
    render_model_performance(matches, run_final_decision_backtest, build_coupon_candidates, next7, completed)

elif menu == "🧪 Backtest":
    st.subheader("🧪 Çok Sezonlu Backtest • V3.14")
    st.caption(
        "Her geçmiş maç, yalnızca o maçtan daha önce oynanmış karşılaşmalar kullanılarak yeniden tahmin edilir. "
        "Bu test oran/kârlılık testi değil; modelin sonuç sınıflandırma isabetini ölçer. "
        "Önceki sezon kadroları farklı olabilir; model bunu henüz dikkate almıyor."
    )

    st.markdown("## 🧠 V3.14 Tek Nihai ANA SEÇİM Walk-Forward Doğrulaması")
    st.caption("Bu bölüm V3.14 kararlarını geçmişte yalnızca o ana kadar bilinen verilerle yeniden üretir ve her maçta en fazla TEK ANA SEÇİM sayar. Bookmaker oranı içermez; kârlılık testi değildir.")
    with st.spinner("V3.14 karar motoru geçmiş maçlarda sınanıyor..."):
        fbt = run_final_decision_backtest(completed)
    if fbt.empty:
        st.warning("V3.14 nihai karar backtesti için yeterli geçmiş veri oluşmadı.")
    else:
        ana = fbt[fbt["Karar"]=="ANA SEÇİM"].copy()
        alt = fbt[fbt["Karar"]=="ALTERNATİF"].copy()
        a1,a2,a3,a4 = st.columns(4)
        with a1: stat_box("Seçim Yapılan Maç", len(ana))
        with a2: stat_box("Tek Seçim İsabet", f'%{round(100*ana["Doğru"].mean(),1)}' if len(ana) else "-")
        with a3: stat_box("ALTERNATİF", len(alt))
        with a4: stat_box("ALT İsabet", f'%{round(100*alt["Doğru"].mean(),1)}' if len(alt) else "-")

        st.markdown("### TEK ANA SEÇİM • pazar bazında")
        if len(ana):
            by_market = ana.groupby(["Pazar","Seçim"]).agg(Maç=("Doğru","size"), **{"İsabet %":("Doğru",lambda x:round(100*x.mean(),1))}).reset_index().sort_values(["Maç","İsabet %"],ascending=False)
            st.dataframe(by_market, hide_index=True, use_container_width=True)
        else:
            st.info("Geçmişte ANA SEÇİM oluşmadı.")

        st.markdown("### TEK ANA SEÇİM • sezon bazında")
        if len(ana):
            by_season = ana.groupby("Sezon").agg(Maç=("Doğru","size"), **{"İsabet %":("Doğru",lambda x:round(100*x.mean(),1))}).reset_index()
            st.dataframe(by_season, hide_index=True, use_container_width=True)

        st.markdown("### Son V3.14 TEK ANA SEÇİMLER")
        if len(ana):
            recent_ana=ana.sort_values("Tarih",ascending=False).head(25).copy()
            recent_ana["Tarih"]=recent_ana["Tarih"].dt.strftime("%d.%m.%Y")
            recent_ana["Sonuç"]=recent_ana["Doğru"].map({True:"✅",False:"❌"})
            st.dataframe(recent_ana[["Tarih","Maç","Skor","Pazar","Seçim","Model %","Backtest %","Backtest n","Destek","Sonuç"]], hide_index=True, use_container_width=True)
        st.warning("V3.14 backtesti sınıflandırma isabetini ölçer. Geçmiş bookmaker oranları olmadan ROI/kâr sonucu çıkarılamaz. Aynı geçmiş sonuçlara bakarak eşikleri değiştirirsek overfitting riski oluşur.")

    st.divider()
    st.markdown("## Temel Poisson Backtesti")

    if not completed.empty:
        # V3.25.1: Streamlit/Arrow mobil görünümünde groupby çıktısının
        # boş hücreler halinde çizilmesini önlemek için sade Python tipleriyle
        # temiz bir gösterim DataFrame'i oluşturuyoruz. Hesaplamaya dokunmaz.
        season_series = completed.groupby("season", dropna=False).size()
        season_rows = []
        for season_name, match_count in season_series.items():
            label = "Bilinmeyen" if pd.isna(season_name) else str(season_name)
            season_rows.append({"Sezon": label, "Oynanmış Maç": int(match_count)})
        season_counts = pd.DataFrame(season_rows, columns=["Sezon", "Oynanmış Maç"])
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
st.caption("İDDAA ANALİZ PRO V3.47.7 • Maç Analiz Merkezi • Çok sezonlu backtest • Model tahminleri garanti değildir.")
