"""AI Project & Risk Intelligence Hub - Streamlit entry point.

Run locally:  pip install -r requirements.txt  &&  streamlit run app.py
"""
from __future__ import annotations

import importlib

import streamlit as st

st.set_page_config(page_title="AI Project & Risk Intelligence Hub", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

from hub import db, perms, seed, ui  # noqa: E402
from hub.i18n import LANGS, t  # noqa: E402


@st.cache_resource(show_spinner="Preparing workspace…")
def _bootstrap() -> bool:
    seed.ensure_demo()  # creates schema and re-creates the NOVATECH demo workspace if the DB is empty
    return True


_bootstrap()
ui.inject_css()

NAV = [  # (page key, label, module)
    ("getting_started", "Getting started", "getting_started"),
    ("dashboard", "Executive dashboard", "dashboard"),
    ("my_work", "My work", "my_work"),
    ("allocation", "Resource allocation", "allocation"),
    ("risks", "Risk register", "risks"),
    ("gantt", "Gantt chart", "gantt"),
    ("projects", "Projects", "projects"),
    ("tasks", "Tasks", "tasks"),
    ("employees", "Employees", "employees"),
    ("absences", "Absences & availability", "absences"),
    ("budget", "Budget & finance", "budget"),
    ("risk_areas", "Risk areas & signals", "risk_areas"),
    ("onboarding", "Onboarding & training", "onboarding"),
    ("access", "Access lifecycle (JML)", "access"),
    ("subcontractors", "Subcontractors", "subcontractors"),
    ("clients", "Clients & contracts", "clients"),
    ("gdpr", "GDPR evidence", "gdpr"),
    ("notifications", "Notifications", "notifications"),
    ("reports", "Management reports", "reports"),
    ("audit", "Audit log", "audit_view"),
    ("users", "Users & roles", "users"),
    ("settings", "Company settings & setup", "settings"),
    ("security", "Security notes", "security"),
    ("platform", "Platform administration", "platform"),
]
ICONS = {"getting_started": "🧭", "dashboard": "📊", "my_work": "✅", "allocation": "⚖️", "risks": "🛡️", "gantt": "📅",
         "projects": "📁", "tasks": "🗂️", "employees": "👥", "absences": "🏖️", "budget": "💶", "risk_areas": "📡",
         "onboarding": "🎓", "access": "🔑", "subcontractors": "🤝", "clients": "🏢", "gdpr": "🇪🇺",
         "notifications": "🔔", "reports": "📄", "audit": "🧾", "users": "👤", "settings": "⚙️", "security": "🔒",
         "platform": "🌐"}


def language_switch(where) -> None:
    cur = st.session_state.get("lang", "en")
    choice = where.radio("🌐 Language / Langue", list(LANGS), index=list(LANGS).index(cur),
                         format_func=lambda k: LANGS[k], horizontal=True, key="lang_radio")
    if choice != cur:
        st.session_state["lang"] = choice
        st.rerun()


def current_user() -> dict | None:
    u = st.session_state.get("user")
    if not u:
        return None
    fresh = db.one("SELECT * FROM users WHERE id = ?", (u["id"],))
    if not fresh or not fresh["active"]:
        st.session_state.clear()
        return None
    return fresh


def allowed_pages(role: str) -> list[tuple]:
    out = []
    for key, label, mod in NAV:
        if key == "getting_started":
            if role != "Platform Administrator":
                out.append((key, label, mod))
        elif perms.can_view(role, key):
            out.append((key, label, mod))
    return out


def main() -> None:
    user = current_user()
    if not user:
        language_switch(st.sidebar)
        from views import auth_view
        auth_view.render()
        return

    role = user["role"]
    cid = user["company_id"]
    company = db.company(cid) if cid else None
    with st.sidebar:
        st.markdown(f"### 🛡️ {t('Risk Intelligence Hub')}")
        if company:
            st.markdown(f"**{company['name']}**")
        st.caption(f"{user['name'].split(' (')[0]} · {t(role)}")
        language_switch(st.sidebar)
        pages = allowed_pages(role)
        keys = [p[0] for p in pages]
        if st.session_state.get("nav") not in keys:
            st.session_state["nav"] = keys[0]
        # force the setup wizard for a new company administrator
        if company and not company["setup_complete"] and role == "Company Administrator" and not st.session_state.get("wizard_seen"):
            st.session_state["nav"] = "settings"
            st.session_state["wizard_seen"] = True
        st.radio(t("Navigation"), keys, key="nav",
                 format_func=lambda k: f"{ICONS.get(k, '•')}  {t(dict((p[0], p[1]) for p in pages)[k])}",
                 label_visibility="collapsed")
        st.divider()
        if st.button("↩ " + t("Sign out"), width="stretch"):
            from hub import audit
            audit.log(cid, user["email"], "logout", "user", user["id"])
            lang = st.session_state.get("lang", "en")
            st.session_state.clear()
            st.session_state["lang"] = lang
            st.rerun()
        st.caption(t("Prototype v1 · rule-based risk engine (no trained AI model)"))

    page = st.session_state["nav"]
    mod = dict((p[0], p[2]) for p in pages)[page]
    ctx = {"user": user, "cid": cid, "company": company, "role": role,
           "can_edit": perms.can_edit(role, page), "page": page}
    if company:
        ui.demo_banner(company)
    module = importlib.import_module(f"views.{mod}")
    module.render(ctx)


main()
