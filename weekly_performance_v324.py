"""V3.25 weekly forward-performance report.
Read-only reporting layer; does not alter decisions, odds locking or settlement.
"""
import pandas as pd
import streamlit as st

TR_TZ = "Europe/Istanbul"
TRACK_START = pd.Timestamp("2026-10-13 00:00:00", tz=TR_TZ)


def _prepare(df):
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "Tarih" not in out.columns:
        return pd.DataFrame()
    out["Tarih"] = pd.to_datetime(out["Tarih"], errors="coerce", utc=True).dt.tz_convert(TR_TZ)
    if "Karar" in out.columns:
        out = out[out["Karar"] == "ANA SEÇİM"].copy()
    return out[(out["Tarih"].notna()) & (out["Tarih"] >= TRACK_START)].copy()


def _week_start(s):
    # Turkish reporting week: Monday 00:00 -> Sunday 23:59 (Europe/Istanbul)
    local = s.dt.tz_convert(TR_TZ)
    naive = local.dt.tz_localize(None)
    monday = (naive - pd.to_timedelta(naive.dt.weekday, unit="D")).dt.normalize()
    return monday.dt.tz_localize(TR_TZ)


def render(all_ana):
    st.markdown("### 📅 Bu Haftanın Performansı • V3.25")
    st.caption(
        "Hafta Pazartesi–Pazar olarak hesaplanır. Yalnızca 13.10.2026'dan sonra gerçekten sonuçlanmış "
        "ANA SEÇİMLER rapora girer; bekleyen maçlar isabet hesabına katılmaz."
    )

    live = _prepare(all_ana)
    if live.empty or "Doğru" not in live.columns:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Bu hafta sonuçlanan", 0)
        c2.metric("Bildi", 0)
        c3.metric("Bilemedi", 0)
        c4.metric("Haftalık isabet", "—")
        st.info("Henüz bu hafta sonuçlanmış ANA SEÇİM yok. İlk maçlar bittikçe bu bölüm otomatik dolacak.")
        return

    live["Hafta başlangıcı"] = _week_start(live["Tarih"])
    live["Bildi"] = live["Doğru"].astype(bool).astype(int)

    weekly = (live.groupby("Hafta başlangıcı", as_index=False)
              .agg(Sinyal=("Doğru", "size"), Bildi=("Bildi", "sum")))
    weekly["Bilemedi"] = weekly["Sinyal"] - weekly["Bildi"]
    weekly["İsabet %"] = (100 * weekly["Bildi"] / weekly["Sinyal"]).round(1)
    weekly["Hafta bitişi"] = weekly["Hafta başlangıcı"] + pd.Timedelta(days=6)
    weekly["Hafta"] = (weekly["Hafta başlangıcı"].dt.strftime("%d.%m.%Y") + " – " +
                       weekly["Hafta bitişi"].dt.strftime("%d.%m.%Y"))
    weekly = weekly.sort_values("Hafta başlangıcı", ascending=False)

    latest = weekly.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bu hafta sonuçlanan", int(latest["Sinyal"]))
    c2.metric("Bildi", int(latest["Bildi"]))
    c3.metric("Bilemedi", int(latest["Bilemedi"]))
    c4.metric("Haftalık isabet", f"%{latest['İsabet %']:.1f}")

    st.dataframe(
        weekly[["Hafta", "Sinyal", "Bildi", "Bilemedi", "İsabet %"]],
        hide_index=True, use_container_width=True
    )

    st.markdown("#### Bu haftanın sonuçlanan seçimleri")
    current_start = latest["Hafta başlangıcı"]
    cur = live[live["Hafta başlangıcı"] == current_start].sort_values("Tarih", ascending=False).copy()
    cur["Sonuç"] = cur["Doğru"].map(lambda x: "✅ BİLDİ" if bool(x) else "❌ BİLEMEDİ")
    cur["Tarih"] = cur["Tarih"].dt.strftime("%d.%m.%Y %H:%M")
    cols = [c for c in ["Tarih", "Maç", "Pazar Grubu", "Pazar", "Model %", "Backtest %", "Destek", "Sonuç"] if c in cur.columns]
    st.dataframe(cur[cols], hide_index=True, use_container_width=True)

    st.caption(
        "Bu tablo sınıflandırma performansıdır; bookmaker kâr/ROI hesabı değildir. "
        "Finansal sonuçlar yalnızca kilitli gerçek oran ve sonuçlandırılmış kayıtlar üzerinden ayrı hesaplanmalıdır."
    )
