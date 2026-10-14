"""V3.23 forward model performance dashboard.
Read-only reporting layer. Adds historical backtest vs live forward comparison.
Does not alter decision, odds-lock, coupon or settlement logic.
"""
import pandas as pd
import streamlit as st

TR_TZ = "Europe/Istanbul"
TRACK_START = pd.Timestamp("2026-10-13 00:00:00", tz=TR_TZ)


def _pct_ratio(x):
    return "—" if x is None or pd.isna(x) else f"%{100*float(x):.1f}"


def _normalize_bt(bt):
    if bt is None or bt.empty:
        return pd.DataFrame()
    out = bt.copy()
    out["Tarih"] = pd.to_datetime(out["Tarih"], errors="coerce", utc=True).dt.tz_convert(TR_TZ)
    return out[out["Karar"] == "ANA SEÇİM"].copy()


def _summary(df, group_cols):
    if df is None or df.empty or "Doğru" not in df.columns:
        return pd.DataFrame()
    g = (df.groupby(group_cols, dropna=False)["Doğru"]
         .agg([("Sinyal", "size"), ("Bildi", "sum"), ("İsabet", "mean")])
         .reset_index())
    g["Bilemedi"] = g["Sinyal"] - g["Bildi"]
    return g


def render(matches, run_final_decision_backtest, build_coupon_candidates, next7, completed):
    st.subheader("📈 Model Performans Merkezi • V3.23")
    st.caption(
        "13.10.2026'dan itibaren üretilen ANA SEÇİMLERİN gerçek ileriye dönük performansını izler. "
        "V3.23 ayrıca takip başlangıcından ÖNCEKİ walk-forward backtest ile canlı sonuçları yan yana gösterir. "
        "Bu ekran yalnızca raporlama yapar; karar motoru, oran kilitleme ve sonuçlandırma mantığını değiştirmez."
    )

    with st.spinner("Model performans defteri hazırlanıyor..."):
        all_ana = _normalize_bt(run_final_decision_backtest(matches))

    if all_ana.empty:
        historical = pd.DataFrame()
        settled = pd.DataFrame()
    else:
        historical = all_ana[all_ana["Tarih"] < TRACK_START].copy()
        settled = all_ana[all_ana["Tarih"] >= TRACK_START].copy().sort_values("Tarih", ascending=False)

    open_df = build_coupon_candidates(next7, completed)
    if open_df is None:
        open_df = pd.DataFrame()

    total_settled = len(settled)
    wins = int(settled["Doğru"].astype(bool).sum()) if total_settled and "Doğru" in settled else 0
    losses = total_settled - wins
    hit = wins / total_settled if total_settled else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sonuçlanan sinyal", total_settled)
    c2.metric("Bildi", wins)
    c3.metric("Bilemedi", losses)
    c4.metric("Canlı isabet", _pct_ratio(hit))

    st.markdown("### ⚖️ Backtest ↔ gerçek canlı karşılaştırması")
    st.caption(
        "Backtest sütunu yalnızca 13.10.2026'dan ÖNCEKİ ANA SEÇİMLERDEN hesaplanır. "
        "Canlı sütunu ise takip başlangıcından sonraki sonuçlanmış seçimlerdir; bekleyen maçlar hesaba katılmaz."
    )

    group_cols = [c for c in ["Pazar Grubu", "Pazar"] if c in all_ana.columns] if not all_ana.empty else []
    if not group_cols:
        st.info("Karşılaştırma için yeterli pazar alanı bulunamadı.")
    else:
        hist = _summary(historical, group_cols)
        live = _summary(settled, group_cols)
        if hist.empty:
            st.info("Takip başlangıcından önce karşılaştırılabilir ANA SEÇİM backtest kaydı bulunamadı.")
        else:
            hist = hist[group_cols + ["Sinyal", "İsabet"]].rename(columns={"Sinyal":"Backtest n", "İsabet":"Backtest oran"})
            if live.empty:
                comp = hist.copy()
                comp["Canlı n"] = 0
                comp["Canlı oran"] = pd.NA
            else:
                live = live[group_cols + ["Sinyal", "İsabet"]].rename(columns={"Sinyal":"Canlı n", "İsabet":"Canlı oran"})
                comp = hist.merge(live, on=group_cols, how="outer")
                comp["Backtest n"] = comp["Backtest n"].fillna(0).astype(int)
                comp["Canlı n"] = comp["Canlı n"].fillna(0).astype(int)
            comp["Backtest %"] = (100 * pd.to_numeric(comp["Backtest oran"], errors="coerce")).round(1)
            comp["Canlı %"] = (100 * pd.to_numeric(comp["Canlı oran"], errors="coerce")).round(1)
            comp["Fark (puan)"] = (comp["Canlı %"] - comp["Backtest %"]).round(1)
            show = comp[group_cols + ["Backtest n", "Backtest %", "Canlı n", "Canlı %", "Fark (puan)"]]
            show = show.sort_values(["Backtest n", "Backtest %"], ascending=[False, False])
            st.dataframe(show, hide_index=True, use_container_width=True)
            if settled.empty:
                st.info("Canlı sonuç henüz yok. İlk takip maçları bittikten sonra Canlı % ve Fark sütunları otomatik oluşacak.")
            elif len(settled) < 30:
                st.warning("Canlı örneklem henüz küçük. Backtest ile farkı erken dönemde model üstünlüğü veya bozulması olarak yorumlamamak gerekir.")

    st.markdown("### 🎯 Pazar bazında gerçek performans")
    if settled.empty:
        st.info("Henüz 13.10.2026 sonrası sonuçlanmış ANA SEÇİM yok. İlk maçlar bittikçe bu tablo otomatik dolacak.")
    else:
        perf = _summary(settled, group_cols)
        if not perf.empty:
            perf["İsabet %"] = (100 * perf["İsabet"]).round(1)
            perf = perf.drop(columns=["İsabet"]).sort_values(["İsabet %", "Sinyal"], ascending=[False, False])
            st.dataframe(perf, hide_index=True, use_container_width=True)

        st.markdown("### 🧾 Sonuçlanan gerçek sinyaller")
        cols = [c for c in ["Tarih","Maç","Pazar Grubu","Pazar","Model %","Backtest %","Destek","Doğru"] if c in settled.columns]
        detail = settled[cols].copy()
        if "Doğru" in detail:
            detail["Sonuç"] = detail["Doğru"].map(lambda x: "✅ BİLDİ" if bool(x) else "❌ BİLEMEDİ")
            detail = detail.drop(columns=["Doğru"])
        st.dataframe(detail, hide_index=True, use_container_width=True)

    st.markdown("### ⏳ Henüz sonuçlanmayan ANA SEÇİMLER")
    if open_df.empty:
        st.info("Şu anda önümüzdeki 7 günde açık ANA SEÇİM yok.")
    else:
        cols = [c for c in ["Tarih","Maç","Pazar Grubu","Pazar","Model %","Backtest %","Destek"] if c in open_df.columns]
        pending = open_df[cols].copy()
        pending["Durum"] = "⏳ BEKLİYOR"
        st.dataframe(pending, hide_index=True, use_container_width=True)

    st.info(
        "Bu bölüm backtest sonucunu canlı başarı gibi göstermez. Canlı isabet yalnızca takip başlangıcından sonra "
        "gerçekten sonuçlanmış ANA SEÇİMLERDEN hesaplanır. Açık maçlar başarı oranına katılmaz."
    )
