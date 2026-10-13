"""V3.5 lightweight ledger persistence.
Survives Streamlit reruns/reconnects while the app instance lives; CSV remains the portable backup.
"""
import json
from pathlib import Path
import streamlit as st

STORE = Path('.iddaa_v35_ledger.json')


def load_records():
    if 'v31_records' in st.session_state:
        return st.session_state.v31_records
    data = {}
    try:
        if STORE.exists():
            raw = json.loads(STORE.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                data = raw
    except Exception:
        data = {}
    st.session_state.v31_records = data
    return data


def save_records(records=None):
    if records is None:
        records = st.session_state.get('v31_records', {})
    tmp = STORE.with_suffix('.tmp')
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(STORE)


def upsert(record):
    records = load_records()
    records[str(record['id'])] = record
    st.session_state.v31_records = records
    save_records(records)
