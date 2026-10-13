import streamlit as st
import pandas as pd
import urllib.request
import json

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# =========================================================
# SAYFA AYARLARI
# =========================================================

st.set_page_config(
    page_title="İDDAA ANALİZ PRO",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# =========================================================
# TASARIM
# =========================================================

st.markdown(
    """
    <style>

    .stApp {
        background: linear-gradient(180deg, #071426 0%, #0b1d33 100%);
        color: white;
    }

    .block-container {
        max-width: 1200px;
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    h1, h2, h3 {
        color: white !important;
    }

    .hero {
        background: linear-gradient(135deg, #102a43, #086b50);
        padding: 25px;
        border-radius: 20px;
        margin-bottom: 20px;
    }

    .hero-title {
        font-size: 32px;
        font-weight: 900;
        color: white;
    }

    .hero-sub {
        color: #e0f2eb;
        font-size: 15px;
        margin-top: 8px;
    }

    .stat-card {
        background: #10253c;
        border-radius: 16px;
        padding: 18px 10px;
        text-align: center;
        border: 1px solid #23405b;
    }

    .stat-number {
        font-size: 28px;
        font-weight: 900;
        color: #43e39d;
    }

    .stat-label {
        color: #d7e2ec;
        font-size: 13px;
    }

    .match-card {
        background: #10253c;
        padding: 18px;
        border-radius: 16px;
        margin-bottom: 12px;
        border: 1px solid #23405b;
    }

    .badge {
        color: #43e39d;
        font-size: 12px;
        font-weight: 800;
        margin-bottom: 7px;
    }

    .teams {
        font-size: 19px;
        font-weight: 800;
        color: white;
        margin-bottom: 8px;
    }

    .match-info {
        color: #c9d5e0;
        font-size: 14px;
        margin-top: 5px;
    }

    @media (max-width: 700px) {

        .hero-title {
            font-size: 26px;
        }

        .teams {
            font-size: 16px;
        }

        .block-container {
            padding-left: 12px;
            padding-right: 12px;
        }

    }

    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# VERİ KAYNAĞI
# =========================================================

API_URL = (
    "https://fixturedownload.azurewebsites.net/"
    "feed/json/super-lig-2026"
)

TR_TIMEZONE = ZoneInfo("Europe/Istanbul")
UTC_TIMEZONE = ZoneInfo("UTC")


# =========================================================
# GERÇEK VERİLERİ ÇEK
# =========================================================

@st.cache_data(ttl=3600)
def get_matches():

    request = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=20
    ) as response:

        raw_data = json.loads(
            response.read().decode("utf-8")
        )

    if not isinstance(raw_data, list):
        raise ValueError(
            "Veri kaynağı beklenen listeyi döndürmedi."
        )

    rows = []

    for event in raw_data:

        date_text = event.get("DateUtc")

        if not date_text:
            continue

        try:

            utc_date = datetime.strptime(
                date_text,
                "%Y-%m-%d %H:%M:%SZ"
            )

            utc_date = utc_date.replace(
                tzinfo=UTC_TIMEZONE
            )

            local_date = utc_date.astimezone(
                TR_TIMEZONE
            )

        except (ValueError, TypeError):
            continue

        home = event.get("HomeTeam")
        away = event.get("AwayTeam")

        if not home or not away:
            continue

        home_score = event.get("HomeTeamScore")
        away_score = event.get("AwayTeamScore")

        finished = (
            home_score is not None
            and away_score is not None
        )

        if finished:
            score = f"{home_score} - {away_score}"
        else:
            score = "-"

        rows.append(
            {
                "id": event.get("MatchNumber"),
                "round": event.get("RoundNumber", "-"),
                "home": home,
                "away": away,
                "datetime": local_date,
                "date": local_date.date(),
                "time": local_date.strftime("%H:%M"),
                "score": score,
                "finished": finished,
                "location": event.get("Location", "")
            }
        )

    df = pd.DataFrame(rows)

    if df.empty:
        raise ValueError(
            "Kullanılabilir maç bulunamadı."
        )

    df = df.sort_values(
        "datetime"
    ).reset_index(drop=True)

    return df


# =========================================================
# VERİYİ HAZIRLA
# =========================================================

error_message = None

try:

    matches = get_matches()

except Exception as error:

    matches = pd.DataFrame()
    error_message = str(error)


now = datetime.now(TR_TIMEZONE)
today = now.date()


if not matches.empty:

    future = matches[
        (matches["datetime"] >= now)
        & (~matches["finished"])
    ].copy()

    next_7 = future[
        future["date"] <= (
            today + timedelta(days=7)
        )
    ].copy()

    next_15 = future[
        future["date"] <= (
            today + timedelta(days=15)
        )
    ].copy()

    past = matches[
        matches["finished"]
    ].copy()

else:

    future = pd.DataFrame()
    next_7 = pd.DataFrame()
    next_15 = pd.DataFrame()
    past = pd.DataFrame()


# =========================================================
# MAÇ KARTI
# =========================================================

def show_match(row):

    match_date = row["datetime"].strftime(
        "%d.%m.%Y"
    )

    stadium = row["location"]

    if not stadium:
        stadium = "Stadyum belirtilmedi"

    card_html = (
        '<div class="match-card">'
        f'<div class="badge">SÜPER LİG • HAFTA {row["round"]}</div>'
        f'<div class="teams">{row["home"]} ⚔️ {row["away"]}</div>'
        f'<div class="match-info">📅 {match_date} • 🕒 {row["time"]}</div>'
        f'<div class="match-info">🏟️ {stadium}</div>'
        f'<div class="match-info">Skor: {row["score"]}</div>'
        '</div>'
    )

    st.markdown(
        card_html,
        unsafe_allow_html=True
    )


# =========================================================
# ÜST BAŞLIK
# =========================================================

hero_html = (
    '<div class="hero">'
    '<div class="hero-title">⚽ İDDAA ANALİZ PRO</div>'
    '<div class="hero-sub">'
    'Türkiye Süper Lig • Gerçek Fikstür • V1.2.2'
    '</div>'
    '</div>'
)

st.markdown(
    hero_html,
    unsafe_allow_html=True
)


# =========================================================
# BAĞLANTI DURUMU
# =========================================================

if error_message:

    st.error(
        "🔴 Veri bağlantısı başarısız."
    )

    st.caption(
        error_message
    )

else:

    st.success(
        "🟢 Fikstür bağlantısı aktif!"
    )

    st.caption(
        "Kaynak: Fixture Download • "
        "Veriler genellikle günlük güncellenir."
    )


# =========================================================
# İSTATİSTİK KARTLARI
# =========================================================

c1, c2, c3 = st.columns(3)


with c1:

    card_7 = (
        '<div class="stat-card">'
        f'<div class="stat-number">{len(next_7)}</div>'
        '<div class="stat-label">7 Günlük Maç</div>'
        '</div>'
    )

    st.markdown(
        card_7,
        unsafe_allow_html=True
    )


with c2:

    card_15 = (
        '<div class="stat-card">'
        f'<div class="stat-number">{len(next_15)}</div>'
        '<div class="stat-label">15 Günlük Maç</div>'
        '</div>'
    )

    st.markdown(
        card_15,
        unsafe_allow_html=True
    )


with c3:

    card_season = (
        '<div class="stat-card">'
        f'<div class="stat-number">{len(matches)}</div>'
        '<div class="stat-label">Sezon Maçları</div>'
        '</div>'
    )

    st.markdown(
        card_season,
        unsafe_allow_html=True
    )


st.write("")


# =========================================================
# MENÜ
# =========================================================

menu = st.radio(
    "Bölüm seç",
    [
        "🏠 Ana Sayfa",
        "📅 Fikstür",
        "📊 Maç Analizi",
        "⚙️ Ayarlar"
    ],
    horizontal=True
)


# =========================================================
# ANA SAYFA
# =========================================================

if menu == "🏠 Ana Sayfa":

    st.subheader(
        "⚽ Önümüzdeki 15 Günün Maçları"
    )

    if next_15.empty:

        st.warning(
            "Önümüzdeki 15 gün için "
            "kayıtlı maç bulunamadı."
        )

    else:

        for _, row in next_15.iterrows():

            show_match(row)


# =========================================================
# FİKSTÜR
# =========================================================

elif menu == "📅 Fikstür":

    st.subheader(
        "📅 Türkiye Süper Lig Fikstürü"
    )

    fixture_type = st.selectbox(
        "Gösterilecek maçlar",
        [
            "Önümüzdeki 7 Gün",
            "Önümüzdeki 15 Gün",
            "Tüm Gelecek Maçlar",
            "Geçmiş Maçlar",
            "Tüm Sezon"
        ]
    )


    if fixture_type == "Önümüzdeki 7 Gün":

        selected_df = next_7

    elif fixture_type == "Önümüzdeki 15 Gün":

        selected_df = next_15

    elif fixture_type == "Tüm Gelecek Maçlar":

        selected_df = future

    elif fixture_type == "Geçmiş Maçlar":

        selected_df = past

    else:

        selected_df = matches


    if selected_df.empty:

        st.info(
            "Bu bölümde gösterilecek maç yok."
        )

    else:

        display_df = selected_df.copy()

        display_df["Tarih"] = (
            display_df["datetime"]
            .dt.strftime("%d.%m.%Y")
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


# =========================================================
# MAÇ ANALİZİ
# =========================================================

elif menu == "📊 Maç Analizi":

    st.subheader(
        "📊 Maç Analizi"
    )

    if future.empty:

        st.warning(
            "Analiz edilecek gelecek maç yok."
        )

    else:

        match_labels = []

        match_indexes = []

        for index, row in future.iterrows():

            label = (
                f'{row["home"]} - {row["away"]}'
                f' | {row["datetime"].strftime("%d.%m.%Y %H:%M")}'
            )

            match_labels.append(label)
            match_indexes.append(index)


        selected_label = st.selectbox(
            "Analiz edilecek maçı seç",
            match_labels
        )


        selected_position = match_labels.index(
            selected_label
        )

        selected_index = match_indexes[
            selected_position
        ]

        selected_match = future.loc[
            selected_index
        ]


        show_match(
            selected_match
        )


        st.info(
            "🧠 İstatistiksel tahmin motoru "
            "henüz aktif değildir."
        )

        st.write(
            "Şu anda gerçek fikstür ve maç "
            "bilgilerini doğruluyoruz."
        )


# =========================================================
# AYARLAR
# =========================================================

else:

    st.subheader(
        "⚙️ Ayarlar"
    )

    st.write(
        "**Lig:** Türkiye Süper Lig"
    )

    st.write(
        "**Sezon:** 2026–2027"
    )

    st.write(
        "**Veri kaynağı:** Fixture Download"
    )

    st.write(
        "**Saat dilimi:** Europe/Istanbul"
    )

    st.write(
        "**Otomatik veri önbelleği:** 60 dakika"
    )


    if st.button(
        "🔄 Verileri Yenile"
    ):

        st.cache_data.clear()

        st.rerun()


# =========================================================
# ALT BİLGİ
# =========================================================

st.divider()

st.caption(
    "İDDAA ANALİZ PRO V1.2.2 • "
    "Gerçek fikstür ve maç sonuçları • "
    "Tahmin motoru henüz aktif değildir."
)
