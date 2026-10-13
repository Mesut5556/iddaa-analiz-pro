import streamlit as st
import pandas as pd
from datetime import datetime

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

    .coupon {
        background: #10253c;
        border: 1px solid rgba(255,255,255,0.10);
        padding: 20px;
        border-radius: 18px;
        margin: 12px 0;
    }

    .low {
        border-left: 5px solid #43e39d;
    }

    .medium {
        border-left: 5px solid #ffbd45;
    }

    .high {
        border-left: 5px solid #ff5b69;
    }

    .badge {
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

    div[data-baseweb="select"] > div {
        border-radius: 14px;
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
# ÖRNEK VERİLER
# Gerçek futbol verileri sonraki aşamada bağlanacak.
# -------------------------------------------------
matches = pd.DataFrame(
    [
        {
            "Lig": "Türkiye Süper Lig",
            "Ev": "Galatasaray",
            "Deplasman": "Trabzonspor",
            "Tarih": "18 Ekim 2026",
            "Saat": "20:00",
            "Tahmin": "1.5 Üst",
            "Olasılık": 74,
        },
        {
            "Lig": "Türkiye Süper Lig",
            "Ev": "Fenerbahçe",
            "Deplasman": "Başakşehir",
            "Tarih": "19 Ekim 2026",
            "Saat": "20:00",
            "Tahmin": "Ev Sahibi Kaybetmez",
            "Olasılık": 71,
        },
        {
            "Lig": "Türkiye Süper Lig",
            "Ev": "Beşiktaş",
            "Deplasman": "Konyaspor",
            "Tarih": "20 Ekim 2026",
            "Saat": "20:00",
            "Tahmin": "1.5 Üst",
            "Olasılık": 68,
        },
        {
            "Lig": "İngiltere Premier Lig",
            "Ev": "Arsenal",
            "Deplasman": "Chelsea",
            "Tarih": "21 Ekim 2026",
            "Saat": "22:00",
            "Tahmin": "Karşılıklı Gol",
            "Olasılık": 66,
        },
    ]
)

# -------------------------------------------------
# ÜST BÖLÜM
# -------------------------------------------------
st.markdown(
    """
    <div class="hero">
        <div class="hero-title">⚽ İDDAA ANALİZ PRO</div>
        <div class="hero-sub">
            Mobil uyumlu futbol analiz ve kupon merkezi • V1.1 Tasarım Sürümü
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------
# İSTATİSTİK KARTLARI
# -------------------------------------------------
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-number">{len(matches)}</div>
            <div class="stat-label">Örnek Maç</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-number">{matches["Lig"].nunique()}</div>
            <div class="stat-label">Lig</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        """
        <div class="stat-card">
            <div class="stat-number">V1.1</div>
            <div class="stat-label">Sürüm</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")

# -------------------------------------------------
# ANA MENÜ
# -------------------------------------------------
menu = st.radio(
    "Bölüm seç",
    ["🏠 Ana Sayfa", "🎟️ Kupon Merkezi", "📊 Maç Analizi", "⚙️ Ayarlar"],
    horizontal=True,
)

# -------------------------------------------------
# ANA SAYFA
# -------------------------------------------------
if menu == "🏠 Ana Sayfa":

    st.subheader("📅 Örnek Maçlar")

    st.info(
        "Bu sürüm yalnızca tasarım ve kullanım testi içindir. "
        "Aşağıdaki maçlar ve tahminler gerçek zamanlı veri değildir."
    )

    for _, row in matches.iterrows():
        st.markdown(
            f"""
            <div class="match-card">
                <div class="league">{row["Lig"]}</div>
                <div class="teams">
                    {row["Ev"]} ⚔️ {row["Deplasman"]}
                </div>
                <div class="info">
                    📅 {row["Tarih"]} &nbsp; • &nbsp; 🕒 {row["Saat"]}
                </div>
                <div class="info">
                    🎯 Örnek tahmin:
                    <b>{row["Tahmin"]}</b>
                    &nbsp; • &nbsp;
                    Örnek olasılık:
                    <b>%{row["Olasılık"]}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# -------------------------------------------------
# KUPON MERKEZİ
# -------------------------------------------------
elif menu == "🎟️ Kupon Merkezi":

    st.subheader("🎟️ Kupon Merkezi")

    risk = st.selectbox(
        "Risk seviyesini seç",
        ["🟢 Düşük Risk", "🟡 Orta Risk", "🔴 Yüksek Risk"],
    )

    if risk == "🟢 Düşük Risk":
        st.markdown(
            """
            <div class="coupon low">
                <span class="badge">DÜŞÜK RİSK</span>
                <h3>Kupon A</h3>
                <p>Galatasaray – Trabzonspor → 1.5 Üst</p>
                <p>Fenerbahçe – Başakşehir → Ev Sahibi Kaybetmez</p>
                <p><b>Not:</b> Bu kupon yalnızca arayüz testi için örnektir.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    elif risk == "🟡 Orta Risk":
        st.markdown(
            """
            <div class="coupon medium">
                <span class="badge">ORTA RİSK</span>
                <h3>Kupon B</h3>
                <p>Galatasaray – Trabzonspor → 2.5 Üst</p>
                <p>Arsenal – Chelsea → Karşılıklı Gol</p>
                <p><b>Not:</b> Bu kupon yalnızca arayüz testi için örnektir.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    else:
        st.markdown(
            """
            <div class="coupon high">
                <span class="badge">YÜKSEK RİSK</span>
                <h3>Kupon C</h3>
                <p>Beşiktaş – Konyaspor → Ev Sahibi Kazanır</p>
                <p>Arsenal – Chelsea → 3.5 Üst</p>
                <p><b>Not:</b> Bu kupon yalnızca arayüz testi için örnektir.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

# -------------------------------------------------
# MAÇ ANALİZİ
# -------------------------------------------------
elif menu == "📊 Maç Analizi":

    st.subheader("📊 Maç Analizi")

    match_names = [
        f'{row["Ev"]} - {row["Deplasman"]}'
        for _, row in matches.iterrows()
    ]

    selected = st.selectbox(
        "İncelemek istediğin maçı seç",
        match_names,
    )

    selected_index = match_names.index(selected)
    row = matches.iloc[selected_index]

    st.markdown(
        f"""
        <div class="match-card">
            <div class="league">{row["Lig"]}</div>
            <div class="teams">
                {row["Ev"]} ⚔️ {row["Deplasman"]}
            </div>
            <div class="info">
                📅 {row["Tarih"]} • 🕒 {row["Saat"]}
            </div>
            <hr>
            <div class="info">
                🎯 Örnek seçim: <b>{row["Tahmin"]}</b>
            </div>
            <div class="info">
                📈 Örnek hesaplanan olasılık:
                <b>%{row["Olasılık"]}</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.progress(int(row["Olasılık"]))

    with st.expander("🔎 Bu tahmin neden seçildi?"):
        st.write(
            "Bu bölüm V1.1'de yalnızca tasarım testi amacıyla gösteriliyor."
        )
        st.write(
            "Gerçek veri aşamasında takım formu, gol ortalamaları, "
            "iç saha/deplasman performansı ve diğer istatistikler "
            "burada hesaplanacak."
        )

# -------------------------------------------------
# AYARLAR
# -------------------------------------------------
else:

    st.subheader("⚙️ Ayarlar")

    st.toggle("Mobil görünüm optimizasyonu", value=True)
    st.toggle("Olasılık yüzdelerini göster", value=True)
    st.toggle("Tahmin açıklamalarını göster", value=True)

    st.success("V1.1 tasarım ayarları aktif.")

# -------------------------------------------------
# ALT BİLGİ
# -------------------------------------------------
st.write("")
st.divider()

st.caption(
    f"İDDAA ANALİZ PRO V1.1 • "
    f"{datetime.now().strftime('%d.%m.%Y')} • "
    "Bu sürümde gerçek bahis tahmin motoru henüz aktif değildir."
)
