"""AI Project & Risk Intelligence Hub - Streamlit entry point.

Run locally:  pip install -r requirements.txt  &&  streamlit run app.py

Every module is a real page with its own URL (st.navigation), so the browser's
Back / Forward / Refresh buttons stay inside the app. A server-side session
(cookie "hub_sid", 8 h) keeps the user signed in after a refresh.
"""
from __future__ import annotations

import importlib
import json

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="AI Project & Risk Intelligence Hub", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

from hub import audit, auth, db, events, perms, router, seed, ui  # noqa: E402
from hub.i18n import LANGS, t  # noqa: E402


@st.cache_resource(show_spinner="Preparing workspace…")
def _bootstrap() -> bool:
    seed.ensure_demo()  # creates schema and re-creates the NOVATECH demo workspace if the DB is empty
    return True


_bootstrap()
ui.inject_css()

SECTIONS = [  # (section label, [(page key, label, module, icon)])
    ("Overview", [
        ("getting_started", "Getting started", "getting_started", "🧭"),
        ("inbox", "Inbox", "inbox", "🔔"),
        ("dashboard", "Executive dashboard", "dashboard", "📊"),
        ("my_work", "My work", "my_work", "✅"),
        ("reports", "Management reports", "reports", "📄"),
    ]),
    ("Delivery", [
        ("allocation", "Resource allocation", "allocation", "⚖️"),
        ("gantt", "Gantt chart", "gantt", "📅"),
        ("projects", "Projects", "projects", "📁"),
        ("tasks", "Tasks", "tasks", "🗂️"),
        ("absences", "Absences & availability", "absences", "🏖️"),
        ("budget", "Budget & finance", "budget", "💶"),
    ]),
    ("Risk & compliance", [
        ("risks", "Risk register", "risks", "🛡️"),
        ("risk_areas", "Risk areas & signals", "risk_areas", "📡"),
        ("gdpr", "GDPR evidence", "gdpr", "🇪🇺"),
        ("subcontractors", "Subcontractors", "subcontractors", "🤝"),
        ("clients", "Clients & contracts", "clients", "🏢"),
        ("audit", "Audit log", "audit_view", "🧾"),
    ]),
    ("People", [
        ("employees", "Employees", "employees", "👥"),
        ("onboarding", "Onboarding & training", "onboarding", "🎓"),
        ("access", "Access lifecycle (JML)", "access", "🔑"),
        ("users", "Users & roles", "users", "👤"),
    ]),
    ("Administration", [
        ("notifications", "Notifications", "notifications", "📨"),
        ("settings", "Company settings & setup", "settings", "⚙️"),
        ("security", "Security notes", "security", "🔒"),
        ("platform", "Platform administration", "platform", "🌐"),
    ]),
]


def language_switch(where) -> None:
    cur = st.session_state.get("lang", "en")
    choice = where.radio("🌐 Language / Langue", list(LANGS), index=list(LANGS).index(cur),
                         format_func=lambda k: LANGS[k], horizontal=True, key="lang_radio")
    if choice != cur:
        st.session_state["lang"] = choice
        st.rerun()


def cookie_script() -> None:
    """Set or clear the session cookie in the browser (first-party, SameSite=Lax)."""
    action = st.session_state.pop("cookie_action", None)
    if not action:
        return
    if action[0] == "set":
        val = f"hub_sid={action[1]}; path=/; max-age={auth.SESSION_HOURS * 3600}; SameSite=Lax"
    else:
        val = "hub_sid=; path=/; max-age=0; SameSite=Lax"
    js = f"""<script>
    const v = {json.dumps(val)} + (location.protocol === 'https:' ? '; Secure' : '');
    try {{ window.parent.document.cookie = v; }} catch (e) {{}}
    try {{ document.cookie = v; }} catch (e) {{}}
    </script>"""
    with st.sidebar:
        components.html(js, height=0)


