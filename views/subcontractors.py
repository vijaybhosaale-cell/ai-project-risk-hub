"""Subcontractor management and participation in client projects."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from hub import audit, db, engine_risk, metrics, ui
from hub.i18n import t, tf

ASSESS = ["Not started", "In progress", "Completed", "Overdue", "Not required"]
PERF = ["On track", "At risk", "Delayed", "Under review"]


def render(ctx: dict) -> None:
    cid, edit, user = ctx["cid"], ctx["can_edit"], ctx["user"]
    cur = ctx["company"]["currency"] or "EUR"
    ui.page_header("subcontractors", t("Subcontractors"), t("Contracts, access, security and delivery of third parties"))
    sb = db.df("""SELECT s.*, c.name AS client, p.code AS project_code FROM subcontractors s LEFT JOIN clients c ON c.id = s.client_id
                  LEFT JOIN projects p ON p.id = s.project_id WHERE s.company_id = ? ORDER BY s.name""", (cid,))
    risk_t = metrics.subcontractor_tasks_at_risk(cid)
    today = date.today()
    exp_soon = 0
    if not sb.empty:
        ex = pd.to_datetime(sb["access_expiry"], errors="coerce").dt.date
        exp_soon = int(((ex.notna()) & (ex <= today)).sum())
    ui.kpi_row([
        (t("Subcontractors"), len(sb), "", "neutral"),
        (t("Tasks at risk"), len(risk_t), t("overdue / due soon / blocked"), "bad" if len(risk_t) else "good"),
        (t("Security assessment missing"), int(sb["security_assessment"].isin(["Not started", "Overdue"]).sum()) if not sb.empty else 0, "", "warn"),
        (t("Access expired / no expiry"), exp_soon + (int((sb["access_expiry"].fillna("") == "").sum()) if not sb.empty else 0), t("review access"), "warn"),
    ])
    tabs = st.tabs(["🤝 " + t("Register"), "🧩 " + t("Participation in client projects"), "✏️ " + t("Add / edit")])
    with tabs[0]:
        ui.table(sb, {"name": "Subcontractor", "company_name": "Company", "contact": "Contact", "email": "E-mail", "client": "Client",
                      "project_code": "Project", "contract_start": "Contract start", "contract_end": "Contract end", "estimated_cost": "Est. cost",
                      "security_assessment": "Security assessment", "data_access": "Data access", "access_expiry": "Access expiry",
                      "incident_notification": "Incident notification", "performance": "Performance"},
                 translate_values=("security_assessment", "performance"))
        st.markdown("**" + t("Security and delivery concerns (tracked separately)") + "**")
        conc = sb[(sb["security_concern"].fillna("") != "") | (sb["delivery_concern"].fillna("") != "")] if not sb.empty else sb
        ui.table(conc, {"name": "Subcontractor", "security_concern": "Security concern", "delivery_concern": "Delivery concern",
                        "corrective_action": "Corrective action / replacement plan"})
    with tabs[1]:
        tk = db.df("""SELECT t.code, t.title, t.due_date, t.status, t.completion, p.code AS project, c.name AS client, s.name AS subcontractor
                      FROM tasks t JOIN subcontractors s ON s.id = t.subcontractor_id JOIN projects p ON p.id = t.project_id
                      LEFT JOIN clients c ON c.id = p.client_id WHERE t.company_id = ? ORDER BY t.due_date""", (cid,))
        if not tk.empty:
            due = pd.to_datetime(tk["due_date"]).dt.date
            open_ = tk["status"].isin(["Not Started", "In Progress", "Blocked", "Under Review"])
            tk["risk"] = ""
            tk.loc[open_ & (due < today), "risk"] = "Overdue"
            tk.loc[open_ & (tk["risk"] == "") & (tk["status"] == "Blocked"), "risk"] = "Blocked"
            tk.loc[open_ & (tk["risk"] == "") & ((due - today).apply(lambda d: d.days) <= 7) & (tk["completion"] < 50), "risk"] = "Due soon, < 50%"
        ui.table(tk, {"subcontractor": "Subcontractor", "client": "Client", "project": "Project", "code": "Task", "title": "Title",
                      "due_date": "Deadline", "status": "Status", "completion": "%", "risk": "Delivery risk"},
                 translate_values=("status", "risk"))
    with tabs[2]:
        if not edit:
            st.info(t("Read-only for your role."))
        else:
            opts = [None] + sb["id"].tolist() if not sb.empty else [None]
            sid = st.selectbox(t("Subcontractor"), opts, format_func=lambda i: t("New subcontractor") if i is None else sb.set_index("id").loc[i, "name"])
            s = db.t_get("subcontractors", cid, int(sid)) if sid else {}
            projects = db.t_rows("projects", cid, "archived = 0")
            with st.form(f"sub_{sid}"):
                c1, c2, c3 = st.columns(3)
                name = c1.text_input(t("Name") + " *", value=s.get("name", ""))
                comp = c2.text_input(t("Company"), value=s.get("company_name", "") or "")
                contact = c3.text_input(t("Contact"), value=s.get("contact", "") or "")
                email = c1.text_input(t("E-mail"), value=s.get("email", "") or "")
                cs = c2.date_input(t("Contract start"), date.fromisoformat(s["contract_start"]) if s.get("contract_start") else today)
                ce = c3.date_input(t("Contract end"), date.fromisoformat(s["contract_end"]) if s.get("contract_end") else today)
                pids = [None] + [p["id"] for p in projects]
                pid = c1.selectbox(t("Project"), pids, index=pids.index(s.get("project_id")) if s.get("project_id") in pids else 0,
                                   format_func=lambda i: "—" if i is None else next(f"{p['code']} · {p['name']}" for p in projects if p["id"] == i))
                cost = c2.number_input(t("Estimated cost") + f" ({cur})", 0.0, value=float(s.get("estimated_cost") or 0), step=1000.0)
                sa = c3.selectbox(t("Security assessment"), ASSESS, index=ASSESS.index(s.get("security_assessment", "Not started")) if s.get("security_assessment") in ASSESS else 0, format_func=tf)
                da = c1.text_input(t("Data access permissions"), value=s.get("data_access", "") or "")
                ax = c2.date_input(t("Access expiry"), date.fromisoformat(s["access_expiry"]) if s.get("access_expiry") else None)
                perf = c3.selectbox(t("Performance"), PERF, index=PERF.index(s.get("performance", "On track")) if s.get("performance") in PERF else 0, format_func=tf)
                obl = st.text_input(t("Contractual obligations"), value=s.get("obligations", "") or "")
                inc = st.text_input(t("Incident notification requirements"), value=s.get("incident_notification", "") or "")
                sc = st.text_input(t("Security concern"), value=s.get("security_concern", "") or "")
                dc = st.text_input(t("Delivery concern"), value=s.get("delivery_concern", "") or "")
                ca = st.text_area(t("Corrective action or replacement plan"), value=s.get("corrective_action", "") or "")
                if st.form_submit_button(t("Save subcontractor"), type="primary"):
                    if not name.strip():
                        st.error(t("Name is required."))
                    else:
                        client_id = next((p["client_id"] for p in projects if p["id"] == pid), None)
                        data = {"name": name, "company_name": comp, "contact": contact, "email": email, "contract_start": str(cs), "contract_end": str(ce),
                                "project_id": pid, "client_id": client_id, "estimated_cost": cost, "security_assessment": sa, "data_access": da,
                                "access_expiry": str(ax) if ax else "", "performance": perf, "obligations": obl, "incident_notification": inc,
                                "security_concern": sc, "delivery_concern": dc, "corrective_action": ca}
                        if sid:
                            db.t_update("subcontractors", cid, int(sid), data)
                        else:
                            db.t_insert("subcontractors", cid, data)
                        audit.log(cid, user["email"], "subcontractor_saved", "subcontractor", sid or name, ca[:200])
                        engine_risk.run(cid)
                        st.success(t("Saved."))
                        st.rerun()
