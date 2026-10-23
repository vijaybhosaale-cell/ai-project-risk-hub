"""Smoke test: render every page for every role with Streamlit's AppTest (headless)."""
import os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HUB_DB_PATH", os.path.join(tempfile.gettempdir(), "hub_test.db"))
import pandas as pd
import streamlit.dataframe_util as du
# pyarrow is unavailable in this sandbox: exercise pandas conversion, skip Arrow serialisation.
def _fake(data, *a, **k):
    du.convert_anything_to_pandas_df(data)
    return b""
du.convert_anything_to_arrow_bytes = _fake
du.convert_pandas_df_to_arrow_bytes = lambda df, *a, **k: b""
import logging; logging.disable(logging.WARNING)
import streamlit as _st
from streamlit.delta_generator import DeltaGenerator
def _fake_df(self, data=None, *a, **k):
    d = du.convert_anything_to_pandas_df(data)
    cc = k.get("column_config") or {}
    missing = [c for c in cc if c not in d.columns]
    if missing: raise KeyError(f"column_config keys not in dataframe: {missing}")
    return self.markdown(f"[table {len(d)} rows]")
def _fake_editor(self, data=None, *a, **k):
    _fake_df(self, data, **{x: y for x, y in k.items() if x == "column_config"})
    return data
DeltaGenerator.dataframe = _fake_df
DeltaGenerator.data_editor = _fake_editor
_st.dataframe = lambda *a, **k: _fake_df(_st._main, *a, **k)
_st.data_editor = lambda *a, **k: _fake_editor(_st._main, *a, **k)
from streamlit.testing.v1 import AppTest
from hub import db, seed
if os.environ.get("FRESH", "1") == "1" and os.path.exists(db.DB_PATH):
    os.remove(db.DB_PATH)
t0 = time.time(); seed.ensure_demo(); print("seed", round(time.time()-t0, 1), "s")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import app_pages
roles = sys.argv[1:] or None
fails = 0
for u in db.query("SELECT * FROM users ORDER BY id"):
    if roles and u["email"].split("@")[0] not in roles: continue
    for lang in ("en", "fr"):
        at = AppTest.from_file("../app.py", default_timeout=60)
        at.session_state["user"] = {"id": u["id"]}
        at.session_state["lang"] = lang
        at.run()
        pages = at.sidebar.radio[1].options if len(at.sidebar.radio) > 1 else []
        only = [x for x in os.environ.get("PAGES", "").split(",") if x]
        for p in app_pages.keys_for(u["role"]):
            if only and p not in only: continue
            at = AppTest.from_file("../app.py", default_timeout=60)
            at.session_state["user"] = {"id": u["id"]}
            at.session_state["lang"] = lang
            at.session_state["nav"] = p
            at.session_state["wizard_seen"] = True
            t1 = time.time(); at.run()
            dt = time.time() - t1
            if at.exception:
                fails += 1
                print("FAIL", u["role"], lang, p, at.exception[0].message[:300]); print("\n".join(at.exception[0].stack_trace[-6:]))
            elif dt > 8:
                print("SLOW", u["role"], p, round(dt, 1))
        if lang == "en": print("ok", u["role"], len(app_pages.keys_for(u["role"])), "pages")
print("FAILURES:", fails)
