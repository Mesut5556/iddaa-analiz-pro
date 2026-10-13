import streamlit as st
import pandas as pd
from datetime import datetime

# SAYFA AYARLARI
st.set_page_config(
    page_title="İDDAA ANALİZ PRO",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# TASARIM
st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #081421, #102b38);
    color: white;
}

.block-container {
    padding-top: 1.5rem;
    max-width: 1100px;
}

h1, h2, h3 {
    color: #ffffff !important;
}

.stButton > button {
    background: #00c896;
    color: #071b20;
    border-radius: 12px;
    border: none;
    font-weight: bold;
    padding: 12px;
    width: 100%;
}

.stButton > button:hover {
    background: #00e6ac;
    color: black;
}

div[data-testid="stMetric"] {
    background: #142d3c;
    border-radius: 15px;
    padding: 15px;
    border: 1px solid #235064;
}

.match-card {
    background: #142d3c;
    padding: 18px;
    border-radius: 15px;
    margin-bottom: 12px;
    border-left: 4px solid #00c896;
}

.notice {
    background: #493b19;
    padding: 12px;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

# BAŞLIK
st.title("⚽ İDDAA ANALİZ PRO")
st.caption("Akıllı Futbol Analiz ve Kupon Merkezi")

st.warning(
    "🧪 DEMO SÜRÜMÜ: Maçlar ve olasılıklar örnektir. "
    "Gerçek bahis tahmini değildir."
)

# ÖRNEK VERİLER
matches = [
    {
        "Lig": "Süper Lig",
        "Maç": "Galatasaray - Trabzonspor",
        "Tahmin": "1X",
        "Olasılık": 78,
        "Risk": "Düşük"
    },
    {
        "Lig": "Süper Lig",
        "Maç": "Fenerbahçe - Antalyaspor",
        "Tahmin": "1.5 Üst",
        "Olasılık": 81,
        "Risk": "Düşük"
    },
    {
        "Lig": "Süper Lig",
        "Maç": "Beşiktaş - Konyaspor",
        "Tahmin": "KG Var",
        "Olasılık": 67,
        "Risk": "Orta"
    },
    {
        "Lig": "1. Lig",
        "Maç": "Sakaryaspor - Erzurumspor",
        "Tahmin": "2.5 Üst",
        "Olasılık": 59,
        "Risk": "Yüksek"
    },
    {
        "Lig": "1. Lig",
        "Maç": "Boluspor - Pendikspor",
        "Tahmin": "MS1",
        "Olasılık": 64,
        "Risk": "Orta"
    },
    {
        "Lig": "1. Lig",
        "Maç": "Çorum FK - Bandırmaspor",
        "Tahmin": "KG Var",
        "Olasılık": 56,
        "Risk": "Yüksek"
    }
]

df = pd.DataFrame(matches)

# ÜST BİLGİLER
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("⚽ Maç", len(df))

with col2:
    st.metric("🏆 Lig", df["Lig"].nunique())

with col3:
    st.metric(
        "📊 Ortalama",
        f"%{df['Olasılık'].mean():.0f}"
    )

st.divider()

# MENÜ
menu = st.radio(
    "Menü",
    [
        "🏠 Ana Sayfa",
        "🎟️ Kupon Merkezi",
        "📊 Maç Analizi",
        "⚙️ Ayarlar"
    ],
    horizontal=True
)

# ANA SAYFA
if menu == "🏠 Ana Sayfa":

    st.header("📅 Haftanın Maçları")

    lig = st.selectbox(
        "Lig seç",
        ["Tüm Ligler", "Süper Lig", "1. Lig"]
    )

    if lig == "Tüm Ligler":
        filtered = df
    else:
        filtered = df[df["Lig"] == lig]

    for _, row in filtered.iterrows():

        st.markdown(
            f"""
            <div class="match-card">
                <small>{row['Lig']}</small>
                <h3>{row['Maç']}</h3>
                <p>🎯 Tahmin: {row['Tahmin']}</p>
                <p>📊 Örnek olasılık: %{row['Olasılık']}</p>
                <p>⚠️ Risk: {row['Risk']}</p>
            </div>
            """,
            unsafe_allow_html=True
        )

# KUPON MERKEZİ
elif menu == "🎟️ Kupon Merkezi":

    st.header("🎟️ Akıllı Kupon Merkezi")

    risk = st.selectbox(
        "Kupon türünü seç",
        [
            "🟢 Yüksek Olasılık",
            "🟡 Dengeli",
            "🔴 Yüksek Risk"
        ]
    )

    if risk == "🟢 Yüksek Olasılık":
        selected = df.nlargest(2, "Olasılık")

    elif risk == "🟡 Dengeli":
        selected = df[
            df["Risk"].isin(["Düşük", "Orta"])
        ].nlargest(3, "Olasılık")

    else:
        selected = df.nlargest(5, "Olasılık")

    if st.button("🎯 KUPON OLUŞTUR"):

        st.success("Kupon hazırlandı!")

        for _, row in selected.iterrows():
            st.markdown(
                f"**{row['Maç']}**  \n"
                f"Tahmin: {row['Tahmin']} | "
                f"Örnek olasılık: %{row['Olasılık']}"
            )

        combined = 1.0

        for probability in selected["Olasılık"]:
            combined *= probability / 100

        st.metric(
            "Birleşik örnek olasılık",
            f"%{combined * 100:.1f}"
        )

        st.caption(
            "Bu hesap bağımsız olay varsayımına dayanır. "
            "Gerçek maçlar için doğrulanmış tahmin değildir."
        )

# MAÇ ANALİZİ
elif menu == "📊 Maç Analizi":

    st.header("📊 Maç Analiz Merkezi")

    selected_match = st.selectbox(
        "Analiz edilecek maç",
        df["Maç"].tolist()
    )

    match = df[df["Maç"] == selected_match].iloc[0]

    st.subheader(match["Maç"])

    st.write("Lig:", match["Lig"])
    st.write("Örnek tahmin:", match["Tahmin"])

    st.progress(match["Olasılık"] / 100)

    st.metric(
        "Örnek olasılık",
        f"%{match['Olasılık']}"
    )

    st.info(
        "Gerçek istatistik motoru sonraki sürümde eklenecek."
    )

# AYARLAR
elif menu == "⚙️ Ayarlar":

    st.header("⚙️ Sistem Ayarları")

    st.checkbox("Süper Lig", value=True)
    st.checkbox("1. Lig", value=True)

    st.selectbox(
        "Analiz dönemi",
        ["7 Gün", "15 Gün"]
    )

    if st.button("🔄 Analizi Yenile"):
        st.rerun()

    st.info(
        "Bu demo sürümünde yenileme işlemi "
        "örnek verileri yeniden gösterir."
    )

st.divider()

st.caption(
    f"İDDAA ANALİZ PRO V1.0 | "
    f"{datetime.now().year} | Demo sürümü"
)
