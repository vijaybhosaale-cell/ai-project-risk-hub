"""Joiner-Mover-Leaver access lifecycle tracking (status tracking only; no external IdP integration)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from hub import audit, db, engine_risk, ui
from hub.i18n import t, tf

EVENTS = ["Joiner", "Mover", "Leaver", "Project access"]


def render(ctx: dict) -> None:
    cid, edit, user = ctx["cid"], ctx["can_edit"], ctx["user"]
    today = date.today()
    ui.page_header("access", t("Access lifecycle (JML)"), t("Joiner · Mover · Leaver access requests, approvals, reviews and revocation"))
    st.info(t("This prototype tracks access status only. It does not create, change or disable accounts in external systems."))
    ar = db.df("""SELECT a.*, e.name, e.department, e.active AS emp_active FROM access_requests a JOIN employees e ON e.id = a.employee_id
                  WHERE a.company_id = ? ORDER BY a.id DESC""", (cid,))
    if not ar.empty:
        rd = pd.to_datetime(ar["review_date"], errors="coerce").dt.date
        lr = pd.to_datetime(ar["last_reviewed"], errors="coerce").dt.date
        ar["review_overdue"] = (ar["activation_status"] == "Active") & rd.notna() & (rd < today) & (lr.isna() | (lr < rd))
    ui.kpi_row([
        (t("Pending approvals"), int((ar["approval_status"] == "Pending").sum()) if not ar.empty else 0, "", "warn"),
        (t("Overdue access reviews"), int(ar["review_overdue"].sum()) if not ar.empty else 0, "", "bad"),
        (t("Leaver access not revoked"), int(ar["revocation_status"].isin(["Pending", "Overdue"]).sum()) if not ar.empty else 0, "", "bad"),
        (t("Active privileged rights"), int(((ar["privileged"] == 1) & (ar["activation_status"] == "Active")).sum()) if not ar.empty else 0, "", "neutral"),
    ])
    tabs = st.tabs(["📋 " + t("Requests"), "⚙️ " + t("Process a request"), "➕ " + t("New request"), "🚪 " + t("Record a departure / move")])
    with tabs[0]:
        f = st.columns(3)
        ev = f[0].multiselect(t("Lifecycle event"), EVENTS, placeholder=t("All"), format_func=tf)
        only = f[1].selectbox(t("Show"), ["All", "Needs action"], format_func=tf)
        x = ar.copy()
        if ev and not x.empty:
            x = x[x["lifecycle_event"].isin(ev)]
        if only == "Needs action" and not x.empty:
            x = x[(x["approval_status"] == "Pending") | x["review_overdue"] | x["revocation_status"].isin(["Pending", "Overdue"]) |
                  ((x["approval_status"] == "Approved") & (x["activation_status"] == "Not activated"))]
        ui.table(x, {"name": "Employee", "lifecycle_event": "Event", "system": "System", "permission": "Permission", "privileged": "Privileged",
                     "justification": "Justification", "requester": "Requester", "approver": "Approver", "approval_status": "Approval",
                     "activation_status": "Activation", "review_date": "Review date", "review_overdue": "Review overdue",
                     "revocation_status": "Revocation"},
                 translate_values=("lifecycle_event", "approval_status", "activation_status", "revocation_status"), height=440)
    with tabs[1]:
        if not edit or ar.empty:
            st.info(t("Read-only for your role.") if not edit else t("No requests."))
        else:
            rid = st.selectbox(t("Request"), ar["id"].tolist(),
                               format_func=lambda i: f"#{i} · {ar.set_index('id').loc[i, 'name']} · {ar.set_index('id').loc[i, 'system']} · {tf(ar.set_index('id').loc[i, 'approval_status'])}")
            r = ar[ar["id"] == rid].iloc[0]
            st.markdown(f"**{r['name']}** ({r['department']}) · {tf(r['lifecycle_event'])} · {r['system']} — {r['permission']}"
                        + (" · 🔴 " + t("privileged") if r["privileged"] else "") + f"  \n{t('Justification')}: {r['justification']}")
            b = st.columns(5)
            def upd(data, action):
                db.t_update("access_requests", cid, int(rid), data)
                audit.log(cid, user["email"], action, "access_request", rid, str(data))
                engine_risk.run(cid)
                st.rerun()
            if b[0].button("✅ " + t("Approve"), disabled=r["approval_status"] != "Pending"):
                if r["requester"] and r["requester"] == user["email"]:
                    st.error(t("The requester cannot approve their own request (segregation of duties)."))
                else:
                    upd({"approval_status": "Approved", "approver": user["email"]}, "access_approved")
            if b[1].button("✖ " + t("Reject"), disabled=r["approval_status"] != "Pending"):
                upd({"approval_status": "Rejected", "approver": user["email"]}, "access_rejected")
            if b[2].button("🔌 " + t("Mark activated"), disabled=not (r["approval_status"] == "Approved" and r["activation_status"] != "Active")):
                upd({"activation_status": "Active", "review_date": str(today + timedelta(days=90))}, "access_activated")
            if b[3].button("🔍 " + t("Record review"), disabled=r["activation_status"] != "Active"):
                upd({"last_reviewed": str(today), "review_date": str(today + timedelta(days=90))}, "access_reviewed")
            if b[4].button("⛔ " + t("Mark revoked"), disabled=r["activation_status"] != "Active" and r["revocation_status"] == "Not required"):
                upd({"activation_status": "Disabled", "revocation_status": "Revoked"}, "access_revoked")
            if r["approval_status"] != "Approved":
                st.caption(t("Activation is only possible after approval. Completing training never activates access automatically."))
    with tabs[2]:
        if not edit:
            st.info(t("Read-only for your role."))
        else:
            emps = db.t_rows("employees", cid, "active = 1", order="name")
            with st.form("acc_new"):
                c1, c2 = st.columns(2)
                eid = c1.selectbox(t("Employee"), [e["id"] for e in emps], format_func=lambda i: next(e["name"] for e in emps if e["id"] == i))
                evn = c2.selectbox(t("Lifecycle event"), EVENTS, format_func=tf)
                sysn = c1.text_input(t("System or application") + " *")
                perm = c2.text_input(t("Requested permission") + " *")
                priv = c1.checkbox(t("Privileged access"))
                rev = c2.date_input(t("Review date"), today + timedelta(days=90))
                just = st.text_input(t("Business justification") + " *")
                if st.form_submit_button(t("Submit request"), type="primary"):
                    if not (sysn.strip() and perm.strip() and just.strip()):
                        st.error(t("System, permission and justification are required."))
                    else:
                        db.t_insert("access_requests", cid, {"employee_id": eid, "lifecycle_event": evn, "system": sysn, "permission": perm,
                                                             "privileged": int(priv), "justification": just, "requester": user["email"],
                                                             "approval_status": "Pending", "activation_status": "Not activated",
                                                             "review_date": str(rev), "revocation_status": "Not required", "created_at": db.now()})
                        audit.log(cid, user["email"], "access_requested", "employee", eid, f"{sysn}/{perm}")
                        st.success(t("Request submitted for approval."))
    with tabs[3]:
        if not edit:
            st.info(t("Read-only for your role."))
        else:
            emps = db.t_rows("employees", cid, "active = 1", order="name")
            with st.form("leaver"):
                eid = st.selectbox(t("Employee"), [e["id"] for e in emps], format_func=lambda i: next(e["name"] for e in emps if e["id"] == i))
                kind = st.radio(t("Event"), ["Leaver", "Mover"], format_func=tf, horizontal=True)
                newdep = st.text_input(t("New department (mover)"))
                ld = st.date_input(t("Effective date"), today)
                if st.form_submit_button(t("Record"), type="primary"):
                    act = db.t_rows("access_requests", cid, "employee_id = ? AND activation_status = 'Active'", (eid,))
                    for a in act:
                        db.t_update("access_requests", cid, a["id"], {"revocation_status": "Pending", "lifecycle_event": kind})
                    if kind == "Leaver":
                        db.t_update("employees", cid, eid, {"active": 0, "employment_status": "Left", "leave_date": str(ld)})
                    elif newdep:
                        db.t_update("employees", cid, eid, {"department": newdep})
                    audit.log(cid, user["email"], f"{kind.lower()}_recorded", "employee", eid, f"{len(act)} active right(s) set to revocation pending")
                    engine_risk.run(cid)
                    st.success(t("{n} active access right(s) marked 'revocation pending' for review. Disable them in the real systems, then mark them revoked here.", n=len(act)))
