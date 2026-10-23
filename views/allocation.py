"""Multi-project resource allocation: matrix, overcapacity analysis, edits and approvals."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from hub import audit, db, engine_alloc, engine_risk, notify, ui
from hub.i18n import t, tf

APPROVERS = {"Company Administrator", "Project Manager", "Team Leader"}


def request_reassignment(ctx, task: dict, to_emp: int, reason: str) -> None:
    cid = ctx["cid"]
    rid = db.t_insert("reassignments", cid, {"task_id": task["id"], "from_employee": task["assignee_id"], "to_employee": to_emp,
                                             "reason": reason, "status": "Pending", "requested_by": ctx["user"]["email"],
                                             "created_at": db.now()})
    audit.log(cid, ctx["user"]["email"], "reassignment_requested", "task", task["id"], f"to employee {to_emp}: {reason}")
    notify.notify(cid, "reassignment", f"Reassignment approval needed: {task['code']}",
                  f"{ctx['user']['name']} requested reassignment of {task['code']} ({task['title']}). Reason: {reason}")
    _ = rid


def decide(ctx, req: dict, approve: bool) -> None:
    cid = ctx["cid"]
    db.t_update("reassignments", cid, req["id"], {"status": "Approved" if approve else "Rejected",
                                                   "decided_by": ctx["user"]["email"], "decided_at": db.now()})
    if approve:
        task = db.t_get("tasks", cid, req["task_id"])
        db.t_update("tasks", cid, task["id"], {"assignee_id": req["to_employee"]})
        db.t_insert("task_history", cid, {"task_id": task["id"], "field": "assignee_id", "old_value": str(task["assignee_id"]),
                                          "new_value": str(req["to_employee"]), "reason": f"Approved reassignment: {req['reason']}",
                                          "user": ctx["user"]["email"], "ts": db.now()})
    audit.log(cid, ctx["user"]["email"], "reassignment_" + ("approved" if approve else "rejected"), "task", req["task_id"])
    engine_risk.run(cid)


def _style_band(v):
    return f"background-color: {ui.BAND_COLORS.get(v, '#fff')}; color: white; font-weight:600"


def render(ctx: dict) -> None:
    cid, edit = ctx["cid"], ctx["can_edit"]
    th = db.settings(cid)["thresholds"]
    ui.page_header("allocation", t("Resource allocation"),
                   t("One capacity per employee, counted across all projects - never separately per project."))
    with st.expander("📐 " + t("How the numbers are calculated")):
        st.markdown(
            f"- **{t('Capacity')}**: {t('weekly hours from the employee profile (configurable per person).')}\n"
            f"- **{t('Effective capacity')}**: {t('capacity minus recorded absence in the current week.')}\n"
            f"- **{t('Allocated')}**: {t('sum of weekly hours across ALL active projects.')}\n"
            f"- **{t('Workload %')}** = {t('allocated / effective capacity.')}\n"
            f"- **{t('Bands')}**: < {th['under']}% {tf('Underutilised')} · {th['under']}–{th['high']}% {tf('Healthy')} · "
            f"{th['high']}–{th['over']}% {tf('High')} · > {th['over']}% {tf('Overcapacity')} ({t('editable in Company settings')}).\n"
            f"- **{t('Delay exposure')}** = {t('over-allocated hours / (capacity / 5) = working days per week that cannot be delivered.')}")

    wl = engine_alloc.workload(cid)
    if wl.empty:
        st.info(t("No employees yet. Add employees first."))
        return
    f1, f2, f3 = st.columns(3)
    loc = f1.multiselect(t("Location"), sorted(wl["location"].dropna().unique()), placeholder=t("All"))
    dep = f2.multiselect(t("Department"), sorted(wl["department"].dropna().unique()), placeholder=t("All"))
    bands = f3.multiselect(t("Workload band"), ["Overcapacity", "High", "Healthy", "Underutilised"], placeholder=t("All"), format_func=tf)
    w = wl.copy()
    if loc:
        w = w[w["location"].isin(loc)]
    if dep:
        w = w[w["department"].isin(dep)]
    if bands:
        w = w[w["band"].isin(bands)]

    ui.kpi_row([
        (t("Employees"), len(w), t("in filter"), "neutral"),
        (t("Over capacity"), int((w["band"] == "Overcapacity").sum()), f"> {th['over']}%", "bad" if (w["band"] == "Overcapacity").any() else "good"),
        (t("High workload"), int((w["band"] == "High").sum()), f"{th['high']}–{th['over']}%", "warn"),
        (t("Over-allocated hours / week"), f"{w['over_hours'].sum():.0f} h", t("total across employees"), "bad" if w["over_hours"].sum() else "good"),
    ])

    tabs = st.tabs(["🧮 " + t("Allocation matrix"), "🚨 " + t("Overcapacity analysis"), "✏️ " + t("Edit allocations"), "✅ " + t("Approvals")])

    # ---- matrix ---------------------------------------------------------------
    with tabs[0]:
        m = engine_alloc.matrix(cid)
        base = w.set_index("name")[["location", "capacity", "effective_capacity", "allocated", "remaining", "utilisation", "band"]]
        mm = base.join(m, how="left").fillna(0) if not m.empty else base
        proj_cols = [c for c in mm.columns if c not in base.columns]
        mm = mm.sort_values("utilisation", ascending=False)
        disp = mm.reset_index().rename(columns={"name": t("Employee"), "location": t("Location"), "capacity": t("Capacity"),
                                                "effective_capacity": t("Effective"), "allocated": t("Allocated"),
                                                "remaining": t("Remaining"), "utilisation": t("Workload %"), "band": t("Band")})
        disp[t("Band")] = disp[t("Band")].map(tf)
        inv = {tf(k): v for k, v in ui.BAND_COLORS.items()}
        sty = disp.style.map(lambda v: f"background-color:{inv.get(v, '')};color:white;font-weight:600" if v in inv else "",
                             subset=[t("Band")]).format(precision=0)
        sty = sty.map(lambda v: "background-color:#eef4fb" if isinstance(v, (int, float)) and v > 0 else "color:#c3cad5",
                      subset=proj_cols)
        st.caption(t("Rows = employees, columns = projects (hours per week). Sorted by workload."))
        st.dataframe(sty, hide_index=True, height=520)

    # ---- overcapacity analysis ------------------------------------------------
    with tabs[1]:
        over = w[w["band"].isin(["Overcapacity", "High"])].sort_values("utilisation", ascending=False)
        names = over["name"].tolist() + [n for n in w.sort_values("name")["name"] if n not in over["name"].tolist()]
        if not names:
            st.success(t("Nobody in this filter is above the high-workload threshold."))
        else:
            sel = st.selectbox(t("Employee"), names, format_func=lambda n: f"{n} · {w.set_index('name').loc[n, 'utilisation']:.0f}%")
            eid = int(w[w["name"] == sel]["employee_id"].iloc[0])
            det = engine_alloc.overcapacity_detail(cid, eid)
            r = det["summary"]
            if r["over_hours"] > 0:
                st.error(f"⚠️ {t('Overcapacity warning')}: {sel} — {r['allocated']:.0f} h / {r['effective_capacity']:.0f} h "
                         f"({r['utilisation']:.0f}%), **+{r['over_hours']:.0f} h {t('per week above capacity')}**.")
            ui.kpi_row([
                (t("Capacity"), f"{r['capacity']:.0f} h", t("{d} absent day(s) this week", d=r["absent_days_this_week"]), "neutral"),
                (t("Allocated (all projects)"), f"{r['allocated']:.0f} h", r["project_list"], "neutral"),
                (t("Remaining"), f"{r['remaining']:.0f} h", tf(r["band"]), "bad" if r["remaining"] < 0 else "good"),
                (t("Delay exposure"), f"{r['delay_exposure_days_per_week']:.1f} {t('days/week')}", t("{n} deadline(s) in window", n=r["upcoming_deadlines"]),
                 "bad" if r["delay_exposure_days_per_week"] else "good"),
            ])
            c1, c2 = st.columns([1.1, 1])
            with c1:
                pr = det["projects"]
                fig = go.Figure()
                for _, row in pr.iterrows():
                    fig.add_bar(y=[sel], x=[row["hours_per_week"]], orientation="h", name=f"{row['project_code']} ({row['hours_per_week']:.0f}h)",
                                text=f"{row['project_code']}: {row['hours_per_week']:.0f}h", textposition="inside")
                fig.add_vline(x=r["effective_capacity"], line_color="#b3261e", line_width=3, line_dash="dash",
                              annotation_text=f"{t('Capacity')} {r['effective_capacity']:.0f}h", annotation_position="top")
                fig.update_layout(barmode="stack", title=t("Hours allocated per project vs capacity"), yaxis=dict(showticklabels=False))
                st.plotly_chart(ui.style_fig(fig, height=230), key="ov_bar")
            with c2:
                st.markdown("**" + t("Recommended actions") + "**")
                recs = engine_alloc.recommendations(r)
                if recs:
                    for i, rec in enumerate(recs, 1):
                        st.markdown(f"{i}. {t(rec)}")
                    st.caption(t("Nothing is changed automatically: every reassignment or deadline change needs manager approval."))
                else:
                    st.success(t("No over-allocation for this employee."))
            tasks = det["tasks"]
            st.markdown("**" + t("Affected tasks and deadlines") + "**")
            if tasks is not None and not tasks.empty:
                ui.table(tasks, {"code": "Task", "project_code": "Project", "title": "Title", "due_date": "Due", "priority": "Priority",
                                 "status": "Status", "remaining_hours": "Remaining h", "delay_exposure_days": "Est. delay (days)"},
                         translate_values=("priority", "status"))
                if ctx["role"] in APPROVERS or edit:
                    with st.container(border=True):
                        st.markdown("**" + t("Find an alternative employee for a task") + "**")
                        tc = st.selectbox(t("Task"), tasks["code"].tolist(),
                                          format_func=lambda c: f"{c} · {tasks.set_index('code').loc[c, 'title']}")
                        task = tasks[tasks["code"] == tc].iloc[0].to_dict()
                        cands = engine_alloc.candidates(cid, task["required_skills"], eid, task["remaining_hours"] / 4)
                        st.caption(t("Required skills: {s}. Ranked by skill match, then spare weekly hours (below the high-workload threshold, not absent).",
                                     s=task["required_skills"] or "-"))
                        if cands.empty:
                            st.warning(t("No qualified employee with spare capacity found. Consider subcontractor support or a deadline change."))
                        else:
                            ui.table(cands, {"name": "Employee", "location": "Location", "job_role": "Role", "skills": "Skills",
                                             "skill_match": "Skill match", "utilisation": "Workload %", "spare_hours": "Spare h/week"})
                            with st.form("reassign_req"):
                                to = st.selectbox(t("Propose"), cands["employee_id"].tolist(),
                                                  format_func=lambda i: cands.set_index("employee_id").loc[i, "name"])
                                reason = st.text_input(t("Reason"), value=t("Reduce overcapacity of {n}", n=sel))
                                if st.form_submit_button(t("Request reassignment (needs approval)"), type="primary"):
                                    request_reassignment(ctx, task, int(to), reason)
                                    st.success(t("Request recorded and sent for approval. Nothing has been reassigned yet."))
            else:
                st.info(t("No open tasks assigned."))

    # ---- edit allocations -------------------------------------------------------
    with tabs[2]:
        if not edit:
            st.info(t("Read-only for your role."))
        else:
            emp_names = w.sort_values("name")
            sel = st.selectbox(t("Employee"), emp_names["employee_id"].tolist(), key="edit_emp",
                               format_func=lambda i: f"{emp_names.set_index('employee_id').loc[i, 'name']} ({emp_names.set_index('employee_id').loc[i, 'utilisation']:.0f}%)")
            al = db.df("""SELECT a.id, a.hours_per_week, a.project_role, p.code, p.name FROM allocations a JOIN projects p ON p.id = a.project_id
                          WHERE a.company_id = ? AND a.employee_id = ? AND p.archived = 0""", (cid, sel))
            projects = db.t_rows("projects", cid, "archived = 0 AND status NOT IN ('Completed','Cancelled')")
            with st.form("alloc_edit"):
                new_vals = {}
                for _, a in al.iterrows():
                    new_vals[int(a["id"])] = st.number_input(f"{a['code']} · {a['name']}", 0.0, 60.0, float(a["hours_per_week"]), 1.0, key=f"al_{a['id']}")
                st.caption(t("Set hours to 0 to remove the allocation."))
                add_p = st.selectbox(t("Add to project"), [None] + [p["id"] for p in projects],
                                     format_func=lambda i: "—" if i is None else next(f"{p['code']} · {p['name']}" for p in projects if p["id"] == i))
                add_h = st.number_input(t("Hours per week for the new project"), 0.0, 60.0, 0.0, 1.0)
                if st.form_submit_button(t("Save allocation"), type="primary"):
                    changes = []
                    for aid, h in new_vals.items():
                        old = float(al[al["id"] == aid]["hours_per_week"].iloc[0])
                        if h == 0:
                            db.t_delete("allocations", cid, aid)
                            changes.append(f"removed {aid}")
                        elif h != old:
                            db.t_update("allocations", cid, aid, {"hours_per_week": h})
                            changes.append(f"{aid}: {old}->{h}")
                    if add_p and add_h > 0:
                        db.t_insert("allocations", cid, {"employee_id": sel, "project_id": add_p, "hours_per_week": add_h, "project_role": "Member"})
                        changes.append(f"added project {add_p}: {add_h}h")
                    audit.log(cid, ctx["user"]["email"], "allocation_changed", "employee", sel, "; ".join(changes))
                    res = engine_risk.run(cid)
                    st.success(t("Saved. Workload and risks recalculated ({c} new, {u} updated, {x} cleared).",
                                 c=res["created"], u=res["updated"], x=res["cleared"]))
                    st.rerun()

    # ---- approvals ---------------------------------------------------------------
    with tabs[3]:
        reqs = db.df("""SELECT r.*, t.code, t.title, e1.name AS from_name, e2.name AS to_name FROM reassignments r
                        JOIN tasks t ON t.id = r.task_id LEFT JOIN employees e1 ON e1.id = r.from_employee
                        LEFT JOIN employees e2 ON e2.id = r.to_employee WHERE r.company_id = ? ORDER BY r.id DESC""", (cid,))
        pend = reqs[reqs["status"] == "Pending"] if not reqs.empty else reqs
        if pend.empty:
            st.info(t("No pending reassignment requests."))
        for _, rq in pend.iterrows():
            with st.container(border=True):
                st.markdown(f"**{rq['code']}** · {rq['title']} — {rq['from_name']} → **{rq['to_name']}**  \n"
                            f"<span class='subtle'>{t('Reason')}: {rq['reason']} · {t('Requested by')} {rq['requested_by']} · {rq['created_at']}</span>",
                            unsafe_allow_html=True)
                if ctx["role"] in APPROVERS:
                    b1, b2, _ = st.columns([1, 1, 4])
                    if b1.button("✅ " + t("Approve"), key=f"ap_{rq['id']}"):
                        decide(ctx, rq.to_dict(), True)
                        st.rerun()
                    if b2.button("✖ " + t("Reject"), key=f"rj_{rq['id']}"):
                        decide(ctx, rq.to_dict(), False)
                        st.rerun()
        if not reqs.empty:
            st.markdown("**" + t("History") + "**")
            ui.table(reqs, {"code": "Task", "from_name": "From", "to_name": "To", "status": "Status", "requested_by": "Requested by",
                            "decided_by": "Decided by", "decided_at": "Decided at"}, translate_values=("status",))
    _ = pd
