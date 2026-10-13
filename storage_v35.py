"""V3.9.1 persistent odds ledger. Supabase is primary; safe connection diagnostics included."""
import json
from pathlib import Path
from datetime import datetime, timezone
import requests
import streamlit as st

STORE = Path('.iddaa_v37_ledger.json')
TABLE = 'odds_records'


def _cfg():
    try:
        url = str(st.secrets.get('SUPABASE_URL', '')).strip().rstrip('/')
        # Accept common secret names so a correctly stored Supabase secret is not missed.
        key = str(
            st.secrets.get('SUPABASE_SECRET_KEY', '')
            or st.secrets.get('SUPABASE_SERVICE_ROLE_KEY', '')
            or st.secrets.get('SUPABASE_KEY', '')
        ).strip()
    except Exception:
        url, key = '', ''
    return url, key


def cloud_ready():
    url, key = _cfg()
    return url.startswith('https://') and bool(key)


def _headers(prefer=None):
    _, key = _cfg()
    h = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    if prefer:
        h['Prefer'] = prefer
    return h


def _split_match(name):
    text = str(name)
    for sep in ('–', '—', ' - '):
        if sep in text:
            a, b = text.split(sep, 1)
            return a.strip(), b.strip()
    return text.strip(), ''


def _to_db(r):
    home, away = _split_match(r.get('mac', ''))
    selection = str(r.get('pazar', ''))
    return {
        'match_key': str(r['id']),
        'match_date': str(r['tarih']),
        'home_team': home,
        'away_team': away,
        'market': 'Double Chance Full Time' if selection in ('1X', 'X2') else selection,
        'selection': selection,
        'model_pct': float(r.get('model_pct') or 0),
        'backtest_pct': float(r.get('backtest_pct') or 0),
        'odds': float(r['oran']),
        'bookmaker': str(r.get('kaynak', '')),
        'stake': float(r.get('tutar', 100)),
        'locked_at': str(r['kayit_zamani']),
        'status': str(r.get('status', 'BEKLIYOR')),
        'home_score': r.get('home_score'),
        'away_score': r.get('away_score'),
        'is_hit': r.get('is_hit'),
        'profit_loss': r.get('profit_loss'),
        'settled_at': r.get('settled_at'),
    }


def _from_db(r):
    mac = f"{r.get('home_team','')} - {r.get('away_team','')}".strip(' -')
    return {
        'id': str(r['match_key']), 'tarih': str(r['match_date']), 'mac': mac,
        'pazar': str(r.get('selection', '')), 'oran': float(r['odds']),
        'kaynak': str(r.get('bookmaker') or ''), 'kayit_zamani': str(r['locked_at']),
        'tutar': float(r.get('stake') or 100),
        'model_pct': float(r.get('model_pct') or 0), 'backtest_pct': float(r.get('backtest_pct') or 0),
        'status': str(r.get('status') or 'BEKLIYOR'), 'is_hit': r.get('is_hit'),
        'profit_loss': r.get('profit_loss'), 'settled_at': r.get('settled_at')
    }


def _cloud_load():
    url, _ = _cfg()
    resp = requests.get(f'{url}/rest/v1/{TABLE}', params={'select':'*','order':'locked_at.asc'}, headers=_headers(), timeout=12)
    resp.raise_for_status()
    return {str(x['match_key']): _from_db(x) for x in resp.json()}


def _cloud_upsert(records):
    if not records:
        return
    url, _ = _cfg()
    payload = [_to_db(x) for x in records.values()]
    resp = requests.post(
        f'{url}/rest/v1/{TABLE}',
        params={'on_conflict':'match_key,market,selection'},
        headers=_headers('resolution=merge-duplicates,return=minimal'),
        json=payload, timeout=15
    )
    resp.raise_for_status()


def _local_load():
    try:
        if STORE.exists():
            raw = json.loads(STORE.read_text(encoding='utf-8'))
            return raw if isinstance(raw, dict) else {}
    except Exception:
        pass
    return {}


