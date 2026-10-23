"""Personal workspace for employees and subcontractors: own tasks and training."""
from __future__ import annotations

import streamlit as st

from hub import db, engine_alloc, ui
from hub.i18n import t, tf
from views.tasks import STATUSES, save_task

SELF_STATUSES = ["Not Started", "In Progress", "Blocked", "Under Review", "Completed"]


def render(ctx: dict) -> None:
    cid, user = ctx["cid"], ctx["user"]
    ui.page_header("my_work", t("My work"), t("Your tasks, progress and training"))
    if user.get("subcontractor_id"):
        where, param = "t.subcontractor_id = ?", user["subcontractor_id"]
        sub = db.t_get("subcontractors", cid, user["subcontractor_id"])
        st.caption(t("Subcontractor") + f": **{sub['name'] if sub else '-'}** · " + t("You only see the tasks assigned to your company."))
    elif user.get("employee_id"):
        where, param = "t.assignee_id = ?", user["employee_id"]
        wl = engine_alloc.workload(cid)
        me = wl[wl["employee_id"] == user["employee_id"]]
        if not me.empty:
            r = me.iloc[0]
            ui.kpi_row([
                (t("My capacity"), f"{r['capacity']:.0f} h", t("per week"), "neutral"),
                (t("Allocated"), f"{r['allocated']:.0f} h", r["project_list"], "neutral"),
                (t("Workload"), f"{r['utilisation']:.0f}%", tf(r["band"]), "bad" if r["band"] == "Overcapacity" else "warn" if r["band"] == "High" else "good"),
                (t("Overdue tasks"), int(r["overdue_tasks"]), t("{n} due soon", n=int(r["upcoming_deadlines"])), "bad" if r["overdue_tasks"] else "good"),
            ])
            if r["band"] == "Overcapacity":
                st.warning(t("You are allocated above your capacity. Your manager has been shown recommendations; talk to them before taking on more work."))
    else:
        st.info(t("Your account is not linked to an employee or subcontractor record. Ask your administrator."))
        return
    tasks = db.df(f"""SELECT t.*, p.code AS project_code FROM tasks t JOIN projects p ON p.id = t.project_id
                      WHERE t.company_id = ? AND {where} ORDER BY t.due_date""", (cid, param))
    st.subheader(t("My tasks"))
    ui.table(tasks, {"code": "ID", "project_code": "Project", "title": "Title", "start_date": "Start", "due_date": "Due",
                     "priority": "Priority", "status": "Status", "completion": "%", "actual_hours": "Actual h"},
             translate_values=("priority", "status"))
    open_t = tasks[tasks["status"].isin(["Not Started", "In Progress", "Blocked", "Under Review"])] if not tasks.empty else tasks
    if not open_t.empty:
        code = st.selectbox(t("Update progress on"), open_t["code"].tolist(), format_func=lambda c: f"{c} · {open_t.set_index('code').loc[c, 'title']}")
        task = db.one("SELECT * FROM tasks WHERE company_id = ? AND code = ?", (cid, code))
        with st.form(f"my_{code}"):
            c1, c2, c3 = st.columns(3)
            stt = c1.selectbox(t("Status"), SELF_STATUSES, index=SELF_STATUSES.index(task["status"]) if task["status"] in SELF_STATUSES else 0, format_func=tf)
            comp = c2.slider(t("Completion %"), 0, 100, int(task["completion"] or 0), 5)
            ah = c3.number_input(t("Actual hours"), 0.0, value=float(task["actual_hours"] or 0), step=1.0)
            note = st.text_input(t("Comment (e.g. why blocked)"))
            if st.form_submit_button(t("Save progress"), type="primary"):
                ch = save_task(ctx, task, {"status": stt, "completion": 100 if stt == "Completed" else comp, "actual_hours": ah}, note)
                st.success(t("Saved: {c}", c=", ".join(ch) if ch else t("no change")))
        st.caption(t("Deadlines, priorities and assignment are managed by your project manager."))
    if user.get("employee_id"):
        st.subheader(t("My training"))
        tr = db.df("""SELECT tr.name, ta.due_date, ta.status, ta.completion FROM training_assignments ta JOIN trainings tr ON tr.id = ta.training_id
                      WHERE ta.company_id = ? AND ta.employee_id = ?""", (cid, user["employee_id"]))
        ui.table(tr, {"name": "Course", "due_date": "Due", "status": "Status", "completion": "%"}, translate_values=("status",))
    _ = STATUSES
