"""Employee directory, profile and maintenance."""
from __future__ import annotations

from datetime import date

import streamlit as st

from hub import audit, db, engine_alloc, engine_risk, importers, ui
from hub.i18n import t, tf

CONTROL_STATES = ["Not recorded", "Verified", "Not enabled", "Exception approved"]
DEVICE_STATES = ["Not recorded", "Compliant", "Non-compliant"]
EMP_STATUSES = ["Active", "On leave", "Notice period", "Left"]


def employee_form(ctx, e: dict | None) -> None:
    cid, user = ctx["cid"], ctx["user"]
    e = e or {}
    locs = db.t_rows("locations", cid, order="name")
    mgrs = db.t_rows("employees", cid, "active = 1", order="name")
    with st.form(f"emp_{e.get('id', 'new')}"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input(t("Employee ID") + " *", value=e.get("emp_code", ""))
        name = c2.text_input(t("Name") + " *", value=e.get("name", ""))
        email = c3.text_input(t("E-mail"), value=e.get("email", "") or "")
        phone = c1.text_input(t("Phone"), value=e.get("phone", "") or "")
        lids = [None] + [x["id"] for x in locs]
        loc = c2.selectbox(t("Location"), lids, index=lids.index(e.get("location_id")) if e.get("location_id") in lids else 0,
                           format_func=lambda i: "—" if i is None else next(x["name"] for x in locs if x["id"] == i))
        dept = c3.text_input(t("Department"), value=e.get("department", "") or "")
        role = c1.text_input(t("Job role"), value=e.get("job_role", "") or "")
        skills = c2.text_input(t("Skills (comma-separated)"), value=e.get("skills", "") or "")
        cap = c3.number_input(t("Weekly capacity (hours)"), 0.0, 60.0, float(e.get("weekly_capacity") or 35), 1.0)
        wh = c1.text_input(t("Working hours"), value=e.get("working_hours", "") or "Mon-Fri 09:00-17:00")
        status = c2.selectbox(t("Employment status"), EMP_STATUSES,
                              index=EMP_STATUSES.index(e.get("employment_status", "Active")) if e.get("employment_status", "Active") in EMP_STATUSES else 0, format_func=tf)
        mids = [None] + [m["id"] for m in mgrs if m["id"] != e.get("id")]
        mgr = c3.selectbox(t("Manager"), mids, index=mids.index(e.get("manager_id")) if e.get("manager_id") in mids else 0,
                           format_func=lambda i: "—" if i is None else next(m["name"] for m in mgrs if m["id"] == i))
        jd = c1.date_input(t("Joining date"), date.fromisoformat(e["join_date"]) if e.get("join_date") else date.today())
        newh = c2.checkbox(t("Recent recruit (onboarding tracked)"), value=bool(e.get("is_new_hire", 0)))
        remote = c3.checkbox(t("Remote-work eligible"), value=bool(e.get("remote_eligible", 0)))
        st.markdown("**" + t("Remote-work security controls (only mark Verified when evidence exists)") + "**")
        r1, r2, r3, r4 = st.columns(4)
        mfa = r1.selectbox("MFA", CONTROL_STATES, index=CONTROL_STATES.index(e.get("mfa_status", "Not recorded")) if e.get("mfa_status") in CONTROL_STATES else 0, format_func=tf)
        dev = r2.selectbox(t("Device compliance"), DEVICE_STATES, index=DEVICE_STATES.index(e.get("device_status", "Not recorded")) if e.get("device_status") in DEVICE_STATES else 0, format_func=tf)
        vpn = r3.selectbox("VPN / Zero-trust", CONTROL_STATES, index=CONTROL_STATES.index(e.get("vpn_status", "Not recorded")) if e.get("vpn_status") in CONTROL_STATES else 0, format_func=tf)
        edr = r4.selectbox(t("Endpoint security (EDR)"), CONTROL_STATES, index=CONTROL_STATES.index(e.get("edr_status", "Not recorded")) if e.get("edr_status") in CONTROL_STATES else 0, format_func=tf)
        if st.form_submit_button(t("Save employee"), type="primary"):
            if not code.strip() or not name.strip():
                st.error(t("Employee ID and name are required."))
                return
            data = {"emp_code": code, "name": name, "email": email, "phone": phone, "location_id": loc, "department": dept, "job_role": role,
                    "skills": skills, "weekly_capacity": cap, "working_hours": wh, "employment_status": status, "manager_id": mgr,
                    "join_date": str(jd), "is_new_hire": int(newh), "remote_eligible": int(remote), "mfa_status": mfa,
                    "device_status": dev, "vpn_status": vpn, "edr_status": edr, "active": 0 if status == "Left" else 1}
            if e.get("id"):
                db.t_update("employees", cid, e["id"], data)
                audit.log(cid, user["email"], "employee_updated", "employee", code)
            else:
                db.t_insert("employees", cid, data)
                audit.log(cid, user["email"], "employee_created", "employee", code)
            res = engine_risk.run(cid)
            st.success(t("Saved. Workload and risks recalculated ({c} new, {u} updated, {x} cleared).", c=res["created"], u=res["updated"], x=res["cleared"]))
            st.rerun()


def render(ctx: dict) -> None:
    cid, edit = ctx["cid"], ctx["can_edit"]
    ui.page_header("employees", t("Employees"), t("Directory, profiles, capacity and workload"))
    wl = engine_alloc.workload(cid)
    emps = db.df("""SELECT e.*, l.name AS location, m.name AS manager FROM employees e LEFT JOIN locations l ON l.id = e.location_id
                    LEFT JOIN employees m ON m.id = e.manager_id WHERE e.company_id = ? ORDER BY e.name""", (cid,))
    if not emps.empty and not wl.empty:
        emps = emps.merge(wl[["employee_id", "allocated", "remaining", "utilisation", "band", "project_list", "open_tasks",
                              "overdue_tasks", "upcoming_deadlines", "absent_now"]], left_on="id", right_on="employee_id", how="left")
    tabs = st.tabs(["👥 " + t("Directory"), "🪪 " + t("Profile"), "✏️ " + t("Add / edit"), "📥 " + t("CSV import")])
    with tabs[0]:
        if emps.empty:
            st.info(t("No employees yet."))
        else:
            f = st.columns(4)
            q = f[0].text_input("🔍 " + t("Search"), placeholder=t("name, skill, role…"))
            lo = f[1].multiselect(t("Location"), sorted(emps["location"].dropna().unique()), placeholder=t("All"))
            de = f[2].multiselect(t("Department"), sorted(emps["department"].dropna().unique()), placeholder=t("All"))
            show_inactive = f[3].checkbox(t("Include former employees"))
            d = emps if show_inactive else emps[emps["active"] == 1]
            if q:
                ql = q.lower()
                d = d[d[["name", "skills", "job_role", "emp_code", "email"]].fillna("").apply(lambda r: ql in " ".join(r).lower(), axis=1)]
            if lo:
                d = d[d["location"].isin(lo)]
            if de:
                d = d[d["department"].isin(de)]
            st.caption(t("{n} employee(s)", n=len(d)))
            ui.table(d, {"emp_code": "ID", "name": "Name", "location": "Location", "department": "Department", "job_role": "Role",
                         "weekly_capacity": "Capacity h", "allocated": "Allocated h", "utilisation": "Workload %", "band": "Band",
                         "project_list": "Projects", "open_tasks": "Open tasks", "overdue_tasks": "Overdue", "employment_status": "Status"},
                     translate_values=("band", "employment_status"), height=480)
    with tabs[1]:
        act = emps[emps["active"] == 1] if not emps.empty else emps
        if act.empty:
            st.info(t("No employees yet."))
        else:
            eid = st.selectbox(t("Employee"), act["id"].tolist(), format_func=lambda i: f"{act.set_index('id').loc[i, 'name']} · {act.set_index('id').loc[i, 'emp_code']}")
            e = act[act["id"] == eid].iloc[0]
            st.markdown(f"### {e['name']}  " + ui.pill(e.get("band") or "Healthy", ui.BAND_COLORS.get(e.get("band"), "#888")), unsafe_allow_html=True)
            st.caption(f"{e['job_role']} · {e['department']} · {e['location']} · {t('Manager')}: {e['manager'] or '-'} · {e['email']} · {e['phone'] or ''}")
            ui.kpi_row([
                (t("Capacity"), f"{e['weekly_capacity']:.0f} h", e["working_hours"] or "", "neutral"),
                (t("Allocated (all projects)"), f"{(e.get('allocated') or 0):.0f} h", e.get("project_list") or "-", "neutral"),
                (t("Available capacity"), f"{(e.get('remaining') or 0):.0f} h", f"{(e.get('utilisation') or 0):.0f}%", "bad" if (e.get("remaining") or 0) < 0 else "good"),
                (t("Overdue / upcoming"), f"{int(e.get('overdue_tasks') or 0)} / {int(e.get('upcoming_deadlines') or 0)}",
                 t("Absent today") if e.get("absent_now") else t("Available"), "warn" if e.get("absent_now") else "neutral"),
            ])
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**" + t("Assigned projects") + "**")
                al = db.df("""SELECT p.code, p.name, a.hours_per_week, a.project_role FROM allocations a JOIN projects p ON p.id = a.project_id
                              WHERE a.company_id = ? AND a.employee_id = ? AND p.archived = 0""", (cid, int(eid)))
                ui.table(al, {"code": "ID", "name": "Project", "hours_per_week": "h/week", "project_role": "Role"})
                st.markdown("**" + t("Skills") + "**: " + (e["skills"] or "-"))
                st.markdown("**" + t("Remote-work controls") + f"** ({t('eligible') if e['remote_eligible'] else t('not eligible')})")
                st.markdown(f"MFA: {tf(e['mfa_status'])} · {t('Device')}: {tf(e['device_status'])} · VPN: {tf(e['vpn_status'])} · EDR: {tf(e['edr_status'])}")
            with c2:
                st.markdown("**" + t("Assigned tasks") + "**")
                tk = db.df("""SELECT t.code, t.title, t.due_date, t.status, t.completion FROM tasks t WHERE t.company_id = ? AND t.assignee_id = ?
                              ORDER BY t.due_date""", (cid, int(eid)))
                ui.table(tk, {"code": "ID", "title": "Title", "due_date": "Due", "status": "Status", "completion": "%"}, translate_values=("status",))
                st.markdown("**" + t("Training status") + "**")
                tr = db.df("""SELECT tr.name, ta.status, ta.due_date FROM training_assignments ta JOIN trainings tr ON tr.id = ta.training_id
                              WHERE ta.company_id = ? AND ta.employee_id = ?""", (cid, int(eid)))
                ui.table(tr, {"name": "Course", "status": "Status", "due_date": "Due"}, translate_values=("status",))
                ab = db.t_df("absences", cid, "employee_id = ?", (int(eid),), order="start_date DESC")
                st.markdown("**" + t("Absences") + "**")
                ui.table(ab, {"absence_type": "Type", "start_date": "From", "end_date": "To"}, translate_values=("absence_type",))
    with tabs[2]:
        if not edit:
            st.info(t("Read-only for your role."))
        else:
            mode = st.radio(t("Mode"), ["new", "edit"], horizontal=True, format_func=lambda m: t("Add employee") if m == "new" else t("Edit / deactivate"))
            if mode == "new":
                employee_form(ctx, None)
            elif not emps.empty:
                eid = st.selectbox(t("Employee"), emps["id"].tolist(), key="ed_emp", format_func=lambda i: emps.set_index("id").loc[i, "name"])
                rec = db.t_get("employees", cid, int(eid))
                employee_form(ctx, rec)
                if rec["active"] and st.button("⛔ " + t("Deactivate employee")):
                    db.t_update("employees", cid, rec["id"], {"active": 0, "employment_status": "Left", "leave_date": str(date.today())})
                    for a in db.t_rows("access_requests", cid, "employee_id = ? AND activation_status = 'Active'", (rec["id"],)):
                        db.t_update("access_requests", cid, a["id"], {"revocation_status": "Pending"})
                    audit.log(cid, ctx["user"]["email"], "employee_deactivated", "employee", rec["emp_code"], "access revocation set to Pending")
                    engine_risk.run(cid)
                    st.success(t("Employee deactivated; active access rights marked 'revocation pending'."))
                    st.rerun()
    with tabs[3]:
        if not edit:
            st.info(t("Read-only for your role."))
        else:
            st.download_button(t("Download CSV template"), importers.template_csv(), "employees_template.csv", "text/csv")
            up = st.file_uploader(t("Upload employees CSV"), type=["csv"])
            if up is not None and st.button(t("Import"), type="primary"):
                n, errs = importers.import_employees(cid, up.getvalue())
                audit.log(cid, ctx["user"]["email"], "employees_imported", "employee", "", f"{n} rows")
                st.success(t("{n} employee(s) imported.", n=n))
                for e in errs:
                    st.warning(e)
                engine_risk.run(cid)
