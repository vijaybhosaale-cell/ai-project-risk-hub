"""Company settings: 9-step setup wizard (editable later), thresholds, notifications, demo reset."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from hub import audit, db, engine_risk, importers, seed, ui
from hub.i18n import t, tf

STEPS = ["Company profile", "Locations", "Employees", "Projects", "Clients & contracts", "Subcontractors",
         "Risk & compliance", "Notifications", "Review"]


def _nav(n: int) -> None:
    st.session_state["wiz_step"] = max(0, min(len(STEPS) - 1, n))


def wizard(ctx: dict) -> None:
    cid, user = ctx["cid"], ctx["user"]
    comp = db.company(cid)
    s = db.settings(cid)
    step = st.session_state.get("wiz_step", 0)
    st.progress((step + 1) / len(STEPS), text=f"{t('Step')} {step + 1} / {len(STEPS)} · {t(STEPS[step])}")
    cols = st.columns(len(STEPS))
    for i, name in enumerate(STEPS):
        cols[i].button(f"{i + 1}", key=f"wz_{i}", on_click=_nav, args=(i,), help=t(name),
                       type="primary" if i == step else "secondary", width="stretch")
    st.subheader(f"{step + 1}. {t(STEPS[step])}")

    if step == 0:
        with st.form("wz_profile"):
            c1, c2 = st.columns(2)
            name = c1.text_input(t("Company name"), value=comp["name"])
            ind = c2.text_input(t("Industry"), value=comp.get("industry") or "")
            country = c1.text_input(t("Country"), value=comp.get("country") or "")
            n = c2.number_input(t("Number of employees"), 0, 100000, int(comp.get("declared_employees") or 0))
            cur = c1.selectbox(t("Currency"), ["EUR", "USD", "GBP", "INR", "CHF"], index=["EUR", "USD", "GBP", "INR", "CHF"].index(comp.get("currency") or "EUR"))
            lang_ = c2.selectbox(t("Preferred language"), ["en", "fr"], index=["en", "fr"].index(comp.get("language") or "en"),
                                 format_func=lambda x: {"en": "English", "fr": "Français"}[x])
            obj = st.text_area(t("Business objectives"), value=comp.get("objectives") or "")
            rep = st.text_input(t("Reporting preferences"), value=comp.get("reporting_prefs") or "Weekly management report")
            if st.form_submit_button(t("Save and continue") + " →", type="primary"):
                db.execute("""UPDATE companies SET name=?, industry=?, country=?, declared_employees=?, currency=?, language=?, objectives=?,
                              reporting_prefs=? WHERE id=?""", (name, ind, country, int(n), cur, lang_, obj, rep, cid))
                audit.log(cid, user["email"], "setup_profile", "company", cid)
                _nav(1)
                st.rerun()
    elif step == 1:
        locs = db.t_df("locations", cid)
        ui.table(locs, {"name": "Location", "address": "Address", "manager": "Location manager", "employee_count": "Employees",
                        "active_projects": "Active projects", "timezone": "Time zone"})
        with st.form("wz_loc"):
            c1, c2, c3 = st.columns(3)
            ln = c1.text_input(t("Location name") + " *")
            ad = c2.text_input(t("Address (optional)"))
            mg = c3.text_input(t("Location manager"))
            ec = c1.number_input(t("Employees"), 0, 100000, 0)
            ap = c2.number_input(t("Active projects"), 0, 1000, 0)
            tz = c3.text_input(t("Time zone"), value=comp.get("timezone") or "Europe/Paris")
            if st.form_submit_button(t("Add location")) and ln.strip():
                db.t_insert("locations", cid, {"name": ln, "address": ad, "manager": mg, "employee_count": int(ec), "active_projects": int(ap), "timezone": tz})
                audit.log(cid, user["email"], "location_added", "location", ln)
                st.rerun()
        if not locs.empty:
            d1, d2 = st.columns([3, 1])
            rm = d1.selectbox(t("Remove a location"), locs["id"].tolist(), format_func=lambda i: locs.set_index("id").loc[i, "name"])
            if d2.button(t("Remove")):
                if db.scalar("SELECT COUNT(*) FROM employees WHERE company_id=? AND location_id=?", (cid, int(rm))):
                    st.error(t("Employees are assigned to this location; move them first."))
                else:
                    db.t_delete("locations", cid, int(rm))
                    st.rerun()
        st.caption(t("Add as many locations as the company has. There is no fixed list."))
    elif step == 2:
        n = db.scalar("SELECT COUNT(*) FROM employees WHERE company_id=? AND active=1", (cid,))
        st.info(t("Declared employees: {d} · recorded: {n}", d=comp.get("declared_employees") or 0, n=n))
        locs = db.t_rows("locations", cid)
        c1, c2 = st.columns(2)
        with c1.form("wz_emp"):
            st.markdown("**" + t("Add an employee") + "**")
            code = st.text_input(t("Employee ID") + " *", value=f"E-{n + 1:03d}")
            name = st.text_input(t("Name") + " *")
            email = st.text_input(t("E-mail"))
            role = st.text_input(t("Job role"))
            loc = st.selectbox(t("Location"), [None] + [x["id"] for x in locs], format_func=lambda i: "—" if i is None else next(x["name"] for x in locs if x["id"] == i))
            skills = st.text_input(t("Skills (comma-separated)"))
            cap = st.number_input(t("Weekly capacity (hours)"), 0.0, 60.0, 35.0)
            wh = st.text_input(t("Working hours"), value="Mon-Fri 09:00-17:00")
            if st.form_submit_button(t("Add employee")) and name.strip():
                db.t_insert("employees", cid, {"emp_code": code, "name": name, "email": email, "job_role": role, "location_id": loc, "skills": skills,
                                               "weekly_capacity": cap, "working_hours": wh, "employment_status": "Active", "join_date": str(date.today()),
                                               "is_new_hire": 1, "active": 1})
                audit.log(cid, user["email"], "employee_created", "employee", code)
                st.rerun()
        with c2:
            st.markdown("**" + t("Or import a CSV file") + "**")
            st.download_button(t("Download CSV template"), importers.template_csv(), "employees_template.csv", "text/csv")
            up = st.file_uploader(t("Upload employees CSV"), type=["csv"], key="wz_csv")
            if up is not None and st.button(t("Import"), key="wz_imp"):
                k, errs = importers.import_employees(cid, up.getvalue())
                st.success(t("{n} employee(s) imported.", n=k))
                for e in errs:
                    st.warning(e)
        ui.table(db.t_df("employees", cid, "active = 1"), {"emp_code": "ID", "name": "Name", "job_role": "Role", "skills": "Skills", "weekly_capacity": "Capacity h"})
    elif step == 3:
        emps = db.t_rows("employees", cid, "active = 1", order="name")
        clients = db.t_rows("clients", cid, order="name")
        n = db.scalar("SELECT COUNT(*) FROM projects WHERE company_id=? AND archived=0", (cid,))
        with st.form("wz_proj"):
            c1, c2, c3 = st.columns(3)
            code = c1.text_input(t("Project ID") + " *", value=f"P{n + 1:02d}")
            name = c2.text_input(t("Project name") + " *")
            prio = c3.selectbox(t("Priority"), ["Low", "Medium", "High", "Critical"], index=1, format_func=tf)
            client = c1.selectbox(t("Client"), [None] + [x["id"] for x in clients], format_func=lambda i: "—" if i is None else next(x["name"] for x in clients if x["id"] == i))
            mgr = c2.selectbox(t("Project manager"), [None] + [e["id"] for e in emps], format_func=lambda i: "—" if i is None else next(e["name"] for e in emps if e["id"] == i))
            bud = c3.number_input(t("Approved budget"), 0.0, value=50000.0, step=1000.0)
            sd = c1.date_input(t("Start date"), date.today())
            ed = c2.date_input(t("Deadline"), date.today() + timedelta(days=90))
            ms = c3.text_input(t("Milestones (comma-separated)"), value="Design sign-off, Go-live")
            team = st.multiselect(t("Team members"), [e["id"] for e in emps], format_func=lambda i: next(e["name"] for e in emps if e["id"] == i))
            hrs = st.number_input(t("Hours per week per team member"), 0.0, 60.0, 10.0)
            st.caption(t("Clients can also be added in the next step and linked later from Projects."))
            if st.form_submit_button(t("Add project"), type="primary") and code.strip() and name.strip():
                pid = db.t_insert("projects", cid, {"code": code, "name": name, "priority": prio, "client_id": client, "manager_id": mgr, "budget": bud,
                                                   "start_date": str(sd), "end_date": str(ed), "status": "Active", "financials_are_estimates": 0})
                for i, m in enumerate([x.strip() for x in ms.split(",") if x.strip()]):
                    md = sd + (ed - sd) * (i + 1) / max(len(ms.split(",")), 1)
                    db.t_insert("milestones", cid, {"project_id": pid, "name": m, "due_date": str(md), "status": "Planned"})
                for e in team:
                    db.t_insert("allocations", cid, {"employee_id": e, "project_id": pid, "hours_per_week": hrs, "project_role": "Member"})
                audit.log(cid, user["email"], "project_created", "project", code)
                st.rerun()
        ui.table(db.t_df("projects", cid, "archived = 0"), {"code": "ID", "name": "Project", "priority": "Priority", "budget": "Budget",
                                                            "start_date": "Start", "end_date": "End"}, translate_values=("priority",))
    elif step == 4:
        with st.form("wz_client"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input(t("Client name") + " *")
            contact = c2.text_input(t("Client contact"))
            country = c3.text_input(t("Country"))
            cs = c1.date_input(t("Contract start"), date.today())
            ce = c2.date_input(t("Contract end"), date.today() + timedelta(days=365))
            rn = c3.date_input(t("Renewal date"), date.today() + timedelta(days=300))
            sla = st.text_input(t("Service-level agreement"))
            dl = st.text_input(t("Important deliverables"))
            eu = c1.checkbox(t("EU / EEA client (GDPR applies)"), value=True)
            dp = st.text_input(t("Applicable data-protection requirements"), value="GDPR Art. 28 processor obligations")
            if st.form_submit_button(t("Add client"), type="primary") and name.strip():
                db.t_insert("clients", cid, {"name": name, "contact": contact, "country": country, "contract_start": str(cs), "contract_end": str(ce),
                                             "renewal_date": str(rn), "sla": sla, "deliverables": dl, "is_eu": int(eu), "dp_obligations": dp, "recurring": 1})
                audit.log(cid, user["email"], "client_created", "client", name)
                st.rerun()
        ui.table(db.t_df("clients", cid), {"name": "Client", "country": "Country", "renewal_date": "Renewal", "sla": "SLA"})
    elif step == 5:
        projects = db.t_rows("projects", cid, "archived = 0")
        with st.form("wz_sub"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input(t("Subcontractor name") + " *")
            contact = c2.text_input(t("Contact"))
            email = c3.text_input(t("E-mail"))
            pid = c1.selectbox(t("Assigned project"), [None] + [p["id"] for p in projects], format_func=lambda i: "—" if i is None else next(p["code"] for p in projects if p["id"] == i))
            resp = c2.text_input(t("Responsibilities / contractual requirements"))
            access = c3.selectbox(t("Access status"), ["None", "Requested", "Active (time-limited)", "Active (no expiry)", "Revoked"], format_func=tf)
            if st.form_submit_button(t("Add subcontractor"), type="primary") and name.strip():
                db.t_insert("subcontractors", cid, {"name": name, "contact": contact, "email": email, "project_id": pid, "obligations": resp,
                                                    "data_access": access, "security_assessment": "Not started", "performance": "On track"})
                audit.log(cid, user["email"], "subcontractor_created", "subcontractor", name)
                st.rerun()
        ui.table(db.t_df("subcontractors", cid), {"name": "Subcontractor", "contact": "Contact", "obligations": "Responsibilities", "data_access": "Access"})
    elif step == 6:
        tr = s["track"]
        with st.form("wz_risk"):
            st.markdown(t("Which risk areas should the platform track?"))
            v = {
                "cyber": st.checkbox(t("Cybersecurity risks"), value=tr.get("cyber", True)),
                "operational": st.checkbox(t("Operational risks (workload, delivery)"), value=tr.get("operational", True)),
                "gdpr": st.checkbox(t("GDPR-related obligations"), value=tr.get("gdpr", True)),
                "supplier": st.checkbox(t("Supplier / subcontractor risks"), value=tr.get("supplier", True)),
                "continuity": st.checkbox(t("Business continuity (cloud, backup)"), value=tr.get("continuity", True)),
                "sla": st.checkbox(t("Service-level compliance"), value=tr.get("sla", True)),
            }
            if st.form_submit_button(t("Save and continue") + " →", type="primary"):
                s["track"] = v
                db.save_settings(cid, s)
                audit.log(cid, user["email"], "setup_risk_scope", "settings", "", str(v))
                _nav(7)
                st.rerun()
    elif step == 7:
        notifications_form(ctx, s)
    elif step == 8:
        counts = {t(k): db.scalar(f"SELECT COUNT(*) FROM {tb} WHERE company_id=?" + (" AND active=1" if tb == "employees" else ""), (cid,))
                  for k, tb in (("Locations", "locations"), ("Employees", "employees"), ("Projects", "projects"), ("Clients", "clients"),
                                ("Subcontractors", "subcontractors"))}
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**{comp['name']}** · {comp.get('industry') or ''} · {comp.get('country') or ''} · {comp.get('currency')}")
            for k, v in counts.items():
                st.markdown(f"- {k}: **{v}**")
        with c2:
            st.markdown("**" + t("Risk areas tracked") + "**: " + ", ".join(k for k, v in s["track"].items() if v))
            st.markdown("**NTFY**: " + (t("enabled") if s["ntfy"]["enabled"] else t("not configured")) + " · **" + t("E-mail") + "**: " +
                        (t("enabled") if s["email"]["enabled"] else t("not configured")))
        st.caption(t("Use the step buttons above to go back and edit anything before completing."))
        if st.button("✅ " + t("Complete setup and generate the dashboard"), type="primary"):
            db.execute("UPDATE companies SET setup_complete = 1 WHERE id = ?", (cid,))
            res = engine_risk.run(cid)
            audit.log(cid, user["email"], "setup_completed", "company", cid, str(res))
            st.session_state["nav"] = "dashboard"
            st.rerun()
    b1, _, b2 = st.columns([1, 4, 1])
    if step > 0:
        b1.button("← " + t("Back"), on_click=_nav, args=(step - 1,), key="wz_back")
    if step < len(STEPS) - 1:
        b2.button(t("Next") + " →", on_click=_nav, args=(step + 1,), key="wz_next")


def notifications_form(ctx: dict, s: dict, key: str = "notif") -> None:
    cid, user = ctx["cid"], ctx["user"]
    with st.form(key):
        st.markdown("**NTFY** — " + t("free push notifications to phone or desktop (install the ntfy app and subscribe to your topic)"))
        c1, c2, c3 = st.columns([1, 2, 2])
        ne = c1.checkbox(t("Enable NTFY"), value=s["ntfy"]["enabled"])
        ns = c2.text_input(t("Server"), value=s["ntfy"]["server"])
        nt = c3.text_input(t("Topic (use a long, hard-to-guess name)"), value=s["ntfy"]["topic"])
        st.markdown("**" + t("E-mail (SMTP)") + "**")
        e1, e2, e3 = st.columns(3)
        ee = e1.checkbox(t("Enable e-mail"), value=s["email"]["enabled"])
        host = e2.text_input(t("SMTP host"), value=s["email"]["smtp_host"])
        port = e3.number_input(t("SMTP port"), 1, 65535, int(s["email"]["smtp_port"] or 587))
        su = e1.text_input(t("SMTP user"), value=s["email"]["smtp_user"])
        sender = e2.text_input(t("Sender address"), value=s["email"]["sender"])
        rec = e3.text_input(t("Manager recipients (comma-separated)"), value=s["email"]["recipients"])
        st.caption(t("The SMTP password is never stored here: set it as the SMTP_PASSWORD secret of the deployment."))
        st.markdown("**" + t("Notify on") + "**")
        o = s["notify_on"]
        k1, k2, k3, k4 = st.columns(4)
        on = {"absence": k1.checkbox(t("Absence recorded"), value=o.get("absence", True)),
              "critical_risk": k2.checkbox(t("New critical risk"), value=o.get("critical_risk", True)),
              "reassignment": k3.checkbox(t("Reassignment request"), value=o.get("reassignment", True)),
              "overcapacity": k4.checkbox(t("Overcapacity"), value=o.get("overcapacity", True))}
        if st.form_submit_button(t("Save notification settings"), type="primary"):
            s["ntfy"] = {"enabled": ne, "server": ns.strip() or "https://ntfy.sh", "topic": nt.strip()}
            s["email"] = {"enabled": ee, "smtp_host": host.strip(), "smtp_port": int(port), "smtp_user": su.strip(), "sender": sender.strip(),
                          "recipients": rec.strip()}
            s["notify_on"] = on
            db.save_settings(cid, s)
            audit.log(cid, user["email"], "notification_settings_saved", "settings", "", f"ntfy={ne} email={ee}")
            st.success(t("Saved."))


def render(ctx: dict) -> None:
    cid, user = ctx["cid"], ctx["user"]
    ui.page_header("settings", t("Company settings & setup"), t("Setup wizard, thresholds, notifications"))
    comp = ctx["company"]
    if not comp["setup_complete"]:
        st.info("👋 " + t("Welcome! Complete these 9 steps to set up your workspace. You can come back and change anything later."))
    tabs = st.tabs(["🧙 " + t("Setup wizard"), "📐 " + t("Thresholds & scoring"), "🔔 " + t("Notifications"), "🎬 " + t("Demo data")])
    with tabs[0]:
        wizard(ctx)
    s = db.settings(cid)
    with tabs[1]:
        with st.form("thr"):
            st.markdown("**" + t("Workload bands (% of effective capacity)") + "**")
            c1, c2, c3 = st.columns(3)
            u = c1.number_input(t("Underutilised below"), 0, 200, int(s["thresholds"]["under"]))
            h = c2.number_input(t("High workload above"), 0, 200, int(s["thresholds"]["high"]))
            o = c3.number_input(t("Overcapacity above"), 0, 300, int(s["thresholds"]["over"]))
            st.markdown("**" + t("Other rules") + "**")
            d1, d2 = st.columns(2)
            win = d1.number_input(t("Upcoming-deadline window (days)"), 1, 120, int(s["deadline_window_days"]))
            bw = d2.number_input(t("Budget warning at (% of budget)"), 1, 200, int(s["budget_warning_pct"]))
            st.markdown("**" + t("Risk priority bands (score = P × I)") + "**")
            r1, r2, r3 = st.columns(3)
            bm = r1.number_input(t("Medium from"), 2, 25, int(s["risk_bands"]["medium"]))
            bh = r2.number_input(t("High from"), 2, 25, int(s["risk_bands"]["high"]))
            bc = r3.number_input(t("Critical from"), 2, 25, int(s["risk_bands"]["critical"]))
            if st.form_submit_button(t("Save"), type="primary"):
                if not (u < h <= o) or not (bm < bh < bc):
                    st.error(t("Thresholds must be increasing."))
                else:
                    s["thresholds"] = {"under": u, "high": h, "over": o}
                    s["deadline_window_days"], s["budget_warning_pct"] = int(win), int(bw)
                    s["risk_bands"] = {"medium": bm, "high": bh, "critical": bc}
                    db.save_settings(cid, s)
                    res = engine_risk.run(cid)
                    audit.log(cid, user["email"], "thresholds_saved", "settings", "", str(s["thresholds"]))
                    st.success(t("Saved. Workload and risks recalculated ({c} new, {u} updated, {x} cleared).", c=res["created"], u=res["updated"], x=res["cleared"]))
    with tabs[2]:
        notifications_form(ctx, s, key="notif_tab")
    with tabs[3]:
        if comp.get("is_demo"):
            st.markdown(t("Restore the NOVATECH demonstration workspace to its initial state (all changes made during a demo are lost). Demo accounts keep the same e-mails and password."))
            if st.checkbox(t("I understand that all demo changes will be lost")) and st.button("♻️ " + t("Reset demo data"), type="primary"):
                seed.reset_demo()
                lang = st.session_state.get("lang", "en")
                st.session_state.clear()
                st.session_state["lang"] = lang
                st.rerun()
        else:
            st.info(t("This is a real company workspace; there is no demo data to reset."))
