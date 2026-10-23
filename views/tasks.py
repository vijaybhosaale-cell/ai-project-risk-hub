"""Task management with history, flags and manager controls."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from hub import audit, db, engine_risk, ui
from hub.i18n import t, tf

STATUSES = ["Not Started", "In Progress", "Blocked", "Under Review", "Completed", "Cancelled"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
DIRECT_REASSIGN = {"Company Administrator", "Project Manager"}


def load(cid: int) -> pd.DataFrame:
    d = db.df("""SELECT t.*, p.code AS project_code, e.name AS assignee, s.name AS subcontractor FROM tasks t
                 JOIN projects p ON p.id = t.project_id LEFT JOIN employees e ON e.id = t.assignee_id
                 LEFT JOIN subcontractors s ON s.id = t.subcontractor_id WHERE t.company_id = ? AND p.archived = 0
                 ORDER BY t.due_date""", (cid,))
    if d.empty:
        return d
    today = date.today()
    due = pd.to_datetime(d["due_date"]).dt.date
    open_ = d["status"].isin(["Not Started", "In Progress", "Blocked", "Under Review"])
    d["flag"] = ""
    d.loc[open_ & (due < today), "flag"] = "Overdue"
    d.loc[open_ & (d["flag"] == "") & (d["status"] == "Blocked"), "flag"] = "Blocked"
    unlikely = open_ & (d["flag"] == "") & (due <= today + timedelta(days=7)) & (d["completion"] < 50)
    d.loc[unlikely, "flag"] = "Unlikely to meet deadline"
    return d


def save_task(ctx, task: dict, data: dict, reason: str) -> list[str]:
    cid, user = ctx["cid"], ctx["user"]
    changed = []
    for k, v in data.items():
        old = task.get(k)
        if str(old if old is not None else "") != str(v if v is not None else ""):
            changed.append(k)
            db.t_insert("task_history", cid, {"task_id": task["id"], "field": k, "old_value": "" if old is None else str(old),
                                              "new_value": "" if v is None else str(v), "reason": reason, "user": user["email"], "ts": db.now()})
    if changed:
        db.t_update("tasks", cid, task["id"], {k: data[k] for k in changed})
        audit.log(cid, user["email"], "task_updated", "task", task["code"], ", ".join(changed) + (f" ({reason})" if reason else ""))
        engine_risk.run(cid)
    return changed


def render(ctx: dict) -> None:
    cid, edit, role, user = ctx["cid"], ctx["can_edit"], ctx["role"], ctx["user"]
    ui.page_header("tasks", t("Tasks"), t("All tasks across projects, with review flags and change history"))
    d = load(cid)
    tabs = st.tabs(["🗂️ " + t("Task list"), "✏️ " + t("Edit task"), "➕ " + t("New task"), "🕓 " + t("History")])
    with tabs[0]:
        if d.empty:
            st.info(t("No tasks yet."))
        else:
            f = st.columns(4)
            pj = f[0].multiselect(t("Project"), sorted(d["project_code"].unique()), placeholder=t("All"))
            stt = f[1].multiselect(t("Status"), STATUSES, placeholder=t("All"), format_func=tf)
            who = f[2].multiselect(t("Assigned"), sorted(d["assignee"].dropna().unique()), placeholder=t("All"))
            fl = f[3].multiselect(t("Flag"), ["Overdue", "Blocked", "Unlikely to meet deadline"], placeholder=t("All"), format_func=tf)
            x = d.copy()
            if pj:
                x = x[x["project_code"].isin(pj)]
            if stt:
                x = x[x["status"].isin(stt)]
            if who:
                x = x[x["assignee"].isin(who)]
            if fl:
                x = x[x["flag"].isin(fl)]
            n_flag = int((d["flag"] != "").sum())
            st.caption(t("{n} task(s) flagged for review (overdue, blocked or unlikely to meet the deadline: due within 7 days and < 50% complete).", n=n_flag))
            ui.table(x, {"code": "ID", "project_code": "Project", "title": "Title", "assignee": "Assigned", "subcontractor": "Subcontractor",
                         "start_date": "Start", "due_date": "Due", "est_hours": "Est. h", "actual_hours": "Actual h", "priority": "Priority",
                         "status": "Status", "completion": "%", "flag": "Flag"},
                     translate_values=("priority", "status", "flag"), height=480)
    with tabs[1]:
        if d.empty or not edit:
            st.info(t("Read-only for your role.") if not edit else t("No tasks yet."))
        else:
            code = st.selectbox(t("Task"), d["code"].tolist(), format_func=lambda c: f"{c} · {d.set_index('code').loc[c, 'title']}")
            task = db.one("SELECT * FROM tasks WHERE company_id = ? AND code = ?", (cid, code))
            emps = db.t_rows("employees", cid, "active = 1", order="name")
            with st.form(f"task_edit_{code}"):
                c1, c2, c3 = st.columns(3)
                status = c1.selectbox(t("Status"), STATUSES, index=STATUSES.index(task["status"]), format_func=tf)
                comp = c2.slider(t("Completion %"), 0, 100, int(task["completion"] or 0), 5)
                prio = c3.selectbox(t("Priority"), PRIORITIES, index=PRIORITIES.index(task["priority"]), format_func=tf)
                sd = c1.date_input(t("Start date"), date.fromisoformat(task["start_date"]))
                dd = c2.date_input(t("Due date"), date.fromisoformat(task["due_date"]))
                ah = c3.number_input(t("Actual hours"), 0.0, value=float(task["actual_hours"] or 0), step=1.0)
                eh = c1.number_input(t("Estimated hours"), 0.0, value=float(task["est_hours"] or 0), step=1.0)
                crit = c2.checkbox(t("Critical task"), value=bool(task["is_critical"]))
                skills = c3.text_input(t("Required skills"), value=task["required_skills"] or "")
                ids = [None] + [e["id"] for e in emps]
                can_direct = role in DIRECT_REASSIGN
                assignee = st.selectbox(t("Assigned employee") + ("" if can_direct else " (" + t("change via reassignment request") + ")"), ids,
                                        index=ids.index(task["assignee_id"]) if task["assignee_id"] in ids else 0,
                                        format_func=lambda i: "—" if i is None else next(e["name"] for e in emps if e["id"] == i),
                                        disabled=not can_direct)
                reason = st.text_input(t("Reason (required when the due date or assignee changes)"))
                if st.form_submit_button(t("Save task"), type="primary"):
                    if dd < sd:
                        st.error(t("Due date cannot be before start date."))
                    elif (str(dd) != task["due_date"] or (can_direct and assignee != task["assignee_id"])) and not reason.strip():
                        st.error(t("Please give a reason for the deadline or assignee change."))
                    else:
                        data = {"status": status, "completion": 100 if status == "Completed" else comp, "priority": prio,
                                "start_date": str(sd), "due_date": str(dd), "actual_hours": ah, "est_hours": eh,
                                "is_critical": int(crit), "required_skills": skills}
                        if can_direct:
                            data["assignee_id"] = assignee
                        ch = save_task(ctx, task, data, reason)
                        st.success(t("Saved: {c}", c=", ".join(ch) if ch else t("no change")))
            if role not in DIRECT_REASSIGN:
                st.caption(t("Team leaders request reassignments from the Resource allocation page; a project manager approves them."))
    with tabs[2]:
        if not edit:
            st.info(t("Read-only for your role."))
        else:
            projects = db.t_rows("projects", cid, "archived = 0 AND status NOT IN ('Completed','Cancelled')")
            emps = db.t_rows("employees", cid, "active = 1", order="name")
            subs = db.t_rows("subcontractors", cid)
            with st.form("task_new"):
                c1, c2 = st.columns(2)
                pid = c1.selectbox(t("Project"), [p["id"] for p in projects], format_func=lambda i: next(f"{p['code']} · {p['name']}" for p in projects if p["id"] == i))
                title = c2.text_input(t("Task title") + " *")
                desc = st.text_area(t("Description"))
                asg = c1.selectbox(t("Assigned employee"), [None] + [e["id"] for e in emps],
                                   format_func=lambda i: "—" if i is None else next(e["name"] for e in emps if e["id"] == i))
                sub = c2.selectbox(t("Subcontractor (optional)"), [None] + [s["id"] for s in subs],
                                   format_func=lambda i: "—" if i is None else next(s["name"] for s in subs if s["id"] == i))
                sd = c1.date_input(t("Start date"), key="nt_sd")
                dd = c2.date_input(t("Due date"), date.today() + timedelta(days=14), key="nt_dd")
                eh = c1.number_input(t("Estimated hours"), 0.0, value=16.0)
                prio = c2.selectbox(t("Priority"), PRIORITIES, index=1, format_func=tf)
                skills = c1.text_input(t("Required skills"))
                dep_opts = d[d["project_id"].isin([p["id"] for p in projects])] if not d.empty else d
                deps = c2.multiselect(t("Depends on"), dep_opts["id"].tolist() if not dep_opts.empty else [],
                                      format_func=lambda i: dep_opts.set_index("id").loc[i, "code"])
                crit = st.checkbox(t("Critical task"))
                if st.form_submit_button(t("Create task"), type="primary"):
                    if not title.strip() or dd < sd:
                        st.error(t("Title required and due date must be after start date."))
                    else:
                        pcode = next(p["code"] for p in projects if p["id"] == pid)
                        n = (db.scalar("SELECT COUNT(*) FROM tasks WHERE company_id=? AND project_id=?", (cid, pid)) or 0) + 1
                        code = f"{pcode}-T{n:02d}"
                        while db.scalar("SELECT COUNT(*) FROM tasks WHERE company_id=? AND code=?", (cid, code)):
                            n += 1
                            code = f"{pcode}-T{n:02d}"
                        db.t_insert("tasks", cid, {"code": code, "project_id": pid, "title": title, "description": desc, "assignee_id": asg,
                                                   "subcontractor_id": sub, "start_date": str(sd), "due_date": str(dd), "est_hours": eh,
                                                   "priority": prio, "status": "Not Started", "completion": 0, "required_skills": skills,
                                                   "depends_on": ",".join(str(x) for x in deps), "is_critical": int(crit)})
                        audit.log(cid, user["email"], "task_created", "task", code, title)
                        engine_risk.run(cid)
                        st.success(t("Task {c} created.", c=code))
    with tabs[3]:
        h = db.df("""SELECT h.ts, t.code, h.field, h.old_value, h.new_value, h.reason, h.user FROM task_history h
                     JOIN tasks t ON t.id = h.task_id WHERE h.company_id = ? ORDER BY h.id DESC LIMIT 300""", (cid,))
        ui.table(h, {"ts": "When", "code": "Task", "field": "Field", "old_value": "Previous", "new_value": "New", "reason": "Reason", "user": "User"})
