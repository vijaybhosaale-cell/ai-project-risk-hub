"""User accounts and roles (company administrators only)."""
from __future__ import annotations

import streamlit as st

from hub import audit, auth, db, perms, ui
from hub.i18n import t, tf


def render(ctx: dict) -> None:
    cid, user = ctx["cid"], ctx["user"]
    ui.page_header("users", t("Users & roles"), t("Accounts of this company only"))
    us = db.df("""SELECT u.id, u.name, u.email, u.role, u.active, u.last_login, e.name AS employee, s.name AS subcontractor
                  FROM users u LEFT JOIN employees e ON e.id = u.employee_id LEFT JOIN subcontractors s ON s.id = u.subcontractor_id
                  WHERE u.company_id = ? ORDER BY u.role, u.name""", (cid,))
    ui.table(us, {"name": "Name", "email": "E-mail", "role": "Role", "employee": "Linked employee", "subcontractor": "Linked subcontractor",
                  "active": "Active", "last_login": "Last sign-in"}, translate_values=("role",))
    with st.expander("🔐 " + t("What each role can see and edit")):
        rows = []
        for page, (v, e) in perms.PAGES.items():
            if page == "platform":
                continue
            rows.append({"Module": page, **{r: ("✏️" if r in e else "👁️" if r in v else "") for r in auth.TENANT_ROLES}})
        import pandas as pd
        st.dataframe(pd.DataFrame(rows), hide_index=True)
    c1, c2 = st.columns(2)
    emps = db.t_rows("employees", cid, "active = 1", order="name")
    subs = db.t_rows("subcontractors", cid)
    with c1.form("new_user"):
        st.markdown("**" + t("Create a user") + "**")
        name = st.text_input(t("Name") + " *")
        email = st.text_input(t("E-mail") + " *")
        role = st.selectbox(t("Role"), auth.TENANT_ROLES, format_func=tf)
        emp = st.selectbox(t("Linked employee (for 'My work')"), [None] + [e["id"] for e in emps],
                           format_func=lambda i: "—" if i is None else next(e["name"] for e in emps if e["id"] == i))
        sub = st.selectbox(t("Linked subcontractor (Subcontractor role)"), [None] + [s["id"] for s in subs],
                           format_func=lambda i: "—" if i is None else next(s["name"] for s in subs if s["id"] == i))
        if st.form_submit_button(t("Create user"), type="primary"):
            if not name.strip() or not auth.valid_email(email):
                st.error(t("Name and a valid e-mail are required."))
            elif auth.email_taken(email):
                st.error(t("This e-mail is already used."))
            else:
                pw = auth.temp_password()
                auth.create_user(cid, name, email, pw, role, emp, sub)
                audit.log(cid, user["email"], "user_created", "user", email, role)
                st.success(t("User created. One-time temporary password (shown once, share it securely):"))
                st.code(pw)
    with c2.form("manage_user"):
        st.markdown("**" + t("Manage a user") + "**")
        others = us[us["id"] != user["id"]]
        if others.empty:
            st.caption(t("No other users."))
            st.form_submit_button(t("Apply"), disabled=True)
        else:
            uid = st.selectbox(t("User"), others["id"].tolist(), format_func=lambda i: f"{others.set_index('id').loc[i, 'email']}")
            action = st.radio(t("Action"), ["reset", "role", "deactivate", "activate"], horizontal=False,
                              format_func=lambda a: {"reset": t("Reset password"), "role": t("Change role"), "deactivate": t("Deactivate"), "activate": t("Re-activate")}[a])
            new_role = st.selectbox(t("New role"), auth.TENANT_ROLES, format_func=tf)
            if st.form_submit_button(t("Apply"), type="primary"):
                target = db.one("SELECT * FROM users WHERE id = ? AND company_id = ?", (int(uid), cid))  # isolation check
                if not target:
                    st.error("Not found")
                elif action == "reset":
                    pw = auth.temp_password()
                    db.execute("UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = NULL WHERE id = ?", (auth.hash_password(pw), target["id"]))
                    audit.log(cid, user["email"], "password_reset_by_admin", "user", target["email"])
                    st.success(t("Temporary password (shown once):"))
                    st.code(pw)
                elif action == "role":
                    db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, target["id"]))
                    audit.log(cid, user["email"], "role_changed", "user", target["email"], f"{target['role']}→{new_role}")
                    st.success(t("Role changed."))
                else:
                    db.execute("UPDATE users SET active = ? WHERE id = ?", (1 if action == "activate" else 0, target["id"]))
                    audit.log(cid, user["email"], f"user_{action}d", "user", target["email"])
                    st.success(t("Done."))
