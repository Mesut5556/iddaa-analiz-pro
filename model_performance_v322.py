"""V3.22 forward model performance dashboard.
Read-only reporting layer. Does not alter decision, odds-lock or settlement logic.
"""
import pandas as pd
import streamlit as st

TR_TZ = "Europe/Istanbul"
TRACK_START = pd.Timestamp("2026-10-13 00:00:00", tz=TR_TZ)


def _pct(x):
    return "—" if pd.isna(x) else f"%{100*float(x):.1f}"


def render(matches, run_final_decision_backtest, build_coupon_candidates, next7, completed):
    st.subheader("📈 Model Performans Merkezi • V3.22")
    st.caption(
        "13.10.2026'dan itibaren üretilen ANA SEÇİMLERİN gerçek ileriye dönük performansını izler. "
        "Bu ekran yalnızca raporlama yapar; karar motoru, oran kilitleme ve sonuçlandırma mantığını değiştirmez."
    )

    with st.spinner("İleriye dönük performans defteri hazırlanıyor..."):
        bt = run_final_decision_backtest(matches)

    if bt is None or bt.empty:
        settled = pd.DataFrame()
    else:
        bt = bt.copy()
        bt["Tarih"] = pd.to_datetime(bt["Tarih"], errors="coerce", utc=True).dt.tz_convert(TR_TZ)
        settled = bt[(bt["Karar"] == "ANA SEÇİM") & (bt["Tarih"] >= TRACK_START)].copy()
        settled = settled.sort_values("Tarih", ascending=False)

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
    c4.metric("Canlı isabet", _pct(hit) if hit is not None else "—")

    st.markdown("### 🎯 Pazar bazında gerçek performans")
    if settled.empty:
        st.info("Henüz 13.10.2026 sonrası sonuçlanmış ANA SEÇİM yok. İlk maçlar bittikçe bu tablo otomatik dolacak.")
    else:
        group_cols = [c for c in ["Pazar Grubu", "Pazar"] if c in settled.columns]
        if group_cols:
            perf = (settled.groupby(group_cols, dropna=False)["Doğru"]
                    .agg([("Sinyal", "size"), ("Bildi", "sum"), ("İsabet", "mean")])
                    .reset_index())
            perf["Bilemedi"] = perf["Sinyal"] - perf["Bildi"]
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
