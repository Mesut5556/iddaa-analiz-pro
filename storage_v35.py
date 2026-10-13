"""V3.6 persistent ledger: Supabase first, session/local fallback.
Uses Streamlit Secrets: SUPABASE_URL and SUPABASE_KEY.
"""
import json
from pathlib import Path
import requests
import streamlit as st
import pandas as pd

STORE = Path('.iddaa_v36_ledger.json')
TABLE = 'odds_records'


def _cfg():
    try:
        url = str(st.secrets.get('SUPABASE_URL', '')).rstrip('/')
        key = str(st.secrets.get('SUPABASE_KEY', ''))
    except Exception:
        url, key = '', ''
    return url, key


def cloud_ready():
    url, key = _cfg()
    return bool(url and key)


def _headers(prefer=None):
    _, key = _cfg()
    h = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    if prefer: h['Prefer'] = prefer
    return h


def _split_match(name):
    for sep in ('–', '—', ' - ', '-'):
        if sep in str(name):
            a, b = str(name).split(sep, 1)
            return a.strip(), b.strip()
    return str(name).strip(), ''


def _to_db(r):
    home, away = _split_match(r.get('mac', ''))
    return {
        'match_key': str(r['id']), 'match_date': str(r['tarih']),
        'home_team': home, 'away_team': away,
        'market': 'Double Chance Full Time' if str(r.get('pazar')) in ('1X','X2') else str(r.get('pazar','')),
        'selection': str(r.get('pazar','')), 'odds': float(r['oran']),
        'bookmaker': str(r.get('kaynak','')), 'stake': float(r.get('tutar',100)),
        'locked_at': str(r['kayit_zamani']), 'status': str(r.get('status','BEKLIYOR'))
    }


def _from_db(r):
    mac = f"{r.get('home_team','')}–{r.get('away_team','')}".strip('–')
    return {'id': str(r['match_key']), 'tarih': str(r['match_date']), 'mac': mac,
            'pazar': str(r.get('selection','')), 'oran': float(r['odds']),
            'kaynak': str(r.get('bookmaker') or ''), 'kayit_zamani': str(r['locked_at']),
            'tutar': float(r.get('stake') or 100)}


def _cloud_load():
    url, _ = _cfg()
    resp = requests.get(f'{url}/rest/v1/{TABLE}', params={'select':'*','order':'locked_at.asc'}, headers=_headers(), timeout=12)
    resp.raise_for_status()
    return {str(x['match_key']): _from_db(x) for x in resp.json()}


def _cloud_upsert(records):
    if not records: return
    url, _ = _cfg()
    payload = [_to_db(x) for x in records.values()]
    resp = requests.post(f'{url}/rest/v1/{TABLE}', params={'on_conflict':'match_key,market,selection'},
        headers=_headers('resolution=ignore-duplicates,return=minimal'), json=payload, timeout=15)
    resp.raise_for_status()


def _local_load():
    try:
        if STORE.exists():
            raw = json.loads(STORE.read_text(encoding='utf-8'))
            return raw if isinstance(raw, dict) else {}
    except Exception: pass
    return {}


def _local_save(records):
    try:
        tmp = STORE.with_suffix('.tmp')
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(STORE)
    except Exception: pass


def load_records(force=False):
    if not force and 'v31_records' in st.session_state:
        return st.session_state.v31_records
    data = {}
    if cloud_ready():
        try:
            data = _cloud_load()
            st.session_state['v36_cloud_ok'] = True
        except Exception as exc:
            st.session_state['v36_cloud_ok'] = False
            st.session_state['v36_cloud_error'] = str(exc)[:180]
            data = _local_load()
    else:
        data = _local_load()
    st.session_state.v31_records = data
    return data


def save_records(records=None):
    if records is None: records = st.session_state.get('v31_records', {})
    _local_save(records)
    if cloud_ready():
        _cloud_upsert(records)
        st.session_state['v36_cloud_ok'] = True
    st.session_state.v31_records = records


def upsert(record):
    records = load_records()
    records[str(record['id'])] = record
    save_records(records)


def cloud_status():
    if not cloud_ready(): return False, 'SUPABASE_URL / SUPABASE_KEY bulunamadı.'
    try:
        load_records(force=True)
        return True, 'Supabase kalıcı veritabanı bağlı.'
    except Exception as exc:
        return False, str(exc)[:180]
