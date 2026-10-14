"""V3.9.4 performance notes / cache version marker.
Heavy walk-forward calculations are cached in app.py with st.cache_data.
Kept as a tiny separate module so future performance helpers can move here
without touching the frozen decision model.
"""
CACHE_VERSION = "V3.9.4"
