"""V3.9 - Kalıcı oran kaydı + açık Supabase bağlantı testi."""
import io
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from storage_v35 import load_records, save_records, cloud_status, settle_records, cloud_diagnostics

TZ = ZoneInfo('Europe/Istanbul')
FIELDS = ['id','tarih','mac','pazar','oran','kaynak','kayit_zamani','tutar']

def _key(date, match, market):
    d = pd.Timestamp(date)
    if d.tzinfo is None: d = d.tz_localize(TZ)
    return f'{d.isoformat()}|{match}|{market}'

def _init():
    load_records()

def _rows():
    _init()
    return list(st.session_state.v31_records.values())

def _restore(upload):
    frame = pd.read_csv(upload, dtype={'id':str,'tarih':str,'mac':str,'pazar':str,'kaynak':str,'kayit_zamani':str})
    if not set(FIELDS).issubset(frame.columns): raise ValueError('CSV sütunları eksik.')
    parsed = {}
    for row in frame[FIELDS].to_dict('records'):
        odd, stake = float(row['oran']), float(row['tutar'])
        when = pd.Timestamp(row['tarih'])
        recorded = pd.Timestamp(row['kayit_zamani'])
        if when.tzinfo is None or recorded.tzinfo is None or recorded >= when:
            raise ValueError('Maç tarihi ve kayıt zamanı saat dilimli olmalı; oran maçtan önce kaydedilmiş olmalı.')
        if not (1.01 <= odd <= 100 and stake > 0): raise ValueError('Oran veya tutar geçersiz.')
        expected = _key(when, str(row['mac']), str(row['pazar']))
        if row['id'] != expected: raise ValueError('CSV kayıt anahtarı uyuşmuyor.')
        parsed[expected] = {**row, 'oran':odd,'tutar':stake}
    st.session_state.v31_records.update(parsed)
    save_records(st.session_state.v31_records)
    return len(parsed)

