"""English / French UI text. English strings are the keys; FR holds translations."""
from __future__ import annotations

import streamlit as st

from .fr import FR

LANGS = {"en": "English", "fr": "Français"}


def lang() -> str:
    return st.session_state.get("lang", "en")


def t(text: str, **kw) -> str:
    s = FR.get(text, text) if lang() == "fr" else text
    if kw:
        try:
            return s.format(**kw)
        except (KeyError, IndexError, ValueError):
            return s
    return s


def tf(value) -> str:
    """Translate a stored enum value (status, priority...) for display."""
    if value is None:
        return ""
    return t(str(value))
