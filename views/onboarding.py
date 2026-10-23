"""Employee onboarding checklist and role-based training."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from hub import audit, db, engine_risk, events, ui
from hub.i18n import t, tf
from hub.seed import ONBOARDING_STEPS

LEAST_PRIVILEGE = {  # suggested baseline access per department (recommendation only)
    "Software Engineering": "Microsoft 365 (standard), Git repositories (developer), project tool (member). No production admin by default.",
    "Cloud & Infrastructure": "Microsoft 365 (standard), cloud console (read-only first; admin only via separate admin account after approval).",
    "Cybersecurity": "Microsoft 365 (standard), SIEM (analyst). Privileged access through separate admin account with MFA.",
    "Data & BI": "Microsoft 365 (standard), data warehouse (read; write only for assigned projects).",
    "Finance & Procurement": "Microsoft 365 (standard), finance ERP (entry). Payment approval rights only with segregation of duties.",
    "Service Desk": "Microsoft 365 (standard), ITSM (agent). Password-reset rights only after training.",
}
TRAIN_STATUSES = ["Assigned", "In progress", "Completed", "Waived"]


def render(ctx: dict) -> None:
    cid, edit, user = ctx["cid"], ctx["can_edit"], ctx["user"]
    today = date.today()
    ui.page_header("onboarding", t("Onboarding & training"), t("Recent recruits: checklist, role-based training and access"))
    nh = db.df("""SELECT e.*, l.name AS location, m.name AS manager FROM employees e LEFT JOIN locations l ON l.id = e.location_id
                  LEFT JOIN employees m ON m.id = e.manager_id WHERE e.company_id = ? AND e.is_new_hire = 1 AND e.active = 1
                  ORDER BY e.join_date DESC""", (cid,))
    steps = db.t_df("onboarding_steps", cid)
    ta = db.df("""SELECT ta.*, tr.name AS course FROM training_assignments ta JOIN trainings tr ON tr.id = ta.training_id
                  WHERE ta.company_id = ?""", (cid,))
    ar = db.t_df("access_requests", cid)
    if nh.empty:
        st.info(t("No recent recruits recorded. Tick 'Recent recruit' on an employee profile to track onboarding."))
    else:
        ids = set(nh["id"])
        s = steps[steps["employee_id"].isin(ids)] if not steps.empty else steps
        prog = s.groupby("employee_id")["done"].mean().mul(100).round(0) if not s.empty else pd.Series(dtype=float)
        nh["onboarding_pct"] = nh["id"].map(prog).fillna(0)
        t2 = ta[ta["employee_id"].isin(ids)] if not ta.empty else ta
        trate = t2.groupby("employee_id")["status"].apply(lambda x: (x == "Completed").mean() * 100).round(0) if not t2.empty else pd.Series(dtype=float)
        nh["training_pct"] = nh["id"].map(trate).fillna(0)
        od = t2[(t2["status"] != "Completed") & (pd.to_datetime(t2["due_date"]).dt.date < today)] if not t2.empty else t2
        nh["overdue_training"] = nh["id"].map(od.groupby("employee_id").size()).fillna(0).astype(int)
        a2 = ar[ar["employee_id"].isin(ids)] if not ar.empty else ar
        pend = a2[a2["approval_status"] == "Pending"]
        nh["access_pending"] = nh["id"].map(pend.groupby("employee_id").size()).fillna(0).astype(int)
        miss = s[(s["step_no"] == 3) & (s["done"] == 0)]["employee_id"].unique() if not s.empty else []
        nh["missing_evidence"] = nh["id"].isin(miss)
        ui.kpi_row([
            (t("Total new employees"), len(nh), t("case study: 25 over two years"), "neutral"),
            (t("Onboarding completed"), int((nh["onboarding_pct"] >= 100).sum()), t("all 10 steps"), "good"),
            (t("Training completion rate"), f"{(t2['status'] == 'Completed').mean() * 100:.0f}%" if not t2.empty else "-", t("new employees"), "warn"),
            (t("Overdue training"), int(nh["overdue_training"].gt(0).sum()), t("employees"), "bad" if nh["overdue_training"].gt(0).any() else "good"),
            (t("Awaiting access approval"), int(nh["access_pending"].gt(0).sum()), t("employees"), "warn"),
            (t("Missing required evidence"), int(nh["missing_evidence"].sum()), t("documents not recorded"), "warn"),
        ], per_row=3)
    tabs = st.tabs(["📋 " + t("New employees"), "✅ " + t("Checklist"), "🎓 " + t("Training catalogue")])
    with tabs[0]:
        ui.table(nh, {"name": "Employee", "join_date": "Joined", "department": "Department", "job_role": "Role", "manager": "Manager",
                      "location": "Location", "onboarding_pct": "Onboarding %", "training_pct": "Training %", "overdue_training": "Overdue training",
                      "access_pending": "Access pending", "missing_evidence": "Missing evidence"},
                 column_config={"onboarding_pct": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
                                "training_pct": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)} if not nh.empty else None)
    with tabs[1]:
        if not nh.empty:
            eid = st.selectbox(t("Employee"), nh["id"].tolist(), format_func=lambda i: f"{nh.set_index('id').loc[i, 'name']} · {nh.set_index('id').loc[i, 'join_date']}")
            e = nh[nh["id"] == eid].iloc[0]
            st.caption(f"{e['job_role']} · {e['department']} · {e['location']} · {t('Manager')}: {e['manager'] or '-'}")
            mine = steps[steps["employee_id"] == eid].set_index("step_no") if not steps.empty else pd.DataFrame()
            c1, c2 = st.columns(2)
            with c1.form(f"chk_{eid}"):
                st.markdown("**" + t("Onboarding checklist") + "**")
                vals = {}
                for i, name in enumerate(ONBOARDING_STEPS, 1):
                    done = bool(mine.loc[i, "done"]) if (not mine.empty and i in mine.index) else False
                    vals[i] = st.checkbox(f"{i}. {t(name)}", value=done, disabled=not edit, key=f"st_{eid}_{i}")
                if st.form_submit_button(t("Save checklist"), disabled=not edit):
                    if vals[10] and not all(vals[i] for i in range(1, 10)):
                        st.error(t("Onboarding cannot be completed while earlier steps are open."))
                    else:
                        for i, v in vals.items():
                            if not mine.empty and i in mine.index:
                                db.t_update("onboarding_steps", cid, int(mine.loc[i, "id"]), {"done": int(v), "done_date": str(today) if v else None})
                            else:
                                db.t_insert("onboarding_steps", cid, {"employee_id": int(eid), "step_no": i, "done": int(v), "done_date": str(today) if v else None})
                        audit.log(cid, user["email"], "onboarding_updated", "employee", e["emp_code"], f"{sum(vals.values())}/10")
                        engine_risk.run(cid)
                        st.success(t("Saved."))
                        st.rerun()
            with c2:
                st.markdown("**" + t("Training assignments") + "**")
                mt = ta[ta["employee_id"] == eid] if not ta.empty else ta
                ui.table(mt, {"course": "Course", "due_date": "Due", "status": "Status", "completion": "%", "score": "Score"}, translate_values=("status",))
                if edit and not mt.empty:
                    with st.form(f"tr_{eid}"):
                        aid = st.selectbox(t("Course"), mt["id"].tolist(), format_func=lambda i: mt.set_index("id").loc[i, "course"])
                        ns = st.selectbox(t("Status"), TRAIN_STATUSES, format_func=tf)
                        sc = st.number_input(t("Assessment score (optional)"), 0, 100, 0)
                        if st.form_submit_button(t("Update training")):
                            db.t_update("training_assignments", cid, int(aid), {"status": ns, "completion": 100 if ns == "Completed" else 50 if ns == "In progress" else 0,
                                                                                 "score": sc or None, "completed_date": str(today) if ns == "Completed" else None})
                            audit.log(cid, user["email"], "training_updated", "employee", e["emp_code"], ns)
                            events.emit(cid, "training", f"Training status updated: {mt.set_index('id').loc[aid, 'course']}",
                                        f"New status: {ns}.", employees=[int(eid)], page="my_work", exclude_user=user["id"], email=False)
                            engine_risk.run(cid)
                            st.rerun()
                st.markdown("**" + t("Access requests") + "**")
                ma = ar[ar["employee_id"] == eid] if not ar.empty else ar
                ui.table(ma, {"system": "System", "permission": "Permission", "approval_status": "Approval", "activation_status": "Activation"},
                         translate_values=("approval_status", "activation_status"))
                st.info("🔐 " + t("Least-privilege suggestion") + ": " + t(LEAST_PRIVILEGE.get(e["department"], "Microsoft 365 (standard) and the tools of assigned projects only.")))
                st.caption(t("Completing training does not grant access. Access requires an approved request in Access lifecycle (JML)."))
    with tabs[2]:
        tr = db.t_df("trainings", cid)
        ui.table(tr, {"name": "Course", "category": "Category", "required_for": "Required for (departments)", "duration_hours": "Hours"})
        if edit:
            with st.form("new_tr"):
                c1, c2, c3 = st.columns(3)
                n = c1.text_input(t("Course name"))
                cat = c2.text_input(t("Category"), value="Security")
                req = c3.text_input(t("Required for (departments, or All)"), value="All")
                hrs = c1.number_input(t("Hours"), 0.0, 100.0, 1.0)
                assign = c2.checkbox(t("Assign now to matching active employees"), value=True)
                due = c3.date_input(t("Due date"), today + timedelta(days=30))
                if st.form_submit_button(t("Add course"), type="primary") and n.strip():
                    tid = db.t_insert("trainings", cid, {"name": n, "category": cat, "required_for": req, "duration_hours": hrs})
                    k = 0
                    if assign:
                        for emp in db.t_rows("employees", cid, "active = 1"):
                            if req.strip().lower() == "all" or emp["department"] in [x.strip() for x in req.split(",")]:
                                db.t_insert("training_assignments", cid, {"employee_id": emp["id"], "training_id": tid, "due_date": str(due), "status": "Assigned", "completion": 0})
                                k += 1
                    audit.log(cid, user["email"], "training_created", "training", tid, f"{n}; assigned {k}")
                    if assign and k:
                        ids = [r["employee_id"] for r in db.t_rows("training_assignments", cid, "training_id = ?", (tid,))]
                        events.emit(cid, "training", f"New training assigned: {n}", f"Due {due}.", employees=ids, page="my_work", email=False)
                    st.success(t("Course added and assigned to {k} employee(s).", k=k))