def _local_save(records):
    try:
        tmp = STORE.with_suffix('.tmp')
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(STORE)
    except Exception:
        pass


def load_records(force=False):
    if not force and 'v31_records' in st.session_state:
        return st.session_state.v31_records
    data = {}
    if cloud_ready():
        try:
            data = _cloud_load()
            st.session_state['v37_cloud_ok'] = True
            st.session_state.pop('v37_cloud_error', None)
        except Exception as exc:
            st.session_state['v37_cloud_ok'] = False
            st.session_state['v37_cloud_error'] = str(exc)[:220]
            data = _local_load()
    else:
        data = _local_load()
    st.session_state.v31_records = data
    return data


def save_records(records=None):
    if records is None:
        records = st.session_state.get('v31_records', {})
    _local_save(records)
    if not cloud_ready():
        msg = 'Supabase ayarı eksik: SUPABASE_URL ve Secret key bulunamadı.'
        st.session_state['v37_cloud_ok'] = False
        st.session_state['v37_cloud_error'] = msg
        raise RuntimeError(msg)
    try:
        _cloud_upsert(records)
        st.session_state['v37_cloud_ok'] = True
        st.session_state.pop('v37_cloud_error', None)
        st.session_state.v31_records = records
    except Exception as exc:
        msg = str(exc)[:500]
        st.session_state['v37_cloud_ok'] = False
        st.session_state['v37_cloud_error'] = msg
        raise RuntimeError('Supabase kayıt hatası: ' + msg) from exc


def settle_records(outcomes):
    """Persist settled hit/loss + virtual P/L without changing locked pre-match odds."""
    records = load_records()
    changed = False
    now = datetime.now(timezone.utc).isoformat()
    for key, hit in outcomes.items():
        if key not in records or records[key].get('status') in ('BILDI', 'BILEMEDI'):
            continue
        r = records[key]
        stake, odds = float(r.get('tutar',100)), float(r.get('oran',0))
        r['status'] = 'BILDI' if hit else 'BILEMEDI'
        r['is_hit'] = bool(hit)
        r['profit_loss'] = round(stake*(odds-1) if hit else -stake, 2)
        r['settled_at'] = now
        changed = True
    if changed:
        save_records(records)
    return changed


def cloud_status():
    if not cloud_ready():
        return False, 'Supabase ayarı eksik: SUPABASE_URL ve Secret key bulunamadı.'
    try:
        data = _cloud_load()
        st.session_state.v31_records = data
        st.session_state['v37_cloud_ok'] = True
        return True, f'Supabase bağlantısı doğrulandı • {len(data)} kalıcı oran kaydı.'
    except Exception as exc:
        st.session_state['v37_cloud_ok'] = False
        return False, 'Supabase bağlantı hatası: ' + str(exc)[:180]



def cloud_diagnostics():
    """Safe diagnostics: never returns the key itself."""
    url, key = _cfg()
    out = {
        'url_ok': url.startswith('https://'),
        'key_found': bool(key),
        'key_type': 'secret/service-role' if (key.startswith('sb_secret_') or key.startswith('eyJ')) else ('publishable/other' if key else 'missing'),
        'http_status': None,
        'message': '',
    }
    if not out['url_ok']:
        out['message'] = 'SUPABASE_URL eksik veya https:// ile başlamıyor.'
        return out
    if not key:
        out['message'] = 'Supabase Secret key bulunamadı.'
        return out
    try:
        resp = requests.get(
            f'{url}/rest/v1/{TABLE}',
            params={'select':'id','limit':'1'},
            headers=_headers(), timeout=12
        )
        out['http_status'] = resp.status_code
        if 200 <= resp.status_code < 300:
            out['message'] = 'BAŞARILI: Streamlit, Supabase tablosunu okuyabiliyor.'
        else:
            body = (resp.text or '').replace(key, '[GIZLI]')[:300]
            out['message'] = f'HTTP {resp.status_code}: {body}'
    except Exception as exc:
        out['message'] = f'Bağlantı isteği başarısız: {str(exc)[:250]}'
    return out
