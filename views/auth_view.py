"""Sign in / Register a company / Forgot password."""
from __future__ import annotations

import streamlit as st

from hub import audit, auth, db, notify, seed
from hub.i18n import t

TIMEZONES = ["Europe/Paris", "Europe/London", "Europe/Berlin", "Europe/Madrid", "Europe/Rome", "Europe/Brussels",
             "Asia/Kolkata", "America/New_York", "UTC"]
CURRENCIES = ["EUR", "USD", "GBP", "INR", "CHF"]
COUNTRIES = ["France", "Belgium", "Germany", "Spain", "Italy", "Netherlands", "Switzerland", "United Kingdom", "India",
             "United States", "Other"]


def _login(user: dict) -> None:
    st.session_state["user"] = {"id": user["id"]}
    st.session_state["nav"] = "platform" if user["role"] == "Platform Administrator" else "getting_started"
    if user["company_id"]:
        comp = db.company(user["company_id"])
        if comp and "lang" not in st.session_state:
            st.session_state["lang"] = comp["language"] or "en"
    st.rerun()


def render() -> None:
    left, mid, right = st.columns([1, 2.2, 1])
    with mid:
        st.markdown("<div style='text-align:center;font-size:2.4rem'>🛡️</div>", unsafe_allow_html=True)
        st.markdown(f"<h1 style='text-align:center;margin-bottom:0'>AI Project &amp; Risk Intelligence Hub</h1>",
                    unsafe_allow_html=True)
        st.markdown(f"<p class='subtle' style='text-align:center'>{t('Projects, people, resources and risks for growing companies - in one workspace.')}</p>",
                    unsafe_allow_html=True)
        tab_in, tab_reg, tab_fp = st.tabs(["🔐 " + t("Sign in"), "🏢 " + t("Register a company"), "❔ " + t("Forgot password")])

        with tab_in:
            with st.form("login"):
                email = st.text_input(t("E-mail"))
                pw = st.text_input(t("Password"), type="password")
                ok = st.form_submit_button(t("Sign in"), type="primary", width="stretch")
            if ok:
                user, msg = auth.authenticate(email, pw)
                if user:
                    _login(user)
                else:
                    st.error(t(msg))
            if seed.quick_demo_enabled():
                st.markdown("**🎬 " + t("Explore the NOVATECH demo (fictional data) as:") + "**")
                demo_users = db.query("""SELECT u.* FROM users u JOIN companies c ON c.id = u.company_id
                                         WHERE c.is_demo = 1 AND u.active = 1 ORDER BY u.id""")
                cols = st.columns(2)
                for i, du in enumerate(demo_users):
                    if cols[i % 2].button(t(du["role"]), key=f"demo_{du['id']}", width="stretch"):
                        audit.log(du["company_id"], du["email"], "demo_quick_login", "user", du["id"], "one-click demo access")
                        _login(du)
                st.caption(t("One-click access exists only for the fictional demo workspace and can be disabled with the DEMO_QUICK_LOGIN=false secret. Real company workspaces always require a password."))
            with st.expander("🔑 " + t("Demo accounts (NOVATECH SERVICES)")):
                st.markdown(t("All demo accounts use the demo password provided by the presenter. Each role sees different menus and permissions."))
                st.markdown("\n".join([
                    f"- `admin@{seed.DEMO_DOMAIN}` — {t('Company Administrator')}",
                    f"- `pm@{seed.DEMO_DOMAIN}` — {t('Project Manager')}",
                    f"- `lead@{seed.DEMO_DOMAIN}` — {t('Team Leader')}",
                    f"- `employee@{seed.DEMO_DOMAIN}` — {t('Employee')}",
                    f"- `hr@{seed.DEMO_DOMAIN}` — {t('HR / Training Manager')}",
                    f"- `risk@{seed.DEMO_DOMAIN}` — {t('Risk / Compliance Manager')}",
                    f"- `finance@{seed.DEMO_DOMAIN}` — {t('Finance Manager')}",
                    f"- `subcontractor@{seed.DEMO_DOMAIN}` — {t('Subcontractor')}",
                ]))

        with tab_reg:
            st.caption(t("Create an independent workspace for your company. You become its Company Administrator."))
            with st.form("register"):
                c1, c2 = st.columns(2)
                cname = c1.text_input(t("Company name") + " *")
                cemail = c2.text_input(t("Company e-mail") + " *")
                aname = c1.text_input(t("Administrator name") + " *")
                aemail = c2.text_input(t("Administrator e-mail") + " *")
                p1 = c1.text_input(t("Password") + " *", type="password", help=t("At least 10 characters with letters and digits"))
                p2 = c2.text_input(t("Confirm password") + " *", type="password")
                country = c1.selectbox(t("Country"), COUNTRIES)
                tz = c2.selectbox(t("Time zone"), TIMEZONES)
                lang = c1.selectbox(t("Preferred language"), ["en", "fr"], format_func=lambda x: {"en": "English", "fr": "Français"}[x])
                cur = c2.selectbox(t("Currency"), CURRENCIES)
                n_emp = c1.number_input(t("Number of employees"), min_value=1, value=20, step=1)
                n_proj = c2.number_input(t("Number of active projects"), min_value=0, value=3, step=1)
                locs = st.text_input(t("Company locations (comma-separated)"), placeholder="Paris, Lyon")
                submitted = st.form_submit_button(t("Create workspace"), type="primary", width="stretch")
            if submitted:
                errs = []
                if not cname.strip() or not aname.strip():
                    errs.append(t("Company name and administrator name are required."))
                if not auth.valid_email(cemail) or not auth.valid_email(aemail):
                    errs.append(t("Enter valid e-mail addresses."))
                elif auth.email_taken(aemail):
                    errs.append(t("An account already exists for this administrator e-mail."))
                if p1 != p2:
                    errs.append(t("Passwords do not match."))
                errs += [t(p) for p in auth.password_problems(p1)]
                if errs:
                    for e in errs:
                        st.error(e)
                else:
                    cid = db.execute(
                        """INSERT INTO companies (name, email, country, timezone, language, currency, declared_employees,
                           declared_projects, declared_locations, setup_complete, is_demo, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,0,0,?)""",
                        (cname.strip(), cemail.strip(), country, tz, lang, cur, int(n_emp), int(n_proj), locs, db.now()))
                    for loc in [x.strip() for x in locs.split(",") if x.strip()]:
                        db.t_insert("locations", cid, {"name": loc, "timezone": tz, "employee_count": 0, "active_projects": 0})
                    uid = auth.create_user(cid, aname.strip(), aemail, p1, "Company Administrator")
                    audit.log(cid, aemail.strip().lower(), "register_company", "company", cid, cname)
                    st.success(t("Workspace created. Signing you in…"))
                    st.session_state["lang"] = lang
                    _login(db.one("SELECT * FROM users WHERE id = ?", (uid,)))

        with tab_fp:
            st.caption(t("Request a one-time reset code. It is e-mailed if the company has configured e-mail; otherwise ask your company administrator to reset your password from Users & roles."))
            with st.form("forgot"):
                fe = st.text_input(t("E-mail"), key="fp_email")
                req = st.form_submit_button(t("Send reset code"))
            if req:
                user = db.one("SELECT * FROM users WHERE lower(email) = ?", (fe.strip().lower(),))
                token = auth.create_reset_token(fe) if user else None
                if token and user["company_id"]:
                    ok, _ = notify.send_email(user["company_id"], "Password reset code",
                                              f"Your one-time reset code (valid 30 minutes): {token}", to=user["email"])
                # Same message whether or not the account exists (no user enumeration)
                st.info(t("If the account exists and e-mail is configured, a reset code has been sent. Otherwise contact your company administrator."))
            with st.form("reset"):
                re_email = st.text_input(t("E-mail"), key="rs_email")
                code = st.text_input(t("Reset code"))
                np1 = st.text_input(t("New password"), type="password")
                do = st.form_submit_button(t("Reset password"))
            if do:
                probs = auth.password_problems(np1)
                if probs:
                    for p in probs:
                        st.error(t(p))
                elif auth.reset_with_token(re_email, code, np1):
                    st.success(t("Password updated. You can sign in now."))
                else:
                    st.error(t("Invalid or expired code."))
