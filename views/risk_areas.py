"""Case-study risk categories: cloud services, remote working, digital tools, incidents & unusual signals."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from hub import audit, db, engine_risk, ui
from hub.i18n import lang, t, tf

SIG_TYPES = ["Incident ticket", "Help-desk ticket", "Security alert", "Near miss", "Unusual signal"]
SIG_STATUS = ["Warning signal", "Under investigation", "Incident under investigation", "Confirmed fact", "Resolved issue", "Closed - no issue"]
TOOL_STATES = ["Approved", "Under review", "Not approved (shadow IT suspected)", "Retired"]


def render(ctx: dict) -> None:
    cid, edit, user = ctx["cid"], ctx["can_edit"], ctx["user"]
    ui.page_header("risk_areas", t("Risk areas & signals"), t("Evidence for the seven case-study risk categories"))
    tabs = st.tabs(["🧭 " + t("Overview"), "☁️ " + t("Cloud services"), "🏠 " + t("Remote working"), "🧰 " + t("Digital tools"),
                    "📡 " + t("Incidents & signals")])
    with tabs[0]:
        reg = engine_risk.register(cid, lang())
        if not reg.empty:
            o = reg[reg["status"].isin(engine_risk.OPEN_STATUSES)]
            g = o.groupby(["case_category", "priority"]).size().reset_index(name="n")
            g["cat"] = g["case_category"].map(tf)
            fig = px.bar(g, y="cat", x="n", color="priority", orientation="h", color_discrete_map=ui.PRIORITY_COLORS,
                         title=t("Open risks by case-study category"), labels={"cat": "", "n": t("Risks")},
                         category_orders={"priority": ["Critical", "High", "Medium", "Low"]})
            fig.for_each_trace(lambda tr: tr.update(name=tf(tr.name)))
            st.plotly_chart(ui.style_fig(fig, height=380), key="ra_over")
        st.caption(t("Each category links the case-study hypothesis (R1-R12) with live evidence recorded in the tabs of this page."))
    with tabs[1]:
        cs = db.t_df("cloud_services", cid)
        ui.table(cs, {"name": "Service", "provider": "Provider", "owner": "Owner", "criticality": "Criticality", "provider_sla": "Provider SLA",
                      "dependencies": "Dependencies", "outages_12m": "Outages (12m)", "last_restore_test": "Last restore test",
                      "rto_hours": "RTO h", "rpo_hours": "RPO h", "recovery_evidence": "Recovery evidence"}, translate_values=("criticality", "recovery_evidence"))
        if edit:
            with st.form("cs"):
                st.markdown("**" + t("Add or update a cloud service") + "**")
                opts = [None] + cs["id"].tolist() if not cs.empty else [None]
                sid = st.selectbox(t("Service"), opts, format_func=lambda i: t("New service") if i is None else cs.set_index("id").loc[i, "name"])
                c1, c2, c3 = st.columns(3)
                name = c1.text_input(t("Name"))
                prov = c2.text_input(t("Provider"))
                own = c3.text_input(t("Owner"))
                crit = c1.selectbox(t("Criticality"), ["Critical", "High", "Medium", "Low"], format_func=tf)
                out = c2.number_input(t("Outages (12m)"), 0, 50, 0)
                lr = c3.date_input(t("Last restore test"), value=None)
                ev = c1.selectbox(t("Recovery evidence"), ["Not recorded", "Restore test report on file", "DR plan on file"], format_func=tf)
                rto = c2.number_input("RTO h", 0.0, 500.0, 8.0)
                rpo = c3.number_input("RPO h", 0.0, 500.0, 4.0)
                st.caption(t("Leave the name empty to update only the fields of the selected service."))
                if st.form_submit_button(t("Save"), type="primary"):
                    data = {"criticality": crit, "outages_12m": int(out), "recovery_evidence": ev, "rto_hours": rto, "rpo_hours": rpo}
                    if lr:
                        data["last_restore_test"] = str(lr)
                    if name:
                        data.update(name=name, provider=prov, owner=own)
                    if sid:
                        db.t_update("cloud_services", cid, int(sid), data)
                    elif name:
                        db.t_insert("cloud_services", cid, data)
                    audit.log(cid, user["email"], "cloud_service_saved", "cloud_service", sid or name)
                    engine_risk.run(cid)
                    st.rerun()
    with tabs[2]:
        e = db.df("""SELECT e.*, l.name AS location FROM employees e LEFT JOIN locations l ON l.id = e.location_id
                     WHERE e.company_id = ? AND e.active = 1""", (cid,))
        rem = e[e["remote_eligible"] == 1] if not e.empty else e
        n = len(rem)
        pct = n / len(e) * 100 if len(e) else 0
        ui.kpi_row([
            (t("Remote-eligible employees"), n, t("{p:.0f}% of staff (case study: 40%)", p=pct), "neutral"),
            (t("MFA verified"), int((rem["mfa_status"] == "Verified").sum()), t("of {n}", n=n), "warn"),
            (t("Compliant devices"), int((rem["device_status"] == "Compliant").sum()), t("of {n}", n=n), "warn"),
            (t("EDR verified"), int((rem["edr_status"] == "Verified").sum()), t("of {n}", n=n), "warn"),
        ])
        st.caption(t("A control is only counted when its status has been entered as Verified/Compliant. 'Not recorded' means no evidence yet - not that the control is missing."))
        if not rem.empty:
            m = rem.melt(id_vars=["name"], value_vars=["mfa_status", "device_status", "vpn_status", "edr_status"], var_name="control", value_name="status")
            g = m.groupby(["control", "status"]).size().reset_index(name="n")
            g["control"] = g["control"].map({"mfa_status": "MFA", "device_status": t("Device compliance"), "vpn_status": "VPN / Zero-trust", "edr_status": "EDR"})
            g["st"] = g["status"].map(tf)
            colors = {"Verified": "#3a9a68", "Compliant": "#3a9a68", "Not recorded": "#b9c2cf", "Not enabled": "#b3261e",
                      "Non-compliant": "#b3261e", "Exception approved": "#d9a400"}
            fig = px.bar(g, x="control", y="n", color="status", color_discrete_map=colors, title=t("Remote-work control evidence"),
                         labels={"control": "", "n": t("Employees")})
            fig.for_each_trace(lambda tr: tr.update(name=tf(tr.name)))
            st.plotly_chart(ui.style_fig(fig), key="ra_remote")
            ui.table(rem, {"name": "Employee", "location": "Location", "department": "Department", "mfa_status": "MFA",
                           "device_status": "Device", "vpn_status": "VPN", "edr_status": "EDR"},
                     translate_values=("mfa_status", "device_status", "vpn_status", "edr_status"))
            st.caption(t("Update individual controls from Employees → Add / edit."))
    with tabs[3]:
        tl = db.t_df("digital_tools", cid)
        ui.table(tl, {"name": "Tool", "owner": "Owner", "approved": "Approval", "config_review_date": "Last config review",
                      "integrations": "Integrations", "change_records": "Change records", "concern": "Concern", "remediation": "Remediation"},
                 translate_values=("approved",))
        if edit:
            with st.form("tool"):
                opts = [None] + tl["id"].tolist() if not tl.empty else [None]
                tid = st.selectbox(t("Tool"), opts, format_func=lambda i: t("New tool") if i is None else tl.set_index("id").loc[i, "name"])
                c1, c2 = st.columns(2)
                name = c1.text_input(t("Name (new tool)"))
                owner = c2.text_input(t("Owner"))
                appr = c1.selectbox(t("Approval"), TOOL_STATES, format_func=tf)
                rev = c2.date_input(t("Configuration review date"), value=None)
                concern = st.text_input(t("Configuration concern"))
                rem_ = st.text_input(t("Remediation action / owner"))
                if st.form_submit_button(t("Save"), type="primary"):
                    data = {"approved": appr, "concern": concern, "remediation": rem_}
                    if owner:
                        data["owner"] = owner
                    if rev:
                        data["config_review_date"] = str(rev)
                    if tid:
                        db.t_update("digital_tools", cid, int(tid), data)
                    elif name:
                        data["name"] = name
                        db.t_insert("digital_tools", cid, data)
                    audit.log(cid, user["email"], "tool_saved", "digital_tool", tid or name, concern)
                    engine_risk.run(cid)
                    st.rerun()
    with tabs[4]:
        sg = db.df("""SELECT s.*, l.name AS location FROM signals s LEFT JOIN locations l ON l.id = s.location_id
                      WHERE s.company_id = ? ORDER BY s.signal_date DESC""", (cid,))
        st.caption(t("Signals are observations, not confirmed incidents. Grouping shows possible patterns; a shared root cause must be supported by evidence."))
        if not sg.empty:
            c1, c2 = st.columns([1, 2])
            grp = c1.selectbox(t("Group signals by"), ["system", "location", "team", "supplier", "signal_type", "week"],
                               format_func=lambda g: {"system": t("System"), "location": t("Location"), "team": t("Team"), "supplier": t("Supplier"),
                                                      "signal_type": t("Type"), "week": t("Time period (week)")}[g])
            days = c1.slider(t("Look-back (days)"), 7, 120, 60)
            s2 = sg[pd.to_datetime(sg["signal_date"]).dt.date >= date.today() - timedelta(days=days)].copy()
            s2["week"] = pd.to_datetime(s2["signal_date"]).dt.to_period("W").astype(str)
            s2[grp] = s2[grp].replace("", "(none)").fillna("(none)")
            g = s2.groupby(grp).size().reset_index(name="n").sort_values("n", ascending=False)
            with c2:
                fig = px.bar(g, x=grp, y="n", title=t("Signals by group (last {d} days)", d=days), labels={grp: "", "n": t("Signals")})
                fig.update_traces(marker_color=[("#b3261e" if v >= 3 else ui.ACCENT) for v in g["n"]])
                st.plotly_chart(ui.style_fig(fig, legend=False), key="ra_sig")
            rep = g[g["n"] >= 3]
            for _, r in rep.iterrows():
                st.warning(t("{n} signals share {g} = '{v}'. Investigation recommended to check whether they have a common root cause (not yet established).",
                             n=r["n"], g=grp, v=r[grp]))
        ui.table(sg, {"signal_date": "Date", "signal_type": "Type", "title": "Signal", "system": "System", "location": "Location",
                      "team": "Team", "supplier": "Supplier", "severity": "Severity", "status": "Status", "root_cause": "Root cause"},
                 translate_values=("signal_type", "severity", "status"))
        if edit:
            c1, c2 = st.columns(2)
            with c1.form("sig_new"):
                st.markdown("**" + t("Record a signal") + "**")
                locs = db.t_rows("locations", cid)
                sd = st.date_input(t("Date"), date.today())
                ty = st.selectbox(t("Type"), SIG_TYPES, format_func=tf)
                ti = st.text_input(t("Description"))
                sy = st.text_input(t("System"))
                lo = st.selectbox(t("Location"), [None] + [x["id"] for x in locs], format_func=lambda i: "—" if i is None else next(x["name"] for x in locs if x["id"] == i))
                te = st.text_input(t("Team"))
                su = st.text_input(t("Supplier"))
                sev = st.selectbox(t("Severity"), ["Low", "Medium", "High"], format_func=tf)
                if st.form_submit_button(t("Record signal")) and ti.strip():
                    db.t_insert("signals", cid, {"signal_date": str(sd), "signal_type": ty, "title": ti, "system": sy, "location_id": lo,
                                                 "team": te, "supplier": su, "severity": sev, "status": "Warning signal"})
                    audit.log(cid, user["email"], "signal_recorded", "signal", "", ti)
                    engine_risk.run(cid)
                    st.rerun()
            with c2.form("sig_upd"):
                st.markdown("**" + t("Update a signal") + "**")
                if not sg.empty:
                    sid = st.selectbox(t("Signal"), sg["id"].tolist(), format_func=lambda i: f"{sg.set_index('id').loc[i, 'signal_date']} · {sg.set_index('id').loc[i, 'title']}")
                    ns = st.selectbox(t("Status"), SIG_STATUS, format_func=tf)
                    rc = st.text_input(t("Root cause (only if supported by evidence)"))
                    if st.form_submit_button(t("Update signal")):
                        db.t_update("signals", cid, int(sid), {"status": ns, "root_cause": rc})
                        audit.log(cid, user["email"], "signal_updated", "signal", sid, f"{ns} {rc}")
                        engine_risk.run(cid)
                        st.rerun()
                else:
                    st.form_submit_button(t("Update signal"), disabled=True)
