"""Shared UI helpers: styling, KPI cards, page headers with help + read-aloud, tables."""
from __future__ import annotations

import html
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from .help import HELP
from .i18n import lang, t, tf

NAVY = "#1f3a5f"
ACCENT = "#2e6fb5"
GREY = "#8a94a6"
SEQ = ["#1f3a5f", "#2e6fb5", "#7fa7d9", "#b9cbe3", "#8a94a6", "#c9ced6"]
PRIORITY_COLORS = {"Critical": "#b3261e", "High": "#e06c1f", "Medium": "#d9a400", "Low": "#3a9a68"}
STATUS_COLORS = {
    "Completed": "#3a9a68", "In Progress": "#2e6fb5", "Not Started": "#b9c2cf", "Blocked": "#b3261e",
    "Under Review": "#7b61c4", "Cancelled": "#8a94a6", "Active": "#2e6fb5", "On Hold": "#d9a400", "At risk": "#e06c1f",
}
BAND_COLORS = {"Underutilised": "#7fa7d9", "Healthy": "#3a9a68", "High": "#d9a400", "Overcapacity": "#b3261e"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea, select { font-family: 'Inter', system-ui, sans-serif; }
.block-container { padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1400px; }
h1, h2, h3 { letter-spacing: -0.01em; color: #1b2a3d; }
h1 { font-size: 1.65rem !important; font-weight: 700 !important; }
h2 { font-size: 1.25rem !important; }
h3 { font-size: 1.05rem !important; }
.kpi { background: #ffffff; border: 1px solid #e3e8ef; border-radius: 10px; padding: 14px 16px; height: 100%;
       box-shadow: 0 1px 2px rgba(16,24,40,.04); }
.kpi .lbl { font-size: .74rem; color: #5b6676; text-transform: uppercase; letter-spacing: .04em; font-weight: 600; }
.kpi .val { font-size: 1.6rem; font-weight: 700; color: #1b2a3d; line-height: 1.25; margin-top: 4px; }
.kpi .sub { font-size: .76rem; color: #6b7686; margin-top: 2px; min-height: 1.15em; }
.kpi.bad { border-left: 4px solid #b3261e; } .kpi.warn { border-left: 4px solid #e06c1f; }
.kpi.good { border-left: 4px solid #3a9a68; } .kpi.neutral { border-left: 4px solid #2e6fb5; }
.pill { display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: .75rem; font-weight: 600; color: #fff; }
.demo-banner { background: #fff8e6; border: 1px solid #f0d68a; color: #6b5200; padding: 8px 14px; border-radius: 8px;
               font-size: .82rem; margin-bottom: 12px; }
.subtle { color: #6b7686; font-size: .86rem; }
.card { background:#fff; border:1px solid #e3e8ef; border-radius:10px; padding:14px 16px; margin-bottom:10px; }
.card h4 { margin: 0 0 6px 0; font-size: .98rem; color:#1b2a3d; }
.step { display:flex; gap:10px; align-items:flex-start; margin: 6px 0; }
.step .n { background:#1f3a5f; color:#fff; border-radius:50%; min-width:24px; height:24px; text-align:center;
           font-size:.8rem; line-height:24px; font-weight:700; }
[data-testid="stSidebar"] { background: #f4f6f9; }
[data-testid="stSidebar"] .stRadio label { font-size: .9rem; }
div[data-testid="stMetricValue"] { font-size: 1.4rem; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def kpi(label: str, value, sub: str = "", tone: str = "neutral") -> str:
    return (f'<div class="kpi {tone}"><div class="lbl">{html.escape(label)}</div>'
            f'<div class="val">{html.escape(str(value))}</div><div class="sub">{html.escape(sub)}</div></div>')


def kpi_row(items: list[tuple], per_row: int = 4) -> None:
    for i in range(0, len(items), per_row):
        cols = st.columns(per_row)
        for c, it in zip(cols, items[i:i + per_row]):
            c.markdown(kpi(*it), unsafe_allow_html=True)
        st.write("")


def pill(text: str, color: str) -> str:
    return f'<span class="pill" style="background:{color}">{html.escape(tf(text))}</span>'


def _html(content: str, height: int) -> None:
    """Render a small HTML/JS snippet (components.html where available, st.iframe otherwise)."""
    fn = getattr(components, "html", None)
    if fn is not None:
        fn(content, height=height)
    else:
        st.iframe(content, height=height)


def listen_button(text: str, key: str) -> None:
    """Read text aloud with the browser's built-in speech synthesis (free, no API)."""
    voice_lang = "fr-FR" if lang() == "fr" else "en-GB"
    label = "🔊 Écouter" if lang() == "fr" else "🔊 Listen"
    stop = "⏹ Stop"
    _html(f"""
    <div style="font-family:Inter,system-ui,sans-serif">
    <button id="b" style="background:#1f3a5f;color:#fff;border:0;border-radius:6px;padding:6px 12px;cursor:pointer;font-size:13px">{label}</button>
    <button id="s" style="background:#e3e8ef;color:#1b2a3d;border:0;border-radius:6px;padding:6px 10px;cursor:pointer;font-size:13px;margin-left:6px">{stop}</button>
    <span id="m" style="font-size:12px;color:#6b7686;margin-left:8px"></span>
    </div>
    <script>
    const txt = {json.dumps(text)};
    document.getElementById('b').onclick = () => {{
      if (!('speechSynthesis' in window)) {{ document.getElementById('m').innerText = 'Speech not supported in this browser'; return; }}
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(txt); u.lang = '{voice_lang}'; u.rate = 1.0;
      const v = window.speechSynthesis.getVoices().find(v => v.lang && v.lang.startsWith('{voice_lang[:2]}'));
      if (v) u.voice = v;
      window.speechSynthesis.speak(u);
    }};
    document.getElementById('s').onclick = () => window.speechSynthesis.cancel();
    </script>""", height=42)


def page_header(page: str, title: str, subtitle: str = "") -> None:
    st.title(title)
    if subtitle:
        st.markdown(f'<div class="subtle">{subtitle}</div>', unsafe_allow_html=True)
    h = HELP.get(page)
    if h:
        steps = h["fr"] if lang() == "fr" else h["en"]
        with st.expander("❓ " + t("How to use this page"), expanded=False):
            for i, s in enumerate(steps, 1):
                st.markdown(f'<div class="step"><div class="n">{i}</div><div>{html.escape(s)}</div></div>', unsafe_allow_html=True)
            listen_button(" ".join(f"{i}. {s}" for i, s in enumerate(steps, 1)), key=f"listen_{page}")


def demo_banner(company: dict) -> None:
    if company and company.get("is_demo"):
        st.markdown('<div class="demo-banner">' + html.escape(t(
            "Demonstration workspace: company facts come from the NOVATECH case study; people, clients, contracts, "
            "figures and signals are fictional sample records. Nothing here is a confirmed incident.")) + "</div>",
            unsafe_allow_html=True)


def style_fig(fig: go.Figure, height: int = 320, legend: bool = True) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=10, r=10, t=40, b=10),
        font=dict(family="Inter, system-ui, sans-serif", size=12, color="#1b2a3d"),
        title_font=dict(size=14), showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="left", x=0, title_text=""),
        colorway=SEQ, paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
    )
    fig.update_xaxes(gridcolor="#eef1f5", zeroline=False)
    fig.update_yaxes(gridcolor="#eef1f5", zeroline=False)
    return fig


def table(df: pd.DataFrame, cols: dict[str, str] | None = None, translate_values: tuple = (), height: int | None = None,
          column_config: dict | None = None) -> None:
    """Show a dataframe with translated headers (and optionally translated enum values)."""
    if df is None or df.empty:
        st.info(t("No records to display."))
        return
    d = df.copy()
    if cols:
        d = d[[c for c in cols if c in d.columns]].rename(columns={k: t(v) for k, v in cols.items()})
    for c in translate_values:
        tc = t(cols.get(c, c)) if cols else c
        if tc in d.columns:
            d[tc] = d[tc].map(tf)
    kw = {"hide_index": True}
    if height:
        kw["height"] = height
    if column_config:
        kw["column_config"] = {t(cols.get(k, k)) if cols else k: v for k, v in column_config.items()}
    st.dataframe(d, **kw)


def money(x, cur: str = "EUR") -> str:
    try:
        sym = {"EUR": "€", "USD": "$", "GBP": "£", "INR": "₹"}.get(cur, cur + " ")
        return f"{sym}{float(x):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return "-"


def opt(options: list, key_fmt=tf):
    """Helper returning selectbox kwargs with translated display."""
    return {"options": options, "format_func": key_fmt}