def render(open_candidates, settled):
    _init()
    st.markdown('## 💾 V3.9 • Maç öncesi oran defteri')
    st.caption('Karar motoru değişmedi. Oran kayıtları Supabase kalıcı veritabanına yazılır; CSV ayrıca taşınabilir yedektir.')
    ok, msg = cloud_status()
    (st.success if ok else st.warning)(('☁️ ' if ok else '⚠️ ') + msg)
    with st.expander('🧪 Supabase bağlantı testi', expanded=not ok):
        d = cloud_diagnostics()
        st.write('Project URL:', '✅ bulundu' if d['url_ok'] else '❌ bulunamadı')
        st.write('Secret key:', '✅ bulundu' if d['key_found'] else '❌ bulunamadı')
        st.write('Key türü:', d['key_type'])
        if d['http_status'] is not None:
            st.write('Data API HTTP:', d['http_status'])
        if d['http_status'] is not None and 200 <= d['http_status'] < 300:
            st.success(d['message'])
        else:
            st.error(d['message'])
    uploaded = st.file_uploader('📤 Önceki oran defteri CSV dosyanı geri yükle', type=['csv'], key='v31_restore')
    if uploaded is not None and st.button('CSV kayıtlarını yükle', key='v31_restore_btn'):
        try:
            count = _restore(uploaded)
            st.success(f'{count} kayıt geri yüklendi.')
        except Exception as exc:
            st.error(f'Yüklenemedi: {exc}')

    now = pd.Timestamp.now(tz=TZ)
    if not open_candidates.empty:
        choices = []
        for _, r in open_candidates.iterrows():
            kickoff = pd.Timestamp(r['Tarih'])
            if kickoff.tzinfo is None: kickoff = kickoff.tz_localize(TZ)
            key = _key(kickoff, str(r['Maç']), str(r['Pazar']))
            if kickoff > now and key not in st.session_state.v31_records:
                choices.append((key, r, kickoff))
        if choices:
            labels = {key:f"{kickoff.strftime('%d.%m %H:%M')} • {r['Maç']} • {r['Pazar']}" for key,r,kickoff in choices}
            selected = st.selectbox('Maç öncesi oran kaydı yapılacak seçim', list(labels), format_func=lambda x:labels[x], key='v31_choice')
            odd = st.number_input('Gerçek ondalık oran (örn. 1,35)', min_value=1.01, max_value=100.0, value=1.35, step=0.01, key='v31_odd')
            source = st.text_input('Oranın alındığı kaynak (bahis şirketi)', value='', key='v31_source')
            stake = st.number_input('Sanal deneme tutarı (TL)', min_value=1.0, max_value=100000.0, value=100.0, step=10.0, key='v31_stake')
            if st.button('🔒 Maç öncesi oranı kaydet', key='v31_save'):
                key, r, kickoff = next(x for x in choices if x[0] == selected)
                at = pd.Timestamp.now(tz=TZ)
                if at >= kickoff: st.error('Maç başlamış; geriye dönük oran kaydı yapılamaz.')
                elif not source.strip(): st.error('Kaynak adı gerekli.')
                elif key in st.session_state.v31_records: st.warning('Bu seçimin oranı zaten kayıtlı; değiştirilmez.')
                else:
                    st.session_state.v31_records[key] = dict(id=key, tarih=kickoff.isoformat(), mac=str(r['Maç']), pazar=str(r['Pazar']), oran=float(odd), kaynak=source.strip(), kayit_zamani=at.isoformat(), tutar=float(stake), model_pct=float(r.get('Model %', 0) or 0), backtest_pct=float(r.get('Backtest %', 0) or 0))
                    try:
                        save_records(st.session_state.v31_records)
                        st.success('✅ Oran Supabase’e kalıcı olarak yazıldı.')
                    except Exception as exc:
                        # Yanlış başarı mesajı verme; başarısız kaydı oturumdan geri al.
                        st.session_state.v31_records.pop(key, None)
                        st.error('❌ Supabase’e yazılamadı.')
                        st.code(str(exc), language=None)
                        st.info('Bu hata mesajının ekran görüntüsünü gönder; Secret key ekranda gösterilmez.')
        else:
            st.info('Yeni oran kaydedilecek başlamamış ve kayıtsız sinyal yok.')
    else:
        st.info('Şu an açık sinyal bulunamadı.')

    # Sonuçlanan seçimleri Supabase'te de kalıcı olarak kapat.
    if not settled.empty:
        outcomes = {}
        for _, r in settled.iterrows():
            k = _key(r['Tarih'], str(r['Maç']), str(r['Seçim']))
            outcomes[k] = bool(r['Doğru'])
        settle_records(outcomes)

    records = _rows()
    if not records:
        st.warning('Henüz maç öncesi oran kaydı yok. ROI hesaplanamaz.')
        return
    df = pd.DataFrame(records)
    st.download_button('⬇️ Oran defteri CSV yedeğini indir', df[FIELDS].to_csv(index=False).encode('utf-8-sig'), 'iddaa_v31_oran_defteri.csv', mime='text/csv', key='v31_export')

    results = {}
    if not settled.empty:
        for _, r in settled.iterrows():
            # Backtest 'Seçim' and coupon 'Pazar' must match; never settle mismatched markets.
            key = _key(r['Tarih'], str(r['Maç']), str(r['Seçim']))
            results[key] = bool(r['Doğru'])
    rows = []
    for record in records:
        outcome = results.get(record['id'])
        profit = None if outcome is None else round(record['tutar']*(record['oran']-1) if outcome else -record['tutar'],2)
        rows.append({'Maç':record['mac'],'Seçim':record['pazar'],'Oran':record['oran'],'Kaynak':record['kaynak'],
                     'Kayıt':record['kayit_zamani'],'Tutar TL':record['tutar'],
                     'Durum':'BEKLİYOR' if outcome is None else ('BİLDİ' if outcome else 'BİLEMEDİ'), 'Net TL':profit})
    view = pd.DataFrame(rows)
    st.dataframe(view, hide_index=True, use_container_width=True)
    closed = view[view['Net TL'].notna()]
    if not closed.empty:
        wagered = float(closed['Tutar TL'].sum())
        pnl = float(closed['Net TL'].sum())
        c1,c2,c3,c4=st.columns(4)
        c1.metric('Sonuçlanan kayıt',len(closed))
        c2.metric('İsabet',f"%{100*(closed['Durum']=='BİLDİ').mean():.1f}")
        c3.metric('Sanal net TL',f'{pnl:+.2f}')
        c4.metric('Sanal ROI',f'%{100*pnl/wagered:+.1f}' if wagered else '—')
    else:
        st.info('Oranı kaydedilmiş maçlar sonuçlandığında sanal ROI burada hesaplanacak.')
    st.info('V3.9: Supabase bağlıysa kayıtlar deploy/restart sonrasında da korunur. CSV yedeği yine indirilebilir. Bu gerçek para yatırımı değildir; kâr garantisi yoktur.')
