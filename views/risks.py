"""Risk register with explainable scoring, heat map, detail view, lifecycle and remediation actions."""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from hub import ai_interface, audit, db, engine_risk, ui
from hub.i18n import lang, t, tf


def render(ctx: dict) -> None:
    cid, edit, user = ctx["cid"], ctx["can_edit"], ctx["user"]
    ui.page_header("risks", t("Risk register"), t("Explainable risk intelligence: Score = Probability × Impact"))
    advisor = ai_interface.get_advisor()
    top = st.columns([3, 1.2])
    top[0].caption(f"🧠 {t('Engine')}: **{t(advisor.name)}** · {t('Trained AI model')}: **{t('No') if not advisor.uses_trained_model else t('Yes')}** · "
                   + t("An AI-ready interface allows an ML or language model to be plugged in later."))
    if edit and top[1].button("🔄 " + t("Run risk engine"), width="stretch"):
        res = engine_risk.run(cid, user["email"])
        audit.log(cid, user["email"], "risk_engine_run", "risks", "", str(res))
        st.success(t("Risk engine finished: {c} new, {u} updated, {x} condition(s) cleared.", c=res["created"], u=res["updated"], x=res["cleared"]))

    reg = engine_risk.register(cid, lang())
    if reg.empty:
        st.info(t("No risks recorded yet."))
    open_r = reg[reg["status"].isin(engine_risk.OPEN_STATUSES)] if not reg.empty else reg
    ui.kpi_row([
        (t("Critical"), int((open_r["priority"] == "Critical").sum()), "20–25", "bad"),
        (t("High"), int((open_r["priority"] == "High").sum()), "15–19", "warn"),
        (t("Medium"), int((open_r["priority"] == "Medium").sum()), "8–14", "neutral"),
        (t("Low"), int((open_r["priority"] == "Low").sum()), "1–7", "good"),
    ])

    tab_reg, tab_detail, tab_new = st.tabs(["📋 " + t("Register"), "🔎 " + t("Risk detail & actions"), "➕ " + t("Add a risk")])
    with tab_reg:
        f = st.columns(5)
        pri = f[0].multiselect(t("Priority"), ["Critical", "High", "Medium", "Low"], format_func=tf, placeholder=t("All"))
        stt = f[1].multiselect(t("Status"), engine_risk.RISK_STATUSES, default=list(engine_risk.OPEN_STATUSES), format_func=tf)
        evs = f[2].multiselect(t("Evidence status"), engine_risk.EVIDENCE_STATUSES, format_func=tf, placeholder=t("All"))
        cat = f[3].multiselect(t("Case category"), engine_risk.CASE_CATEGORIES, format_func=tf, placeholder=t("All"))
        src = f[4].selectbox(t("Source"), ["All", "Case study", "Rule engine", "Manual"], format_func=tf)
        q = st.text_input("🔍 " + t("Search"), placeholder=t("title, owner, project…"))
        r = reg.copy()
        if pri:
            r = r[r["priority"].isin(pri)]
        if stt:
            r = r[r["status"].isin(stt)]
        if evs:
            r = r[r["evidence_status"].isin(evs)]
        if cat:
            r = r[r["case_category"].isin(cat)]
        if src != "All" and not r.empty:
            r = r[r["source"].fillna("").str.startswith(src)]
        if q and not r.empty:
            ql = q.lower()
            r = r[r.apply(lambda x: ql in " ".join(str(v) for v in x.values).lower(), axis=1)]

        c1, c2 = st.columns([1, 2.2])
        with c1:
            hm = [[0] * 5 for _ in range(5)]
            for _, x in r.iterrows():
                hm[int(x["impact"]) - 1][int(x["probability"]) - 1] += 1
            z = [[(p + 1) * (i + 1) for p in range(5)] for i in range(5)]
            fig = go.Figure(go.Heatmap(z=z, x=[1, 2, 3, 4, 5], y=[1, 2, 3, 4, 5], showscale=False,
                                       colorscale=[[0, "#3a9a68"], [0.3, "#d9a400"], [0.6, "#e06c1f"], [1, "#b3261e"]],
                                       text=[[str(v) if v else "" for v in row] for row in hm], texttemplate="%{text}",
                                       textfont=dict(size=16, color="white"), hovertemplate="P=%{x} I=%{y}<extra></extra>"))
            fig.update_layout(title=t("Heat map (risks in filter)"), xaxis_title=t("Probability"), yaxis_title=t("Impact"))
            st.plotly_chart(ui.style_fig(fig, height=330, legend=False), key="heat")
        with c2:
            st.caption(t("{n} risk(s) shown", n=len(r)))
            ui.table(r, {"code": "Code", "display_title": "Risk", "case_category": "Case category", "probability": "P", "impact": "I",
                         "score": "Score", "priority": "Priority", "status": "Status", "evidence_status": "Evidence status",
                         "owner": "Owner", "project_code": "Project"},
                     translate_values=("priority", "status", "evidence_status", "case_category"), height=420)

    with tab_detail:
        if reg.empty:
            st.info(t("No risks recorded yet."))
        else:
            codes = reg["code"].tolist()
            default = st.session_state.get("risk_sel", codes[0])
            code = st.selectbox(t("Risk"), codes, index=codes.index(default) if default in codes else 0,
                                format_func=lambda c: f"{c} · {reg.set_index('code').loc[c, 'display_title']} ({reg.set_index('code').loc[c, 'score']})")
            x = reg[reg["code"] == code].iloc[0]
            col = engine_risk.PRIORITY_COLORS.get(x["priority"], "#888")
            st.markdown(f"""<div class="card"><h4>{html.escape(x['code'])} — {html.escape(x['display_title'])}</h4>
                {ui.pill(x['priority'], col)} {ui.pill(x['status'], '#5b6676')} {ui.pill(x['evidence_status'], '#2e6fb5')}
                <div style="margin-top:8px"><b>P</b> {x['probability']} × <b>I</b> {x['impact']} = <b>{x['score']}</b>
                · {html.escape(t('Category'))}: {html.escape(str(x['category']))} · {html.escape(tf(x['case_category']))}
                · {html.escape(t('Owner'))}: {html.escape(str(x['owner'] or '-'))} · {html.escape(t('Source'))}: {html.escape(str(x['source']))}</div></div>""",
                        unsafe_allow_html=True)
            st.markdown("**" + t("Why was this risk raised?") + "**")
            st.info(x["display_explanation"] or "-")
            d1, d2 = st.columns(2)
            if x["cause"]:
                d1.markdown(f"**{t('Cause / vulnerability')}**  \n{x['cause']}")
                d2.markdown(f"**{t('Risk event')}**  \n{x['event']}")
                d1.markdown(f"**{t('Potential consequences')}**  \n{x['consequences']}")
            d2.markdown(f"**{t('Evidence to collect')}**  \n{x['evidence_needed'] or '-'}")
            d1.markdown(f"**{t('Recommended action / controls')}**  \n{x['recommended_action'] or '-'}")
            if x["source"] == "Rule engine":
                st.caption(t("Raised automatically from stored data. Its score is recalculated each time the engine runs; if the condition disappears it moves to 'Condition cleared' for manager review."))

            acts = db.t_df("risk_actions", cid, "risk_id = ?", (int(x["id"]),))
            st.markdown("**" + t("Remediation actions") + "**")
            ui.table(acts, {"action": "Action", "owner": "Owner", "due_date": "Due", "status": "Status", "note": "Note", "user": "By"},
                     translate_values=("status",))
            if edit:
                e1, e2 = st.columns(2)
                with e1.form("risk_update"):
                    st.markdown("**" + t("Review / update") + "**")
                    ns = st.selectbox(t("Status"), engine_risk.RISK_STATUSES, index=engine_risk.RISK_STATUSES.index(x["status"]), format_func=tf)
                    ne = st.selectbox(t("Evidence status"), engine_risk.EVIDENCE_STATUSES,
                                      index=engine_risk.EVIDENCE_STATUSES.index(x["evidence_status"]) if x["evidence_status"] in engine_risk.EVIDENCE_STATUSES else 1,
                                      format_func=tf)
                    no = st.text_input(t("Owner"), value=x["owner"] or "")
                    p1, p2 = st.columns(2)
                    np_ = p1.slider(t("Probability"), 1, 5, int(x["probability"]))
                    ni = p2.slider(t("Impact"), 1, 5, int(x["impact"]))
                    note = st.text_input(t("Comment (stored in audit log)"))
                    if st.form_submit_button(t("Save risk"), type="primary"):
                        data = {"status": ns, "evidence_status": ne, "owner": no, "probability": np_, "impact": ni, "updated_at": db.now()}
                        if ns == "Resolved":
                            data["resolved_at"] = db.now()
                        db.t_update("risks", cid, int(x["id"]), data)
                        audit.log(cid, user["email"], "risk_updated", "risk", x["code"],
                                  f"status {x['status']}->{ns}; evidence {x['evidence_status']}->{ne}; P{x['probability']}->{np_} I{x['impact']}->{ni}; {note}")
                        st.session_state["risk_sel"] = code
                        st.success(t("Risk updated."))
                        st.rerun()
                with e2.form("risk_action"):
                    st.markdown("**" + t("Add remediation action") + "**")
                    a = st.text_input(t("Action"))
                    ao = st.text_input(t("Action owner"))
                    ad = st.date_input(t("Due date"))
                    if st.form_submit_button(t("Add action")) and a.strip():
                        db.t_insert("risk_actions", cid, {"risk_id": int(x["id"]), "action": a, "owner": ao, "due_date": str(ad),
                                                          "status": "Open", "note": "", "user": user["email"], "ts": db.now()})
                        if x["status"] == "Open":
                            db.t_update("risks", cid, int(x["id"]), {"status": "In remediation", "updated_at": db.now()})
                        audit.log(cid, user["email"], "risk_action_added", "risk", x["code"], a)
                        st.session_state["risk_sel"] = code
                        st.rerun()
                if not acts.empty:
                    open_acts = acts[acts["status"] != "Done"]
                    if not open_acts.empty:
                        aid = st.selectbox(t("Mark action as done"), open_acts["id"].tolist(),
                                           format_func=lambda i: open_acts.set_index("id").loc[i, "action"])
                        if st.button(t("Mark done")):
                            db.t_update("risk_actions", cid, int(aid), {"status": "Done", "note": f"Done by {user['email']} {db.now()}"})
                            audit.log(cid, user["email"], "risk_action_done", "risk", x["code"], str(aid))
                            st.rerun()

    with tab_new:
        if not edit:
            st.info(t("Read-only for your role."))
        else:
            projects = db.t_rows("projects", cid, "archived = 0")
            with st.form("new_risk"):
                c1, c2 = st.columns(2)
                title = c1.text_input(t("Risk title") + " *")
                title_fr = c2.text_input(t("Title in French (optional)"))
                cat = c1.text_input(t("Category"), value="Cybersecurity")
                ccat = c2.selectbox(t("Case category"), engine_risk.CASE_CATEGORIES, format_func=tf)
                p = c1.slider(t("Probability"), 1, 5, 3)
                i = c2.slider(t("Impact"), 1, 5, 3)
                st.caption(t("Score preview updates after saving: P × I with bands Low 1–7, Medium 8–14, High 15–19, Critical 20–25."))
                cause = st.text_area(t("Cause / vulnerability"))
                event = st.text_area(t("Risk event"))
                cons = st.text_area(t("Potential consequences"))
                evn = st.text_input(t("Evidence to collect"))
                rec = st.text_input(t("Recommended action / controls"))
                owner = c1.text_input(t("Owner"))
                ev = c2.selectbox(t("Evidence status"), engine_risk.EVIDENCE_STATUSES, index=1, format_func=tf)
                proj = st.selectbox(t("Project (optional)"), [None] + [x["id"] for x in projects],
                                    format_func=lambda v: "—" if v is None else next(f"{x['code']} · {x['name']}" for x in projects if x["id"] == v))
                if st.form_submit_button(t("Create risk"), type="primary"):
                    if not title.strip():
                        st.error(t("Title is required."))
                    else:
                        n = (db.scalar("SELECT COUNT(*) FROM risks WHERE company_id=? AND source='Manual'", (cid,)) or 0) + 1
                        db.t_insert("risks", cid, {
                            "code": f"M-{n:03d}", "title": title, "title_fr": title_fr, "category": cat, "case_category": ccat,
                            "probability": p, "impact": i, "status": "Open", "evidence_status": ev, "source": "Manual",
                            "project_id": proj, "owner": owner, "cause": cause, "event": event, "consequences": cons,
                            "evidence_needed": evn, "recommended_action": rec,
                            "explanation": f"Recorded manually by {user['name']}. Because of: {cause} Risk event: {event} Consequence: {cons}",
                            "created_at": db.now(), "updated_at": db.now()})
                        audit.log(cid, user["email"], "risk_created", "risk", f"M-{n:03d}", title)
                        st.success(t("Risk {c} created with score {s} ({p}).", c=f"M-{n:03d}", s=p * i, p=tf(engine_risk.priority(p * i, cid))))
    _ = pd
