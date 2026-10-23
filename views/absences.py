"""Absence & availability: record unavailability and show its impact (no automatic changes)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from hub import audit, db, engine_alloc, engine_risk, events, notify, router, ui
from hub.i18n import t, tf

TYPES = ["Planned leave", "Unexpected absence", "Training time", "Other unavailability"]


def impact(cid: int, absence: dict) -> dict:
    s = date.fromisoformat(absence["start_date"])
    e = date.fromisoformat(absence["end_date"] or absence["start_date"])
    emp = db.t_get("employees", cid, absence["employee_id"])
    days = engine_alloc.working_days_overlap(s, e, s, e)
    lost = days * (emp["weekly_capacity"] or 0) / 5
    tasks = db.df("""SELECT t.*, p.code AS project_code, p.name AS project FROM tasks t JOIN projects p ON p.id = t.project_id
                     WHERE t.company_id = ? AND t.assignee_id = ? AND t.status IN ('Not Started','In Progress','Blocked','Under Review')""",
                  (cid, absence["employee_id"]))
    if not tasks.empty:
        due = pd.to_datetime(tasks["due_date"]).dt.date
        st_ = pd.to_datetime(tasks["start_date"]).dt.date
        tasks = tasks[(st_ <= e) & (due >= s - timedelta(days=0)) | ((due >= s) & (due <= e + timedelta(days=7)))]
        tasks = tasks.copy()
        tasks["near_deadline"] = pd.to_datetime(tasks["due_date"]).dt.date <= e + timedelta(days=7)
    al = db.df("""SELECT p.code, p.name, a.hours_per_week FROM allocations a JOIN projects p ON p.id = a.project_id
                  WHERE a.company_id = ? AND a.employee_id = ? AND p.archived = 0""", (cid, absence["employee_id"]))
    if not al.empty:
        al["hours_lost"] = (al["hours_per_week"] / 5 * days).round(1)
    return {"employee": emp, "days": days, "hours_lost": round(lost, 1), "tasks": tasks, "projects": al}


def show_impact(cid: int, absence: dict) -> None:
    im = impact(cid, absence)
    ui.kpi_row([
        (t("Working days unavailable"), im["days"], f"{absence['start_date']} → {absence['end_date']}", "warn"),
        (t("Capacity lost"), f"{im['hours_lost']:.0f} h", im["employee"]["name"], "warn"),
        (t("Affected tasks"), len(im["tasks"]), t("{n} near their deadline", n=int(im["tasks"]["near_deadline"].sum()) if not im["tasks"].empty else 0),
         "bad" if len(im["tasks"]) else "good"),
        (t("Affected projects"), len(im["projects"]), "", "neutral"),
    ])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**" + t("Impact on project capacity") + "**")
        ui.table(im["projects"], {"code": "Project", "name": "Name", "hours_per_week": "h/week", "hours_lost": "Hours lost"})
    with c2:
        st.markdown("**" + t("Affected tasks") + "**")
        ui.table(im["tasks"], {"code": "Task", "project_code": "Project", "due_date": "Due", "priority": "Priority", "completion": "%",
                               "near_deadline": "Deadline in/just after absence"}, translate_values=("priority",))
    if not im["tasks"].empty:
        st.markdown("**" + t("Recommended alternative resources (manager decides)") + "**")
        for _, tk in im["tasks"].head(5).iterrows():
            c = engine_alloc.candidates(cid, tk["required_skills"], absence["employee_id"], 4, limit=3)
            names = ", ".join(f"{r['name']} ({r['spare_hours']:.0f}h {t('free')})" for _, r in c.iterrows()) if not c.empty else t("none available - consider subcontractor or new date")
            st.markdown(f"- **{tk['code']}** ({tk['required_skills'] or '-'}): {names}")
        st.caption(t("Nothing has been reassigned and no deadline has been changed. Use Resource allocation → Overcapacity analysis to request a reassignment."))
        router.link("allocation", t("Open Resource allocation (reassign, subcontractor, hiring or deadline request)") + " →")


def render(ctx: dict) -> None:
    cid, edit, user = ctx["cid"], ctx["can_edit"], ctx["user"]
    ui.page_header("absences", t("Absences & availability"), t("Record unavailability and see the impact on projects"))
    emps = db.t_rows("employees", cid, "active = 1", order="name")
    tabs = st.tabs(["➕ " + t("Record absence"), "📋 " + t("Absences"), "🔎 " + t("Impact analysis")])
    with tabs[0]:
        if not edit:
            st.info(t("Read-only for your role."))
        else:
            with st.form("abs"):
                c1, c2 = st.columns(2)
                eid = c1.selectbox(t("Employee"), [e["id"] for e in emps], format_func=lambda i: next(f"{e['name']} · {e['department']}" for e in emps if e["id"] == i))
                typ = c2.selectbox(t("Type"), TYPES, format_func=tf)
                sd = c1.date_input(t("From"), date.today())
                ed = c2.date_input(t("To"), date.today() + timedelta(days=4))
                reason = st.text_input(t("Note (avoid sensitive details such as medical information)"))
                if st.form_submit_button(t("Record absence"), type="primary"):
                    if ed < sd:
                        st.error(t("End date cannot be before start date."))
                    else:
                        aid = db.t_insert("absences", cid, {"employee_id": eid, "absence_type": typ, "start_date": str(sd), "end_date": str(ed),
                                                            "reason": reason, "created_by": user["email"], "created_at": db.now()})
                        emp = db.t_get("employees", cid, eid)
                        audit.log(cid, user["email"], "absence_recorded", "employee", emp["emp_code"], f"{typ} {sd}→{ed}")
                        res = engine_risk.run(cid)
                        a = db.t_get("absences", cid, aid)
                        im = impact(cid, a)
                        mgr = db.t_get("employees", cid, emp["manager_id"]) if emp["manager_id"] else None
                        body = (f"{emp['name']} unavailable ({typ}) {sd} to {ed}. {len(im['tasks'])} task(s) affected, "
                                f"{im['hours_lost']}h capacity lost. Manager: {mgr['name'] if mgr else '-'}.")
                        events.emit(cid, "absence", f"Absence recorded: {emp['name']}", body,
                                    employees=[emp["manager_id"]] if emp["manager_id"] else [], roles=["Project Manager"],
                                    page="absences", exclude_user=user["id"])
                        events.emit(cid, "absence", "Your absence has been recorded", f"{typ}: {sd} → {ed}.",
                                    employees=[eid], page="my_work", exclude_user=user["id"], email=False)
                        out = ["NTFY / e-mail: queued (see Notifications log)"]
                        st.session_state["last_absence"] = aid
                        st.success(t("Absence recorded. Workload and risks recalculated ({c} new, {u} updated).", c=res["created"], u=res["updated"]))
                        if out:
                            st.caption(" · ".join(out))
            if st.session_state.get("last_absence"):
                a = db.t_get("absences", cid, st.session_state["last_absence"])
                if a:
                    st.subheader(t("Impact of the absence just recorded"))
                    show_impact(cid, a)
    with tabs[1]:
        ab = db.df("""SELECT a.*, e.name, e.department FROM absences a JOIN employees e ON e.id = a.employee_id
                      WHERE a.company_id = ? ORDER BY a.start_date DESC""", (cid,))
        if not ab.empty:
            today = date.today()
            ab["when"] = ab.apply(lambda r: "Current" if r["start_date"] <= str(today) <= r["end_date"] else ("Upcoming" if r["start_date"] > str(today) else "Past"), axis=1)
        ui.table(ab, {"name": "Employee", "department": "Department", "absence_type": "Type", "start_date": "From", "end_date": "To",
                      "when": "When", "reason": "Note", "created_by": "Recorded by"}, translate_values=("absence_type", "when"))
        if edit and not ab.empty:
            aid = st.selectbox(t("Cancel an absence"), ab["id"].tolist(), format_func=lambda i: f"{ab.set_index('id').loc[i, 'name']} · {ab.set_index('id').loc[i, 'start_date']}")
            if st.button(t("Cancel absence")):
                db.t_delete("absences", cid, int(aid))
                audit.log(cid, user["email"], "absence_cancelled", "absence", aid)
                engine_risk.run(cid)
                st.rerun()
    with tabs[2]:
        ab = db.df("""SELECT a.*, e.name FROM absences a JOIN employees e ON e.id = a.employee_id WHERE a.company_id = ?
                      AND a.end_date >= ? ORDER BY a.start_date""", (cid, str(date.today())))
        if ab.empty:
            st.info(t("No current or upcoming absences."))
        else:
            aid = st.selectbox(t("Absence"), ab["id"].tolist(),
                               format_func=lambda i: f"{ab.set_index('id').loc[i, 'name']} · {tf(ab.set_index('id').loc[i, 'absence_type'])} · {ab.set_index('id').loc[i, 'start_date']}")
            show_impact(cid, db.t_get("absences", cid, int(aid)))
