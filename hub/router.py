"""Per-session registry of the st.Page objects of the current run, so views can link / switch to other pages."""
from __future__ import annotations

import streamlit as st


def register(pages: dict) -> None:
    st.session_state["_pages"] = pages


def page(key: str):
    return st.session_state.get("_pages", {}).get(key)


def link(key: str, label: str, icon: str | None = None, where=None, **kw) -> None:
    """Render a link to another page if the current user can open it."""
    p = page(key)
    if p is None:
        return
    (where or st).page_link(p, label=label, icon=icon, **kw)


def session_params() -> dict:
    sid = st.session_state.get("sid")
    return {"s": sid} if sid else {}


def go(key: str) -> None:
    p = page(key)
    if p is not None:
        st.switch_page(p, query_params=session_params())


def user_agent() -> str:
    try:
        ua = st.context.headers.get("User-Agent")
        return ua if isinstance(ua, str) else ""
    except Exception:
        return ""
