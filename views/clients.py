"""Client and contract portfolio."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from hub import audit, db, metrics, perms, ui
from hub.i18n import t


def render(ctx: dict) -> None:
    cid, edit, role, user = ctx["cid"], ctx["can_edit"], ctx["role"], ctx["user"]
    cur = ctx["company"]["currency"] or "EUR"
    show_value = role in perms.CONTRACT_VALUE_ROLES
    today = date.today()
    ui.page_header("clients", t("Clients & contracts"), t("Portfolio, renewals, SLAs and data-protection obligations"))
    c = db.t_df("clients", cid, order="name")
    if c.empty:
        st.info(t("No clients yet."))
    ph = metrics.projects_health(cid)
    ev = db.t_df("compliance_evidence", cid)
    if not c.empty:
        c["projects"] = c["id"].map(ph.groupby("client_id")["code"].apply(lambda x: ", ".join(x)) if not ph.empty else {}).fillna("")
        bad = ph[ph["health"].isin(["At risk", "Critical"])] if not ph.empty else ph
        c["project_issue"] = c["id"].isin(bad["client_id"]) if not bad.empty else False
        rn = pd.to_datetime(c["renewal_date"], errors="coerce").dt.date
        c["renewal_soon"] = rn.notna() & (rn <= today + timedelta(days=60)) & (rn >= today)
        miss = ev[ev["status"].isin(["Missing", "Expired"])]["client_id"].unique() if not ev.empty else []
        c["evidence_gap"] = c["id"].isin(miss)
        c["why"] = c.apply(lambda r: "; ".join(x for x, f in ((t("project at risk"), r["project_issue"]), (t("renewal ≤ 60 days"), r["renewal_soon"]),
                                                               (t("GDPR evidence gap"), r["evidence_gap"])) if f), axis=1)
        c["at_risk"] = c["why"] != ""
        facts = json.loads(ctx["company"].get("case_facts") or "{}")
        ui.kpi_row([
            (t("Client records"), len(c), t("case study: {n} active clients", n=facts.get("active_clients")) if facts else "", "neutral"),
            (t("Recurring contracts"), int(c["recurring"].sum()), "", "neutral"),
            (t("EU / EEA clients"), int(c["is_eu"].sum()), t("case study: EU = 70% of recurring revenue") if facts else "", "neutral"),
            (t("Clients potentially at risk"), int(c["at_risk"].sum()), t("potential, not a confirmed breach"), "warn" if c["at_risk"].any() else "good"),
        ])
    tabs = st.tabs(["🏢 " + t("Portfolio"), "📈 " + t("Portfolio dashboard"), "✏️ " + t("Add / edit")])
    with tabs[0]:
        cols = {"name": "Client", "contact": "Contact", "country": "Country", "projects": "Projects", "contract_start": "Contract start",
                "contract_end": "Contract end", "renewal_date": "Renewal", "recurring": "Recurring", "sla": "SLA",
                "dp_obligations": "Data-protection obligations", "incident_obligations": "Incident communication", "why": "Potential risk"}
        if show_value:
            cols["contract_value"] = "Contract value"
        else:
            st.caption(t("Contract values are hidden for your role."))
        only = st.toggle(t("Show only clients potentially at risk"))
        ui.table(c[c["at_risk"]] if (only and not c.empty) else c, cols, height=480)
    with tabs[1]:
        if not c.empty:
            c1, c2 = st.columns(2)
            g = c.groupby("country").size().reset_index(name="n").sort_values("n")
            c1.plotly_chart(ui.style_fig(px.bar(g, y="country", x="n", orientation="h", title=t("Clients by country"),
                                                labels={"country": "", "n": t("Clients")}).update_traces(marker_color=ui.ACCENT), legend=False), key="cl1")
            r = c.copy()
            r["renewal"] = pd.to_datetime(r["renewal_date"])
            r = r[(r["renewal"] >= pd.Timestamp(today)) & (r["renewal"] <= pd.Timestamp(today + timedelta(days=365)))]
            if not r.empty:
                fig = px.scatter(r, x="renewal", y="name", color="at_risk", color_discrete_map={True: "#e06c1f", False: ui.ACCENT},
                                 title=t("Contract renewals in the next 12 months"), labels={"renewal": "", "name": ""})
                fig.update_traces(marker=dict(size=12))
                fig.for_each_trace(lambda tr: tr.update(name=t("Potentially at risk") if tr.name == "True" else t("No flag")))
                c2.plotly_chart(ui.style_fig(fig), key="cl2")
            if show_value:
                v = c.groupby(c["is_eu"].map({1: "EU / EEA", 0: t("Outside EU")}))["contract_value"].sum().reset_index()
                st.plotly_chart(ui.style_fig(px.pie(v, names="is_eu", values="contract_value", hole=0.5,
                                                    title=t("Sample contract value by region (demo records, not the case-study 70% figure)"))), key="cl3")
    with tabs[2]:
        if not edit:
            st.info(t("Read-only for your role."))
        else:
            opts = [None] + c["id"].tolist() if not c.empty else [None]
            sel = st.selectbox(t("Client"), opts, format_func=lambda i: t("New client") if i is None else c.set_index("id").loc[i, "name"])
            r = db.t_get("clients", cid, int(sel)) if sel else {}
            with st.form(f"cl_{sel}"):
                a, b, d = st.columns(3)
                name = a.text_input(t("Client name") + " *", value=r.get("name", ""))
                contact = b.text_input(t("Client contact"), value=r.get("contact", "") or "")
                country = d.text_input(t("Country"), value=r.get("country", "") or "")
                eu = a.checkbox(t("EU / EEA client (GDPR applies)"), value=bool(r.get("is_eu", 1)))
                rec = b.checkbox(t("Recurring revenue"), value=bool(r.get("recurring", 1)))
                val = d.number_input(t("Contract value") + f" ({cur})", 0.0, value=float(r.get("contract_value") or 0), step=1000.0, disabled=not show_value)
                cs = a.date_input(t("Contract start"), date.fromisoformat(r["contract_start"]) if r.get("contract_start") else today)
                ce = b.date_input(t("Contract end"), date.fromisoformat(r["contract_end"]) if r.get("contract_end") else today + timedelta(days=365))
                rn = d.date_input(t("Renewal date"), date.fromisoformat(r["renewal_date"]) if r.get("renewal_date") else today + timedelta(days=300))
                sla = st.text_input(t("Service-level agreement"), value=r.get("sla", "") or "")
                dl = st.text_input(t("Required deliverables"), value=r.get("deliverables", "") or "")
                dp = st.text_input(t("Data-protection obligations"), value=r.get("dp_obligations", "") or "")
                ic = st.text_input(t("Incident communication obligations"), value=r.get("incident_obligations", "") or "")
                evn = st.text_input(t("Contractual evidence (references)"), value=r.get("evidence_notes", "") or "")
                if st.form_submit_button(t("Save client"), type="primary"):
                    if not name.strip():
                        st.error(t("Name is required."))
                    else:
                        data = {"name": name, "contact": contact, "country": country, "is_eu": int(eu), "recurring": int(rec),
                                "contract_start": str(cs), "contract_end": str(ce), "renewal_date": str(rn), "sla": sla, "deliverables": dl,
                                "dp_obligations": dp, "incident_obligations": ic, "evidence_notes": evn}
                        if show_value:
                            data["contract_value"] = val
                        if sel:
                            db.t_update("clients", cid, int(sel), data)
                        else:
                            db.t_insert("clients", cid, data)
                        audit.log(cid, user["email"], "client_saved", "client", sel or name)
                        st.success(t("Saved."))
                        st.rerun()
