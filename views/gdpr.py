"""GDPR / data-protection evidence register for European clients (spec section 19, completed)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from hub import audit, db, engine_risk, ui
from hub.i18n import t, tf
from hub.seed import EVIDENCE_TYPES

STATUSES = ["Missing", "Draft", "In review", "Verified", "Expired", "Not applicable"]
COLORS = {"Verified": "#3a9a68", "In review": "#d9a400", "Draft": "#7fa7d9", "Missing": "#b3261e", "Expired": "#e06c1f", "Not applicable": "#b9c2cf"}


def render(ctx: dict) -> None:
    cid, edit, user = ctx["cid"], ctx["can_edit"], ctx["user"]
    ui.page_header("gdpr", t("GDPR evidence"), t("Data-protection evidence register for European clients"))
    st.caption(t("Tracked evidence: 1) data-processing agreements, 2) data maps / records of processing, 3) relevant contract clauses, "
                 "4) incident-notification procedure, 5) sub-processor list and international-transfer assessment, 6) retention and deletion rules. "
                 "This register supports compliance work; it is not legal advice."))
    ev = db.df("""SELECT ce.*, c.name AS client FROM compliance_evidence ce JOIN clients c ON c.id = ce.client_id
                  WHERE ce.company_id = ? AND c.is_eu = 1""", (cid,))
    if ev.empty:
        st.info(t("No evidence records yet. Add evidence for your European clients below."))
    else:
        ui.kpi_row([
            (t("Evidence items"), len(ev), t("{n} clients", n=ev["client_id"].nunique()), "neutral"),
            (t("Verified"), int((ev["status"] == "Verified").sum()), f"{(ev['status'] == 'Verified').mean() * 100:.0f}%", "good"),
            (t("Missing or expired"), int(ev["status"].isin(["Missing", "Expired"]).sum()), t("raises a compliance risk"), "bad"),
            (t("Overdue"), int(((pd.to_datetime(ev["due_date"]).dt.date < date.today()) & (ev["status"] != "Verified")).sum()), t("past due date, not verified"), "warn"),
        ])
        piv = ev.pivot_table(index="client", columns="evidence_type", values="status", aggfunc="first").fillna("—")
        piv = piv[[c for c in EVIDENCE_TYPES if c in piv.columns]]
        disp = piv.map(tf)
        disp.columns = [t(c) for c in disp.columns]
        inv = {tf(k): v for k, v in COLORS.items()}
        st.markdown("**" + t("Evidence matrix") + "**")
        st.dataframe(disp.style.map(lambda v: f"background-color:{inv.get(v, '#fff')};color:{'white' if v in inv else '#333'};font-weight:600"),
                     height=min(420, 40 + 36 * len(disp)))
    if edit:
        c1, c2 = st.columns(2)
        with c1.form("ev_upd"):
            st.markdown("**" + t("Update evidence") + "**")
            if not ev.empty:
                eid = st.selectbox(t("Evidence item"), ev["id"].tolist(), format_func=lambda i: f"{ev.set_index('id').loc[i, 'client']} · {t(ev.set_index('id').loc[i, 'evidence_type'])} ({tf(ev.set_index('id').loc[i, 'status'])})")
                stt = st.selectbox(t("Status"), STATUSES, format_func=tf)
                ref = st.text_input(t("Document reference"))
                note = st.text_input(t("Notes"))
                if st.form_submit_button(t("Save"), type="primary"):
                    db.t_update("compliance_evidence", cid, int(eid), {"status": stt, "reference": ref, "notes": note,
                                                                        "last_review": str(date.today()) if stt == "Verified" else None})
                    audit.log(cid, user["email"], "evidence_updated", "compliance_evidence", eid, f"{stt} {ref}")
                    engine_risk.run(cid)
                    st.rerun()
            else:
                st.form_submit_button(t("Save"), disabled=True)
        with c2.form("ev_new"):
            st.markdown("**" + t("Add evidence") + "**")
            clients = db.t_rows("clients", cid, "is_eu = 1", order="name")
            cl = st.selectbox(t("Client"), [x["id"] for x in clients], format_func=lambda i: next(x["name"] for x in clients if x["id"] == i)) if clients else None
            typ = st.selectbox(t("Evidence type"), EVIDENCE_TYPES, format_func=t)
            stt2 = st.selectbox(t("Status"), STATUSES, format_func=tf, key="ev2")
            owner = st.text_input(t("Owner"))
            due = st.date_input(t("Due date"))
            if st.form_submit_button(t("Add")) and cl:
                db.t_insert("compliance_evidence", cid, {"client_id": cl, "evidence_type": typ, "status": stt2, "owner": owner, "due_date": str(due)})
                audit.log(cid, user["email"], "evidence_added", "client", cl, typ)
                engine_risk.run(cid)
                st.rerun()
    if not ev.empty:
        st.markdown("**" + t("Register") + "**")
        ui.table(ev.sort_values(["client", "evidence_type"]), {"client": "Client", "evidence_type": "Evidence", "status": "Status", "owner": "Owner",
                                                               "due_date": "Due", "last_review": "Last review", "reference": "Reference"},
                 translate_values=("status", "evidence_type"))
