"""V3.13 - Kalıcı Supabase oran defteri ve otomatik sonuçlandırma."""
import io
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from storage_v310 import load_records, save_records, cloud_status, settle_records

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
    st.markdown('## 💾 V3.13 • Maç öncesi oran defteri')
    st.caption('Karar motoru değişmedi. Oran kayıtları Supabase kalıcı veritabanına yazılır; CSV ayrıca taşınabilir yedektir.')
    ok, msg = cloud_status()
    (st.success if ok else st.warning)(('☁️ ' if ok else '⚠️ ') + msg)
    # V3.13: test/diagnostic UI removed; cloud_status remains as the normal health check.
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
            
            try:
                hs, aws = [int(x) for x in str(r.get('Skor','')).split('-', 1)]
            except Exception:
                hs, aws = None, None
            outcomes[k] = {'hit': bool(r['Doğru']), 'home_score': hs, 'away_score': aws}
        try:
            changed = settle_records(outcomes)
            if changed:
                st.success('✅ V3.13: Yeni biten maç sonucu, skor ve sanal kâr/zarar Supabase’e kalıcı yazıldı.')
        except Exception as exc:
            st.warning('⚠️ V3.13 sonuç senkronizasyonu tamamlanamadı: ' + str(exc)[:180])

    records = _rows()
    if not records:
        st.warning('Henüz maç öncesi oran kaydı yok. ROI hesaplanamaz.')
        return
    df = pd.DataFrame(records)
    st.download_button('⬇️ Oran defteri CSV yedeğini indir', df[FIELDS].to_csv(index=False).encode('utf-8-sig'), 'iddaa_v31_oran_defteri.csv', mime='text/csv', key='v31_export')

    # V3.13: the database is the source of truth for settlement/ROI.
    # This survives reruns, deploys and later fixture-window changes.
    records = _rows()
    rows = []
    for record in records:
        status = str(record.get('status') or 'BEKLIYOR').upper()
        settled_flag = status in ('BILDI','BILEMEDI')
        hs, aws = record.get('home_score'), record.get('away_score')
        score = '—' if hs is None or aws is None else f'{int(hs)}-{int(aws)}'
        profit = record.get('profit_loss') if settled_flag else None
        rows.append({'Maç':record['mac'],'Seçim':record['pazar'],'Oran':record['oran'],'Kaynak':record['kaynak'],
                     'Skor':score,'Kayıt':record['kayit_zamani'],'Tutar TL':record['tutar'],
                     'Durum':'BEKLİYOR' if not settled_flag else ('BİLDİ' if status=='BILDI' else 'BİLEMEDİ'),
                     'Net TL':profit})
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
    # V3.13: açık sinyaller + kilitli oranlar + sonuçlanan kayıtlar tek performans defterinde.
    st.markdown('## 📊 V3.13 • Birleşik performans defteri')
    ledger = []
    record_map = {str(x.get('id')): x for x in records}
    if not open_candidates.empty:
        for _, r in open_candidates.iterrows():
            kickoff = pd.Timestamp(r['Tarih'])
            if kickoff.tzinfo is None:
                kickoff = kickoff.tz_localize(TZ)
            k = _key(kickoff, str(r['Maç']), str(r['Pazar']))
            rec = record_map.get(k)
            ledger.append({
                'Tarih': kickoff.strftime('%d.%m.%Y %H:%M'), 'Maç': str(r['Maç']), 'Seçim': str(r['Pazar']),
                'Model %': float(r.get('Model %',0) or 0), 'Backtest %': float(r.get('Backtest %',0) or 0),
                'Oran': None if rec is None else rec.get('oran'), 'Kaynak': '—' if rec is None else rec.get('kaynak','—'),
                'Skor': '—', 'Durum': '🔒 ORAN KİLİTLİ' if rec else '⏳ ORAN BEKLİYOR', 'Net TL': None
            })
    for rec in records:
        status = str(rec.get('status') or 'BEKLIYOR').upper()
        if status not in ('BILDI','BILEMEDI'):
            continue
        hs, aws = rec.get('home_score'), rec.get('away_score')
        ledger.append({
            'Tarih': pd.Timestamp(rec['tarih']).tz_convert(TZ).strftime('%d.%m.%Y %H:%M') if pd.Timestamp(rec['tarih']).tzinfo else pd.Timestamp(rec['tarih']).tz_localize(TZ).strftime('%d.%m.%Y %H:%M'),
            'Maç': rec['mac'], 'Seçim': rec['pazar'], 'Model %': rec.get('model_pct',0), 'Backtest %': rec.get('backtest_pct',0),
            'Oran': rec.get('oran'), 'Kaynak': rec.get('kaynak','—'),
            'Skor': '—' if hs is None or aws is None else f'{int(hs)}-{int(aws)}',
            'Durum': '✅ BİLDİ' if status=='BILDI' else '❌ BİLEMEDİ', 'Net TL': rec.get('profit_loss')
        })
    if ledger:
        ledger_df = pd.DataFrame(ledger).drop_duplicates(subset=['Tarih','Maç','Seçim'], keep='last')
        st.dataframe(ledger_df, hide_index=True, use_container_width=True)
        locked = sum(str(x).startswith('🔒') for x in ledger_df['Durum'])
        waiting = sum(str(x).startswith('⏳') for x in ledger_df['Durum'])
        finished = sum(str(x).startswith(('✅','❌')) for x in ledger_df['Durum'])
        a,b,c = st.columns(3)
        a.metric('Oranı kilitli açık', locked)
        b.metric('Oran bekleyen açık', waiting)
        c.metric('Sonuçlanan', finished)
        st.caption('Bu tablo tek bakışta sinyal → kilitli maç önü oranı → skor → sonuç → sanal net TL zincirini gösterir.')
    else:
        st.info('Birleşik performans defterinde henüz kayıt yok.')

    st.info('V3.13: Sonuç, skor ve sanal kâr/zarar Supabase’e kalıcı yazılır. Sayfa/deploy sonrası ROI Supabase kayıtlarından yeniden kurulur; kilitli maç önü oranı değiştirilmez.')
