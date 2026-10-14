"""V3.9.5: One-match, read-only OddsPapi double-chance verification."""
import pandas as pd
import streamlit as st


def _normal(s):
    return ' '.join(str(s).casefold().replace('-', ' ').split())


def _double_chance_catalog(catalog):
    result = {}
    for market in catalog if isinstance(catalog, list) else []:
        if not isinstance(market, dict) or str(market.get('sportId')) != '10':
            continue
        name = _normal(market.get('marketName', ''))
        typ = _normal(market.get('marketType', ''))
        period = _normal(market.get('period', ''))
        # Restrict to explicitly identified double chance, 90-minute markets.
        if not ('double chance' in name or 'doublechance' in typ or 'double chance' in typ):
            continue
        if period not in ('fulltime', 'full time', 'regular time', '90 minutes'):
            continue
        outcomes = {}
        for o in market.get('outcomes', []):
            if not isinstance(o, dict):
                continue
            label = str(o.get('outcomeName', '')).upper().replace(' ', '').replace('-', '').replace('/', '')
            if label in ('1X', 'X1', 'HOMEORDRAW', 'HOMEDRAW'):
                outcomes[str(o.get('outcomeId'))] = '1X'
            elif label in ('X2', '2X', 'DRAWORAWAY', 'DRAWAWAY'):
                outcomes[str(o.get('outcomeId'))] = 'X2'
        if outcomes:
            result[str(market.get('marketId'))] = {'name': market.get('marketName'), 'outcomes': outcomes}
    return result


def _extract(odds, markets, selection):
    quotes = []
    for bookname, book in (odds.get('bookmakerOdds') or {}).items():
        if not isinstance(book, dict) or book.get('suspended') or book.get('bookmakerIsActive') is not True:
            continue
        for mid, market in (book.get('markets') or {}).items():
            if str(mid) not in markets or not isinstance(market, dict) or market.get('marketActive') is not True:
                continue
            allowed = markets[str(mid)]['outcomes']
            for oid, outcome in (market.get('outcomes') or {}).items():
                if allowed.get(str(oid)) != selection or not isinstance(outcome, dict):
                    continue
                for player in (outcome.get('players') or {}).values():
                    if not isinstance(player, dict) or player.get('active') is not True:
                        continue
                    try:
                        price = float(player['price'])
                    except (TypeError, ValueError, KeyError):
                        continue
                    if 1.01 <= price <= 100:
                        quotes.append({'Kaynak': str(bookname), 'Oran': price,
                                       'Pazar': markets[str(mid)]['name'],
                                       'Pazar ID': str(mid), 'Sonuç ID': str(oid),
                                       'Güncelleme': str(player.get('changedAt') or '')})
    return sorted(quotes, key=lambda r: r['Oran'], reverse=True)


def render(candidates, api_key, odds_papi_get, odds_papi_tournament, find_exact_fixture):
    st.markdown('### 🔎 V3.9.5 • Çifte Şans otomatik oran testi')
    st.caption('Yalnızca seçtiğin TEK maç için, düğmeye basınca OddsPapi sorgulanır. Oranlar otomatik kaydedilmez; önce pazar eşleşmesini doğruluyoruz. API kotası kullanılır.')
    if not api_key:
        st.warning('ODDSPAPI_KEY Streamlit Secrets içinde bulunamadı.')
        return
    if candidates is None or candidates.empty:
        st.info('Test edilecek açık sinyal yok.')
        return
    available = candidates[candidates['Pazar'].astype(str).isin(['1X', 'X2'])].copy()
    if available.empty:
        st.info('Şu anda 1X veya X2 seçimi yok.')
        return
    options = list(available.index)
    idx = st.selectbox('Test maçı', options, format_func=lambda i: f"{available.loc[i, 'Maç']} • {available.loc[i, 'Pazar']}", key='v33_test_match')
    if not st.button('🔍 Seçili maçın 1X/X2 oranını test et', key='v33_test_button'):
        return
    row = available.loc[idx]
    kickoff = pd.Timestamp(row['Tarih'])
    if kickoff.tzinfo is None:
        kickoff = kickoff.tz_localize('Europe/Istanbul')
    else:
        kickoff = kickoff.tz_convert('Europe/Istanbul')
    if pd.Timestamp.now(tz='Europe/Istanbul') >= kickoff:
        st.error('Maç başlamış. Maç öncesi oran testi yapılmadı.')
        return
    try:
        with st.spinner('OddsPapi: pazar kataloğu → fikstür → tek maç oranı...'):
            catalog = odds_papi_get('markets', {'language': 'en'}, api_key)
            dc = _double_chance_catalog(catalog)
            if not dc:
                st.warning('OddsPapi katalogunda doğrulanmış 90 dakika Çifte Şans pazarı bulunamadı. Oran gösterilmedi.')
                return
            tournament = odds_papi_tournament(api_key)
            if not tournament:
                st.warning('Türkiye Süper Lig turnuvası tekil olarak eşleşmedi.')
                return
            start = (kickoff - pd.Timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z')
            end = (kickoff + pd.Timedelta(days=2)).strftime('%Y-%m-%dT00:00:00Z')
            fixtures = odds_papi_get('fixtures', {'tournamentId': tournament, 'from': start,
                          'to': end, 'language': 'en', 'statusId': 0}, api_key)
            if not isinstance(fixtures, list):
                raise ValueError('Fikstür yanıtı beklenen biçimde değil.')
            fid = find_exact_fixture(row, fixtures)
            if not fid:
                st.warning('Takımlar ve başlangıç saati kesin eşleşmedi. Yanlış maça oran bağlanmadı.')
                return
            data = odds_papi_get('odds', {'fixtureId': fid, 'oddsFormat': 'decimal', 'language': 'en'}, api_key)
            if not isinstance(data, dict) or str(data.get('fixtureId')) != str(fid):
                raise ValueError('Oran yanıtındaki maç ID eşleşmiyor.')
            quotes = _extract(data, dc, str(row['Pazar']))
        st.success(f"Doğrulanan maç: {row['Maç']} • {row['Pazar']} • {kickoff.strftime('%d.%m.%Y %H:%M')}")
        st.caption('Katalog pazarları: ' + ', '.join(f"{v['name']} (ID {k})" for k,v in dc.items()))
        if quotes:
            st.dataframe(pd.DataFrame(quotes).head(20), hide_index=True, use_container_width=True)
            st.info('Test başarılı: gerçek 1X/X2 oranı bulundu. Henüz oran defterine kaydedilmedi; önce bu ekranı kontrol edelim.')
        else:
            st.warning('Maç ve pazar doğrulandı ancak seçilen 1X/X2 için aktif fiyat bulunamadı. Oran uydurulmadı.')
    except Exception as exc:
        st.error('OddsPapi test hatası: ' + str(exc)[:160])
