"""SaaS platform administration: tenants overview (counts only, no private records)."""
from __future__ import annotations

import streamlit as st

from hub import audit, db, ui
from hub.i18n import t


def render(ctx: dict) -> None:
    user = ctx["user"]
    ui.page_header("platform", t("Platform administration"), t("Registered companies (no access to their private records)"))
    c = db.df("""SELECT c.id, c.name, c.country, c.created_at, c.active, c.is_demo, c.setup_complete,
                 (SELECT COUNT(*) FROM users u WHERE u.company_id = c.id) AS users,
                 (SELECT COUNT(*) FROM employees e WHERE e.company_id = c.id AND e.active = 1) AS employees,
                 (SELECT COUNT(*) FROM projects p WHERE p.company_id = c.id) AS projects FROM companies c ORDER BY c.id""")
    ui.kpi_row([(t("Companies"), len(c), "", "neutral"), (t("Active"), int(c["active"].sum()) if not c.empty else 0, "", "good"),
                (t("Users"), int(c["users"].sum()) if not c.empty else 0, "", "neutral"),
                (t("Setup completed"), int(c["setup_complete"].sum()) if not c.empty else 0, "", "neutral")])
    ui.table(c, {"id": "ID", "name": "Company", "country": "Country", "created_at": "Created", "active": "Active", "is_demo": "Demo",
                 "setup_complete": "Setup done", "users": "Users", "employees": "Employees", "projects": "Projects"})
    if not c.empty:
        cid = st.selectbox(t("Company"), c["id"].tolist(), format_func=lambda i: c.set_index("id").loc[i, "name"])
        b1, b2, _ = st.columns([1, 1, 3])
        if b1.button(t("Suspend")):
            db.execute("UPDATE companies SET active = 0 WHERE id = ?", (int(cid),))
            audit.log(None, user["email"], "company_suspended", "company", cid)
            st.rerun()
        if b2.button(t("Re-activate")):
            db.execute("UPDATE companies SET active = 1 WHERE id = ?", (int(cid),))
            audit.log(None, user["email"], "company_activated", "company", cid)
            st.rerun()
