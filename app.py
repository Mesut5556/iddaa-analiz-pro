import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import urllib.request
import json

# -------------------------------------------------
# SAYFA AYARLARI
# -------------------------------------------------
st.set_page_config(
    page_title="İDDAA ANALİZ PRO",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -------------------------------------------------
# TASARIM
# -------------------------------------------------
st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(180deg, #071426 0%, #0b1d33 100%);
        color: white;
    }

    .block-container {
        max-width: 1200px;
        padding-top: 1.2rem;
        padding-bottom: 3rem;
    }

    h1, h2, h3, p, label {
        color: white !important;
    }

    .hero {
        padding: 26px 22px;
        border-radius: 22px;
        background: linear-gradient(135deg, #102a43, #0b6b50);
        margin-bottom: 18px;
        border: 1px solid rgba(255,255,255,0.12);
    }

    .hero-title {
        font-size: 34px;
        font-weight: 900;
        margin: 0;
    }

    .hero-sub {
        color: #d8e6f3;
        font-size: 15px;
        margin-top: 7px;
    }

    .stat-card {
        background: #10253c;
        border: 1px solid rgba(255,255,255,0.10);
        padding: 18px;
        border-radius: 18px;
        text-align: center;
        margin-bottom: 10px;
    }

    .stat-number {
        color: #43e39d;
        font-size: 27px;
        font-weight: 900;
    }

    .stat-label {
        color: #d7e2ec;
        font-size: 13px;
        margin-top: 4px;
    }

    .match-card {
        background: #10253c;
        border: 1px solid rgba(255,255,255,0.10);
        padding: 18px;
        border-radius: 18px;
        margin: 10px 0;
    }

    .league {
        color: #43e39d;
        font-size: 12px;
        font-weight: 800;
    }

    .teams {
        color: white;
        font-size: 19px;
        font-weight: 800;
        margin-top: 6px;
    }

    .info {
        color: #c9d5e0;
        font-size: 13px;
        margin-top: 7px;
    }

    .live-badge {
        display: inline-block;
        background: rgba(67,227,157,0.14);
        color: #65f0b0;
        padding: 5px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 800;
    }

    div[data-testid="stButton"] button {
        width: 100%;
        min-height: 48px;
        border-radius: 14px;
        font-weight: 800;
    }

    @media (max-width: 700px) {
        .block-container {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }

        .hero {
            padding: 20px 16px;
        }

        .hero-title {
            font-size: 27px;
        }

        .teams {
            font-size: 17px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------
# AYARLAR
# -------------------------------------------------
LEAGUE_ID = "4339"
SEASON = "2026-2027"

API_URL = (
    "https://www.thesportsdb.com/api/v1/json/123/"
    f"eventsseason.php?id={LEAGUE_ID}&s={SEASON}"
)

# -------------------------------------------------
# API'DEN VERİ ÇEK
# -------------------------------------------------
@st.cache_data(ttl=1800)
def get_super_lig_matches():
    try:
        request = urllib.request.Request(
            API_URL,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

        events = data.get("events")

        if not events:
            return pd.DataFrame(), "API maç verisi döndürmedi."

        rows = []

        for event in events:
            date_text = event.get("dateEvent")
            time_text = (
                event.get("strTimeLocal")
                or event.get("strTime")
                or ""
            )

            try:
                match_date = datetime.strptime(
                    date_text,
                    "%Y-%m-%d"
                ).date()
            except Exception:
                continue

            if time_text:
                time_text = time_text[:5]
            else:
                time_text = "--:--"

            home_score = event.get("intHomeScore")
            away_score = event.get("intAwayScore")

            if home_score is not None and away_score is not None:
                score = f"{home_score} - {away_score}"
            else:
                score = "-"

            rows.append(
                {
                    "id": event.get("idEvent", ""),
                    "league": event.get(
                        "strLeague",
                        "Turkish Super Lig"
                    ),
                    "home": event.get(
                        "strHomeTeam",
                        "Bilinmiyor"
                    ),
                    "away": event.get(
                        "strAwayTeam",
                        "Bilinmiyor"
                    ),
                    "date": match_date,
                    "time": time_text,
                    "round": event.get("intRound", "-"),
                    "status": event.get("strStatus", ""),
                    "score": score,
                    "home_badge": event.get(
                        "strHomeTeamBadge",
                        ""
                    ),
                    "away_badge": event.get(
                        "strAwayTeamBadge",
                        ""
                    ),
                }
            )

        df = pd.DataFrame(rows)

        if df.empty:
            return df, "Kullanılabilir maç bulunamadı."

        df = df.sort_values(
            by=["date", "time"]
        ).reset_index(drop=True)

        return df, None

    except Exception as e:
        return pd.DataFrame(), str(e)


matches, api_error = get_super_lig_matches()

today = datetime.now().date()
end_date = today + timedelta(days=15)

if not matches.empty:
    upcoming = matches[
        (matches["date"] >= today)
        & (matches["date"] <= end_date)
    ].copy()

    future_all = matches[
        matches["date"] >= today
    ].copy()

    past_matches = matches[
        matches["date"] < today
    ].copy()

else:
    upcoming = pd.DataFrame()
    future_all = pd.DataFrame()
    past_matches = pd.DataFrame()

# -------------------------------------------------
# ÜST BÖLÜM
# -------------------------------------------------
st.markdown(
    """
    <div class="hero">
        <div class="hero-title">
            ⚽ İDDAA ANALİZ PRO
        </div>

        <div class="hero-sub">
            Gerçek futbol verisi • Türkiye Süper Lig • V1.2
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------
# API DURUMU
# -------------------------------------------------
if api_error:
    st.error(
        "⚠️ Futbol verisi şu anda alınamadı.\n\n"
        f"Teknik bilgi: {api_error}"
    )
else:
    st.success(
        "🟢 TheSportsDB bağlantısı aktif — "
        "gerçek Süper Lig verisi alındı."
    )

# -------------------------------------------------
# İSTATİSTİK KARTLARI
# -------------------------------------------------
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-number">
                {len(upcoming)}
            </div>
            <div class="stat-label">
                Önümüzdeki 15 Gün
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-number">
                {len(matches)}
            </div>
            <div class="stat-label">
                API'den Gelen Maç
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        """
        <div class="stat-card">
            <div class="stat-number">
                V1.2
            </div>
            <div class="stat-label">
                Gerçek Veri
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")

# -------------------------------------------------
# MENÜ
# -------------------------------------------------
menu = st.radio(
    "Bölüm seç",
    [
        "🏠 Ana Sayfa",
        "📅 Fikstür",
        "📊 Maç Analizi",
        "⚙️ Ayarlar"
    ],
    horizontal=True,
)

# -------------------------------------------------
# ANA SAYFA
# -------------------------------------------------
if menu == "🏠 Ana Sayfa":

    st.subheader("⚽ Yaklaşan Süper Lig Maçları")

    st.caption(
        "Bugünden itibaren önümüzdeki 15 günlük "
        "gerçek API verileri gösterilir."
    )

    if upcoming.empty:

        if not future_all.empty:
            st.info(
                "Önümüzdeki 15 gün içinde API'de kayıtlı "
                "Süper Lig maçı bulunamadı."
            )

            next_match = future_all.iloc[0]

            st.write("### Sonraki kayıtlı maç")

            st.markdown(
                f"""
                <div class="match-card">

                    <div class="league">
                        {next_match["league"]}
                    </div>

                    <div class="teams">
                        {next_match["home"]}
                        ⚔️
                        {next_match["away"]}
                    </div>

                    <div class="info">
                        📅 {next_match["date"].strftime("%d.%m.%Y")}
                        &nbsp; • &nbsp;
                        🕒 {next_match["time"]}
                    </div>

                </div>
                """,
                unsafe_allow_html=True,
            )

        else:
            st.warning(
                "API'de gelecekte oynanacak maç bulunamadı."
            )

    else:

        for _, row in upcoming.iterrows():

            st.markdown(
                f"""
                <div class="match-card">

                    <div class="league">
                        {row["league"]}
                        • Hafta {row["round"]}
                    </div>

                    <div class="teams">
                        {row["home"]}
                        ⚔️
                        {row["away"]}
                    </div>

                    <div class="info">
                        📅 {row["date"].strftime("%d.%m.%Y")}
                        &nbsp; • &nbsp;
                        🕒 {row["time"]}
                    </div>

                    <div class="info">
                        <span class="live-badge">
                            GERÇEK VERİ
                        </span>
                    </div>

                </div>
                """,
                unsafe_allow_html=True,
            )

# -------------------------------------------------
# FİKSTÜR
# -------------------------------------------------
elif menu == "📅 Fikstür":

    st.subheader("📅 Süper Lig Fikstürü")

    if matches.empty:

        st.warning("Gösterilecek maç bulunamadı.")

    else:

        display_df = matches.copy()

        display_df["Tarih"] = display_df["date"].apply(
            lambda x: x.strftime("%d.%m.%Y")
        )

        display_df = display_df[
            [
                "round",
                "Tarih",
                "time",
                "home",
                "away",
                "score"
            ]
        ]

        display_df.columns = [
            "Hafta",
            "Tarih",
            "Saat",
            "Ev Sahibi",
            "Deplasman",
            "Skor"
        ]

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )

# -------------------------------------------------
# MAÇ ANALİZİ
# -------------------------------------------------
elif menu == "📊 Maç Analizi":

    st.subheader("📊 Maç Analizi")

    if future_all.empty:

        st.info(
            "Analiz edilecek gelecek maç bulunamadı."
        )

    else:

        match_names = [
            f'{row["home"]} - {row["away"]}'
            for _, row in future_all.iterrows()
        ]

        selected = st.selectbox(
            "Maç seç",
            match_names
        )

        selected_index = match_names.index(selected)

        row = future_all.iloc[selected_index]

        st.markdown(
            f"""
            <div class="match-card">

                <div class="league">
                    {row["league"]}
                    • Hafta {row["round"]}
                </div>

                <div class="teams">
                    {row["home"]}
                    ⚔️
                    {row["away"]}
                </div>

                <div class="info">
                    📅 {row["date"].strftime("%d.%m.%Y")}
                    &nbsp; • &nbsp;
                    🕒 {row["time"]}
                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )

        st.info(
            "🧠 İstatistiksel tahmin motoru henüz aktif değil. "
            "Şu anda yalnızca gerçek maç verisini doğruluyoruz."
        )

# -------------------------------------------------
# AYARLAR
# -------------------------------------------------
else:

    st.subheader("⚙️ Ayarlar")

    st.write(
        f"**Lig:** Türkiye Süper Lig"
    )

    st.write(
        f"**Sezon:** {SEASON}"
    )

    st.write(
        f"**Lig ID:** {LEAGUE_ID}"
    )

    st.write(
        "**Veri kaynağı:** TheSportsDB"
    )

    if st.button("🔄 Veriyi Yenile"):

        st.cache_data.clear()
        st.rerun()

# -------------------------------------------------
# ALT BİLGİ
# -------------------------------------------------
st.write("")
st.divider()

st.caption(
    "İDDAA ANALİZ PRO V1.2 • "
    "Gerçek futbol verisi bağlantı testi • "
    "Tahmin motoru henüz aktif değildir."
)
