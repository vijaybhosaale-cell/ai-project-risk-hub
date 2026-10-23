"""Project portfolio, project detail, create / edit / archive."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from hub import audit, db, engine_alloc, engine_risk, metrics, perms, ui
from hub.i18n import lang, t, tf

PROJECT_STATUSES = ["Planned", "Active", "On Hold", "Completed", "Cancelled"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
HEALTH_COLORS = {"On track": "#3a9a68", "At risk": "#e06c1f", "Critical": "#b3261e", "Completed": "#7fa7d9", "Cancelled": "#8a94a6"}


def project_form(ctx, p: dict | None) -> None:
    cid, user = ctx["cid"], ctx["user"]
    clients = db.t_rows("clients", cid, order="name")
    emps = db.t_rows("employees", cid, "active = 1", order="name")
    locs = db.t_rows("locations", cid, order="name")
    p = p or {}
    key = p.get("id", "new")
    with st.form(f"proj_form_{key}"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input(t("Project ID") + " *", value=p.get("code", ""))
        name = c2.text_input(t("Project name") + " *", value=p.get("name", ""))
        status = c3.selectbox(t("Status"), PROJECT_STATUSES, index=PROJECT_STATUSES.index(p.get("status", "Active")), format_func=tf)
        desc = st.text_area(t("Description"), value=p.get("description", "") or "")
        cl_ids = [None] + [c["id"] for c in clients]
        client = c1.selectbox(t("Client"), cl_ids, index=cl_ids.index(p.get("client_id")) if p.get("client_id") in cl_ids else 0,
                              format_func=lambda i: "—" if i is None else next(c["name"] for c in clients if c["id"] == i))
        em_ids = [None] + [e["id"] for e in emps]
        mgr = c2.selectbox(t("Project manager"), em_ids, index=em_ids.index(p.get("manager_id")) if p.get("manager_id") in em_ids else 0,
                           format_func=lambda i: "—" if i is None else next(e["name"] for e in emps if e["id"] == i))
        lo_ids = [None] + [x["id"] for x in locs]
        loc = c3.selectbox(t("Location"), lo_ids, index=lo_ids.index(p.get("location_id")) if p.get("location_id") in lo_ids else 0,
                           format_func=lambda i: "—" if i is None else next(x["name"] for x in locs if x["id"] == i))
        sd = c1.date_input(t("Start date"), date.fromisoformat(p["start_date"]) if p.get("start_date") else date.today())
        ed = c2.date_input(t("End date"), date.fromisoformat(p["end_date"]) if p.get("end_date") else date.today() + timedelta(days=90))
        prio = c3.selectbox(t("Priority"), PRIORITIES, index=PRIORITIES.index(p.get("priority", "Medium")), format_func=tf)
        bud = c1.number_input(t("Approved budget"), 0.0, value=float(p.get("budget") or 0), step=1000.0)
        act = c2.number_input(t("Actual expenditure"), 0.0, value=float(p.get("actual_spend") or 0), step=1000.0)
        fc = c3.number_input(t("Forecast expenditure"), 0.0, value=float(p.get("forecast_spend") or 0), step=1000.0)
        eff = c1.number_input(t("Estimated effort (hours)"), 0.0, value=float(p.get("estimated_effort") or 0), step=10.0)
        sla = c2.text_input(t("Contract / SLA reference"), value=p.get("sla_ref", "") or "")
        est = c3.checkbox(t("Financial figures are estimates"), value=bool(p.get("financials_are_estimates", 1)))
        if st.form_submit_button(t("Save project"), type="primary"):
            if not code.strip() or not name.strip():
                st.error(t("Project ID and name are required."))
                return
            if ed < sd:
                st.error(t("End date cannot be before start date."))
                return
            data = {"code": code.strip(), "name": name.strip(), "description": desc, "client_id": client, "manager_id": mgr,
                    "location_id": loc, "start_date": str(sd), "end_date": str(ed), "status": status, "priority": prio,
                    "budget": bud, "actual_spend": act, "forecast_spend": fc, "estimated_effort": eff, "sla_ref": sla,
                    "financials_are_estimates": int(est)}
            if p.get("id"):
                db.t_update("projects", cid, p["id"], data)
                audit.log(cid, user["email"], "project_updated", "project", code)
            else:
                pid = db.t_insert("projects", cid, data)
                if mgr:
                    db.t_insert("allocations", cid, {"employee_id": mgr, "project_id": pid, "hours_per_week": 4.0, "project_role": "Project manager"})
                audit.log(cid, user["email"], "project_created", "project", code)
            engine_risk.run(cid)
            st.success(t("Project saved."))
            st.rerun()


def render(ctx: dict) -> None:
    cid, edit, role = ctx["cid"], ctx["can_edit"], ctx["role"]
    cur = ctx["company"]["currency"] or "EUR"
    ui.page_header("projects", t("Projects"), t("Portfolio health, progress, budget and risks"))
    ph = metrics.projects_health(cid)
    tabs = st.tabs(["📁 " + t("Portfolio"), "🔎 " + t("Project detail"), "➕ " + t("New project"), "🗄️ " + t("Archived")])
    with tabs[0]:
        if ph.empty:
            st.info(t("No projects yet."))
        else:
            f1, f2 = st.columns(2)
            hs = f1.multiselect(t("Health"), list(HEALTH_COLORS), placeholder=t("All"), format_func=tf)
            ls = f2.multiselect(t("Location"), sorted(ph["location"].dropna().unique()), placeholder=t("All"))
            d = ph.copy()
            if hs:
                d = d[d["health"].isin(hs)]
            if ls:
                d = d[d["location"].isin(ls)]
            ui.table(d, {"code": "ID", "name": "Project", "client": "Client", "manager": "Manager", "location": "Location",
                         "status": "Status", "priority": "Priority", "progress": "Progress %", "budget_util": "Budget used %",
                         "health": "Health", "health_reasons": "Why", "end_date": "End"},
                     translate_values=("status", "priority", "health"),
                     column_config={"progress": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)})
            st.caption(t("Progress = sum(estimated hours × completion) / sum(estimated hours), cancelled tasks excluded. Health rules: Critical = open critical risk, budget overrun or end date passed; At risk = open high risk, overdue tasks/milestones, budget ≥ warning threshold, over-allocated member or on hold."))
    with tabs[1]:
        if ph.empty:
            st.info(t("No projects yet."))
        else:
            code = st.selectbox(t("Project"), ph["code"].tolist(), format_func=lambda c: f"{c} · {ph.set_index('code').loc[c, 'name']}")
            p = ph[ph["code"] == code].iloc[0].to_dict()
            st.markdown(f"### {p['code']} · {p['name']}  " + ui.pill(p["health"], HEALTH_COLORS.get(p["health"], "#888")), unsafe_allow_html=True)
            st.caption(p.get("description") or "")
            if p["health_reasons"]:
                st.warning(t("Why") + ": " + p["health_reasons"])
            ui.kpi_row([
                (t("Progress"), f"{p['progress']:.0f}%", f"{p['start_date']} → {p['end_date']}", "neutral"),
                (t("Budget used"), f"{p['budget_util']:.0f}%", f"{ui.money(p['actual_spend'], cur)} / {ui.money(p['budget'], cur)}" +
                 (" · " + t("estimate") if p.get("financials_are_estimates") else ""), "bad" if p["budget_util"] > 100 else "warn" if p["budget_util"] >= 90 else "neutral"),
                (t("Overdue tasks"), p["overdue_tasks"], t("{n} overdue milestone(s)", n=p["overdue_milestones"]), "bad" if p["overdue_tasks"] else "good"),
                (t("Open critical / high risks"), f"{p['open_critical']} / {p['open_high']}", t("{n} over-allocated member(s)", n=p["over_team"]),
                 "bad" if p["open_critical"] else "warn" if p["open_high"] else "good"),
            ])
            st.markdown(f"**{t('Client')}:** {p.get('client') or '-'} · **{t('Manager')}:** {p.get('manager') or '-'} · "
                        f"**{t('Location')}:** {p.get('location') or '-'} · **{t('Priority')}:** {tf(p['priority'])} · **SLA:** {p.get('sla_ref') or '-'}")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**" + t("Team (hours per week on this project / total workload)") + "**")
                team = db.df("""SELECT e.id AS employee_id, e.name, a.project_role, a.hours_per_week FROM allocations a
                                JOIN employees e ON e.id = a.employee_id WHERE a.company_id = ? AND a.project_id = ?""", (cid, int(p["id"])))
                wl = engine_alloc.workload(cid)
                if not team.empty and not wl.empty:
                    team = team.merge(wl[["employee_id", "utilisation", "band"]], on="employee_id", how="left")
                ui.table(team, {"name": "Employee", "project_role": "Role", "hours_per_week": "h/week", "utilisation": "Total workload %", "band": "Band"},
                         translate_values=("band",))
                st.markdown("**" + t("Milestones") + "**")
                ms = db.t_df("milestones", cid, "project_id = ?", (int(p["id"]),), order="due_date")
                ui.table(ms, {"name": "Milestone", "due_date": "Due", "status": "Status"}, translate_values=("status",))
                if edit and not ms.empty:
                    with st.form(f"ms_{p['id']}"):
                        m1, m2 = st.columns(2)
                        mid = m1.selectbox(t("Milestone"), ms["id"].tolist(), format_func=lambda i: ms.set_index("id").loc[i, "name"])
                        mst = m2.selectbox(t("Status"), ["Planned", "In Progress", "Completed", "Missed"], format_func=tf)
                        if st.form_submit_button(t("Update milestone")):
                            db.t_update("milestones", cid, int(mid), {"status": mst})
                            audit.log(cid, ctx["user"]["email"], "milestone_updated", "milestone", mid, mst)
                            engine_risk.run(cid)
                            st.rerun()
                if edit:
                    with st.form(f"msnew_{p['id']}"):
                        m1, m2 = st.columns(2)
                        mn = m1.text_input(t("New milestone"))
                        md = m2.date_input(t("Due date"), key=f"md_{p['id']}")
                        if st.form_submit_button(t("Add milestone")) and mn.strip():
                            db.t_insert("milestones", cid, {"project_id": int(p["id"]), "name": mn, "due_date": str(md), "status": "Planned"})
                            st.rerun()
            with c2:
                st.markdown("**" + t("Tasks") + "**")
                tk = db.df("""SELECT t.code, t.title, e.name AS assignee, t.due_date, t.status, t.completion, t.priority FROM tasks t
                              LEFT JOIN employees e ON e.id = t.assignee_id WHERE t.company_id = ? AND t.project_id = ? ORDER BY t.start_date""",
                           (cid, int(p["id"])))
                ui.table(tk, {"code": "Task", "title": "Title", "assignee": "Assigned", "due_date": "Due", "status": "Status", "completion": "%"},
                         translate_values=("status",))
                st.markdown("**" + t("Risks on this project") + "**")
                rg = engine_risk.register(cid, lang())
                rg = rg[(rg["project_id"] == p["id"])] if not rg.empty else rg
                ui.table(rg, {"code": "Code", "display_title": "Risk", "score": "Score", "priority": "Priority", "status": "Status"},
                         translate_values=("priority", "status"))
                st.markdown("**" + t("Subcontractors") + "**")
                sb = db.t_df("subcontractors", cid, "project_id = ?", (int(p["id"]),))
                ui.table(sb, {"name": "Subcontractor", "security_assessment": "Security assessment", "performance": "Performance",
                              "access_expiry": "Access expiry"}, translate_values=("security_assessment", "performance"))
            if edit:
                with st.expander("✏️ " + t("Edit project")):
                    project_form(ctx, db.t_get("projects", cid, int(p["id"])))
                b1, _ = st.columns([1, 4])
                if b1.button("🗄️ " + t("Archive project"), key=f"arch_{p['id']}"):
                    db.t_update("projects", cid, int(p["id"]), {"archived": 1})
                    audit.log(cid, ctx["user"]["email"], "project_archived", "project", p["code"])
                    engine_risk.run(cid)
                    st.rerun()
            if role in perms.CONTRACT_VALUE_ROLES:
                pass
    with tabs[2]:
        if edit:
            project_form(ctx, None)
        else:
            st.info(t("Read-only for your role."))
    with tabs[3]:
        arch = db.t_df("projects", cid, "archived = 1")
        ui.table(arch, {"code": "ID", "name": "Project", "status": "Status", "end_date": "End"}, translate_values=("status",))
        if edit and not arch.empty:
            aid = st.selectbox(t("Restore project"), arch["id"].tolist(), format_func=lambda i: arch.set_index("id").loc[i, "name"])
            if st.button(t("Restore")):
                db.t_update("projects", cid, int(aid), {"archived": 0})
                audit.log(cid, ctx["user"]["email"], "project_restored", "project", aid)
                st.rerun()
    _ = pd