def current_user() -> dict | None:
    u = st.session_state.get("user")
    if not u:
        # Restore the session after a browser refresh.
        token = st.query_params.get("s")
        if not token:
            try:
                token = st.context.cookies.get("hub_sid")
            except Exception:
                token = None
        restored = auth.session_user(token, router.user_agent())
        if restored:
            st.session_state["user"] = {"id": restored["id"]}
            st.session_state["sid"] = token
            return restored
        return None
    fresh = db.one("SELECT * FROM users WHERE id = ?", (u["id"],))
    if not fresh or not fresh["active"]:
        st.session_state.clear()
        return None
    return fresh


def visible(role: str, key: str) -> bool:
    if key in ("getting_started", "inbox"):
        return role != "Platform Administrator"
    return perms.can_view(role, key)


def make_page(key: str, label: str, mod: str, icon: str, ctx: dict, default: bool):
    def _run():
        hist = st.session_state.setdefault("page_hist", [])
        if not hist or hist[-1] != key:
            hist.append(key)
            del hist[:-30]
        c = dict(ctx, page=key, can_edit=perms.can_edit(ctx["role"], key))
        top = st.columns([1, 7])
        if len(hist) > 1 and top[0].button("← " + t("Back"), key=f"back_{key}"):
            hist.pop()
            router.go(hist[-1])
        if ctx["company"]:
            ui.demo_banner(ctx["company"])
        importlib.import_module(f"views.{mod}").render(c)
    _run.__name__ = f"page_{key}"
    title = t(label)
    if key == "inbox" and ctx.get("unread"):
        title = f"{title} ({ctx['unread']})"
    return st.Page(_run, title=title, icon=icon, url_path=key, default=default)


def main() -> None:
    user = current_user()
    if not user:
        language_switch(st.sidebar)
        cookie_script()
        from views import auth_view
        st.navigation([st.Page(auth_view.render, title=t("Sign in"), icon="🔐", default=True)], position="hidden").run()
        return

    role, cid = user["role"], user["company_id"]
    company = db.company(cid) if cid else None
    ctx = {"user": user, "cid": cid, "company": company, "role": role,
           "unread": events.unread(user["id"]) if cid else 0}
    keys = [k for _, items in SECTIONS for k, *_ in items if visible(role, k)]
    default_key = "platform" if role == "Platform Administrator" else "getting_started"
    if company and not company["setup_complete"] and role == "Company Administrator":
        default_key = "settings"
    default_key = st.session_state.get("_force_page") or default_key
    if default_key not in keys:
        default_key = keys[0]

    pages, grouped = {}, []
    for section, items in SECTIONS:
        sec = []
        for key, label, mod, icon in items:
            if key in keys:
                pages[key] = make_page(key, label, mod, icon, ctx, key == default_key)
                sec.append(key)
        if sec:
            grouped.append((section, sec))
    router.register(pages)
    current = st.navigation(list(pages.values()), position="hidden")

    with st.sidebar:
        st.markdown(f"### 🛡️ {t('Risk Intelligence Hub')}")
        if company:
            st.markdown(f"**{company['name']}**")
        st.caption(f"{user['name'].split(' (')[0]} · {t(role)}")
        language_switch(st.sidebar)
        for section, sec_keys in grouped:
            st.markdown(f"<div class='nav-sec'>{t(section)}</div>", unsafe_allow_html=True)
            for k in sec_keys:
                st.page_link(pages[k])
        st.divider()
        if st.button("↩ " + t("Sign out"), width="stretch"):
            audit.log(cid, user["email"], "logout", "user", user["id"])
            auth.end_session(st.session_state.get("sid"))
            lang = st.session_state.get("lang", "en")
            st.session_state.clear()
            st.query_params.clear()
            st.session_state["lang"] = lang
            st.session_state["cookie_action"] = ("clear",)
            st.rerun()
        st.caption(t("Prototype v1 · rule-based risk engine (no trained AI model)"))
    cookie_script()
    # Keep the session reference in the URL so a browser refresh keeps the user signed in.
    sid = st.session_state.get("sid")
    if sid and st.query_params.get("s") != sid:
        st.query_params["s"] = sid
    current.run()


main()
