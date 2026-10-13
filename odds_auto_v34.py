"""V3.4: verified OddsPapi double-chance odds -> pre-match locked tracking ledger."""
import pandas as pd
import streamlit as st
from odds_double_chance_v33 import _double_chance_catalog, _extract

TZ = 'Europe/Istanbul'


def _key(date, match, market):
    d = pd.Timestamp(date)
    if d.tzinfo is None:
        d = d.tz_localize(TZ)
    else:
        d = d.tz_convert(TZ)
    return f'{d.isoformat()}|{match}|{market}'


def _ensure_store():
    if 'v31_records' not in st.session_state:
        st.session_state.v31_records = {}


def _prepare_context(candidates, api_key, odds_papi_get, odds_papi_tournament):
    catalog = odds_papi_get('markets', {'language': 'en'}, api_key)
    dc = _double_chance_catalog(catalog)
    if not dc:
        raise ValueError('90 dakika Çifte Şans pazarı doğrulanamadı.')
    tournament = odds_papi_tournament(api_key)
    if not tournament:
        raise ValueError('Türkiye Süper Lig turnuvası tekil eşleşmedi.')
    dates = pd.to_datetime(candidates['Tarih'], errors='coerce', utc=True)
    start = (dates.min() - pd.Timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z')
    end = (dates.max() + pd.Timedelta(days=2)).strftime('%Y-%m-%dT00:00:00Z')
    fixtures = odds_papi_get('fixtures', {'tournamentId': tournament, 'from': start,
        'to': end, 'language': 'en', 'statusId': 0}, api_key)
    if not isinstance(fixtures, list):
        raise ValueError('Fikstür yanıtı beklenen biçimde değil.')
    return dc, fixtures


def _fetch_one(row, dc, fixtures, api_key, odds_papi_get, find_exact_fixture):
    kickoff = pd.Timestamp(row['Tarih'])
    if kickoff.tzinfo is None:
        kickoff = kickoff.tz_localize(TZ)
    else:
        kickoff = kickoff.tz_convert(TZ)
    if pd.Timestamp.now(tz=TZ) >= kickoff:
        return None, 'Maç başlamış.'
    selection = str(row['Pazar'])
    if selection not in ('1X', 'X2'):
        return None, 'V3.4 otomatik kayıt şu an yalnızca 1X/X2 için açık.'
    fid = find_exact_fixture(row, fixtures)
    if not fid:
        return None, 'Takım/saat kesin eşleşmedi.'
    data = odds_papi_get('odds', {'fixtureId': fid, 'oddsFormat': 'decimal', 'language': 'en'}, api_key)
    if not isinstance(data, dict) or str(data.get('fixtureId')) != str(fid):
        return None, 'Oran yanıtındaki maç ID uyuşmadı.'
    quotes = _extract(data, dc, selection)
    if not quotes:
        return None, 'Aktif doğrulanmış fiyat bulunamadı.'
    # Highest currently active verified quote. We store bookmaker + capture time so the audit is reproducible.
    q = quotes[0]
    return {'kickoff': kickoff, 'quote': q}, None


def _lock(row, found, stake=100.0):
    _ensure_store()
    kickoff, q = found['kickoff'], found['quote']
    key = _key(kickoff, str(row['Maç']), str(row['Pazar']))
    if key in st.session_state.v31_records:
        return False, 'Zaten kilitli.'
    now = pd.Timestamp.now(tz=TZ)
    if now >= kickoff:
        return False, 'Maç başlamış.'
    st.session_state.v31_records[key] = dict(
        id=key, tarih=kickoff.isoformat(), mac=str(row['Maç']), pazar=str(row['Pazar']),
        oran=float(q['Oran']), kaynak=str(q['Kaynak']), kayit_zamani=now.isoformat(), tutar=float(stake)
    )
    return True, f"{q['Oran']:.2f} • {q['Kaynak']}"


def render(candidates, api_key, odds_papi_get, odds_papi_tournament, find_exact_fixture):
    _ensure_store()
    st.markdown('### 🤖 V3.4 • Otomatik oran kilitleme')
    st.caption('Doğrulanmış 90 dakika Çifte Şans oranını OddsPapi’den maç başlamadan alır ve oran defterine kilitler. Aynı seçim sonradan değiştirilmez. API kotası kullanılır.')
    if not api_key:
        st.warning('ODDSPAPI_KEY Streamlit Secrets içinde bulunamadı.')
        return
    if candidates is None or candidates.empty:
        st.info('Açık ANA SEÇİM yok.')
        return
    available = candidates[candidates['Pazar'].astype(str).isin(['1X','X2'])].copy()
    now = pd.Timestamp.now(tz=TZ)
    pending = []
    for idx, row in available.iterrows():
        kickoff = pd.Timestamp(row['Tarih'])
        if kickoff.tzinfo is None: kickoff = kickoff.tz_localize(TZ)
        else: kickoff = kickoff.tz_convert(TZ)
        key = _key(kickoff, str(row['Maç']), str(row['Pazar']))
        if kickoff > now and key not in st.session_state.v31_records:
            pending.append(idx)
    if not pending:
        st.success('Açık 1X/X2 seçimlerinin tamamı oran defterinde kilitli.')
        return

    labels = {i: f"{available.loc[i,'Maç']} • {available.loc[i,'Pazar']}" for i in pending}
    selected = st.selectbox('Otomatik oran alınacak seçim', pending, format_func=lambda i: labels[i], key='v34_one')
    stake = st.number_input('Sanal takip tutarı (TL)', min_value=1.0, max_value=100000.0, value=100.0, step=10.0, key='v34_stake')

    c1, c2 = st.columns(2)
    one = c1.button('🔒 Seçileni otomatik çek ve kilitle', key='v34_lock_one')
    all_btn = c2.button(f'⚡ Tüm açık 1X/X2 oranlarını kilitle ({len(pending)})', key='v34_lock_all')
    if not (one or all_btn):
        st.info(f'{len(pending)} açık 1X/X2 seçimi henüz oran defterine kilitlenmedi.')
        return
    targets = [selected] if one else pending
    try:
        with st.spinner('OddsPapi doğrulanıyor ve maç öncesi oranlar alınıyor...'):
            dc, fixtures = _prepare_context(available.loc[targets], api_key, odds_papi_get, odds_papi_tournament)
            report = []
            for idx in targets:
                row = available.loc[idx]
                found, err = _fetch_one(row, dc, fixtures, api_key, odds_papi_get, find_exact_fixture)
                if err:
                    report.append({'Maç': row['Maç'], 'Seçim': row['Pazar'], 'Durum': 'KAYDEDİLMEDİ', 'Oran/Kaynak': err})
                    continue
                ok, msg = _lock(row, found, stake)
                report.append({'Maç': row['Maç'], 'Seçim': row['Pazar'], 'Durum': 'KİLİTLENDİ' if ok else 'KAYDEDİLMEDİ', 'Oran/Kaynak': msg})
        st.dataframe(pd.DataFrame(report), hide_index=True, use_container_width=True)
        if any(r['Durum']=='KİLİTLENDİ' for r in report):
            st.success('Maç öncesi oran defterine kilitlendi. Aşağıdaki CSV yedeğini indirerek kaydı koru.')
        if any(r['Durum']=='KAYDEDİLMEDİ' for r in report):
            st.warning('Bazı seçimler güvenli eşleşme/fiyat bulunamadığı için kaydedilmedi; oran uydurulmadı.')
    except Exception as exc:
        st.error('V3.4 otomatik oran hatası: ' + str(exc)[:180])
