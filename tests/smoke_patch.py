import logging; logging.disable(logging.WARNING)
import streamlit as _st
import streamlit.dataframe_util as du
from streamlit.delta_generator import DeltaGenerator
def _fake_df(self, data=None, *a, **k):
    d = du.convert_anything_to_pandas_df(data)
    return self.markdown(f"[table {len(d)} rows]")
DeltaGenerator.dataframe = _fake_df
_st.dataframe = lambda *a, **k: _fake_df(_st._main, *a, **k)
