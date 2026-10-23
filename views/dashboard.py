"""Executive dashboard - every number is computed from stored data on each load."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from hub import db, engine_alloc, engine_risk, metrics, ui
from hub.i18n import lang, t, tf


def render(ctx: dict) -> None:
    cid = ctx["cid"]
    cur = ctx["company"]["currency"] or "EUR"
    today = date.today()
    s = db.settings(cid)
    ui.page_header("dashboard", t("Executive dashboard"), t("Live view of projects, people, budget and risks"))

    locs = db.t_df("locations", cid)
    projs = metrics.projects_health(cid)
    with st.container(border=True):
        f1, f2, f3, f4 = st.columns([1.2, 1.6, 1.2, 1.6])
        sel_loc = f1.multiselect(t("Location"), locs["name"].tolist() if not locs.empty else [], placeholder=t("All"))
        p_opts = projs["code"].tolist() if not projs.empty else []
        sel_proj = f2.multiselect(t("Project"), p_opts, placeholder=t("All"),
                                  format_func=lambda c: f"{c} · {projs.set_index('code').loc[c, 'name']}")
        sel_pri = f3.multiselect(t("Risk priority"), ["Critical", "High", "Medium", "Low"], placeholder=t("All"), format_func=tf)
        rng = f4.date_input(t("Task due-date range"), (today - timedelta(days=60), today + timedelta(days=60)))
    d0, d1 = (rng if isinstance(rng, (list, tuple)) and len(rng) == 2 else (today - timedelta(days=60), today + timedelta(days=60)))

    # ---- apply filters ------------------------------------------------------
    wl = engine_alloc.workload(cid)
    if sel_loc and not wl.empty:
        wl = wl[wl["location"].isin(sel_loc)]
    p = projs.copy()
    if sel_loc and not p.empty:
        p = p[p["location"].isin(sel_loc)]
    if sel_proj and not p.empty:
        p = p[p["code"].isin(sel_proj)]
    pids = set(p["id"]) if not p.empty else set()
    tasks = db.df("""SELECT t.*, p.code AS project_code, e.name AS assignee FROM tasks t JOIN projects p ON p.id = t.project_id
                     LEFT JOIN employees e ON e.id = t.assignee_id WHERE t.company_id = ?""", (cid,))
    tasks = tasks[tasks["project_id"].isin(pids)] if not tasks.empty else tasks
    tasks["due"] = pd.to_datetime(tasks["due_date"]).dt.date
    tasks_rng = tasks[(tasks["due"] >= d0) & (tasks["due"] <= d1)]
    open_mask = tasks["status"].isin(engine_alloc.OPEN_TASK)
    risks = engine_risk.register(cid, lang())
    open_r = risks[risks["status"].isin(engine_risk.OPEN_STATUSES)] if not risks.empty else risks
    if (sel_proj or sel_loc) and not open_r.empty:
        open_r = open_r[open_r["project_id"].isin(pids) | open_r["project_id"].isna()]
    if sel_pri and not open_r.empty:
        open_r = open_r[open_r["priority"].isin(sel_pri)]
    emp_ids = set(wl["employee_id"]) if not wl.empty else set()

    # ---- KPIs ---------------------------------------------------------------
    active_p = p[p["status"].isin(["Active", "On Hold"])] if not p.empty else p
    budget = active_p["budget"].sum() if not active_p.empty else 0
    actual = active_p["actual_spend"].sum() if not active_p.empty else 0
    bu = actual / budget * 100 if budget else 0
    window = s.get("deadline_window_days", 14)
    overdue = int((open_mask & (tasks["due"] < today)).sum())
    upcoming = int((open_mask & (tasks["due"] >= today) & (tasks["due"] <= today + timedelta(days=window))).sum())
    over = int((wl["band"] == "Overcapacity").sum()) if not wl.empty else 0
    unavailable = int(wl["absent_now"].sum()) if not wl.empty else 0
    crit = int((open_r["priority"] == "Critical").sum()) if not open_r.empty else 0
    high = int((open_r["priority"] == "High").sum()) if not open_r.empty else 0
    at_risk = int(active_p["health"].isin(["At risk", "Critical"]).sum()) if not active_p.empty else 0
    tr = metrics.training_rate(cid, emp_ids)
    ev = db.t_df("compliance_evidence", cid)
    open_comp = (int((ev["status"] != "Verified").sum()) if not ev.empty else 0) + \
        int(db.scalar("SELECT COUNT(*) FROM risk_actions WHERE company_id=? AND status != 'Done'", (cid,)) or 0)
    sub_risk = metrics.subcontractor_tasks_at_risk(cid)
    sub_risk = sub_risk[sub_risk["project_id"].isin(pids)] if not sub_risk.empty else sub_risk
    done_rng = int((tasks_rng["status"] == "Completed").sum())
    inprog_rng = int((tasks_rng["status"] == "In Progress").sum())

    ui.kpi_row([
        (t("Total employees"), len(wl), t("active, in filter"), "neutral"),
        (t("Active projects"), int((p["status"] == "Active").sum()) if not p.empty else 0, t("{n} on hold", n=int((p["status"] == "On Hold").sum()) if not p.empty else 0), "neutral"),
        (t("Completed projects"), int((p["status"] == "Completed").sum()) if not p.empty else 0, "", "good"),
        (t("Tasks completed"), done_rng, t("due in selected range"), "good"),
        (t("Tasks in progress"), inprog_rng, t("due in selected range"), "neutral"),
        (t("Overdue tasks"), overdue, t("open and past due"), "bad" if overdue else "good"),
        (t("Upcoming deadlines"), upcoming, t("next {n} days", n=window), "warn" if upcoming else "neutral"),
        (t("Employees at overcapacity"), over, t("allocated above capacity"), "bad" if over else "good"),
        (t("Employees currently unavailable"), unavailable, t("absence recorded today"), "warn" if unavailable else "neutral"),
        (t("Critical risks"), crit, t("open"), "bad" if crit else "good"),
        (t("High risks"), high, t("open"), "warn" if high else "good"),
        (t("Budget utilisation"), f"{bu:.0f}%", f"{ui.money(actual, cur)} / {ui.money(budget, cur)}", "bad" if bu > 100 else "warn" if bu >= s['budget_warning_pct'] else "neutral"),
        (t("Projects at risk"), at_risk, t("health: at risk or critical"), "warn" if at_risk else "good"),
        (t("Training completion rate"), f"{tr:.0f}%", t("all assignments"), "good" if tr >= 85 else "warn"),
        (t("Open compliance actions"), open_comp, t("evidence + remediation actions"), "warn" if open_comp else "good"),
        (t("Subcontractor tasks at risk"), len(sub_risk), t("overdue / due soon"), "bad" if len(sub_risk) else "good"),
    ])

    # ---- charts ---------------------------------------------------------------
    c1, c2 = st.columns(2)
    with c1:
        if not p.empty:
            sc = p.groupby("health").size().reset_index(name="n")
            sc["label"] = sc["health"].map(tf)
            colors = {"On track": "#3a9a68", "At risk": "#e06c1f", "Critical": "#b3261e", "Completed": "#7fa7d9", "Cancelled": "#8a94a6"}
            fig = px.pie(sc, names="label", values="n", hole=0.55, color="health", color_discrete_map=colors,
                         title=t("Project status distribution (health)"))
            fig.update_traces(textinfo="value+label", textposition="outside")
            st.plotly_chart(ui.style_fig(fig, legend=False), key="d_status")
    with c2:
        if not tasks.empty:
            g = tasks[tasks["status"] != "Cancelled"].groupby("project_code").agg(
                total=("id", "count"), done=("status", lambda x: (x == "Completed").sum())).reset_index()
            g["pct"] = (g["done"] / g["total"] * 100).round(0)
            fig = px.bar(g, x="project_code", y="pct", text="pct", title=t("Task completion % by project"),
                         labels={"project_code": "", "pct": "%"})
            fig.update_traces(marker_color=ui.ACCENT, texttemplate="%{text:.0f}%")
            fig.update_yaxes(range=[0, 105])
            st.plotly_chart(ui.style_fig(fig, legend=False), key="d_taskpct")

    c3, c4 = st.columns(2)
    with c3:
        if not wl.empty:
            order = ["Underutilised", "Healthy", "High", "Overcapacity"]
            b = wl.groupby("band").size().reindex(order, fill_value=0).reset_index(name="n")
            b["label"] = b["band"].map(tf)
            fig = px.bar(b, x="label", y="n", color="band", color_discrete_map=ui.BAND_COLORS, text="n",
                         title=t("Employee workload distribution"), labels={"label": "", "n": t("Employees")})
            st.plotly_chart(ui.style_fig(fig, legend=False), key="d_wl")
    with c4:
        if not wl.empty:
            g = wl.groupby("location").agg(avg=("utilisation", "mean"), over=("band", lambda x: (x == "Overcapacity").sum()),
                                           n=("employee_id", "count")).reset_index()
            fig = go.Figure()
            fig.add_bar(x=g["location"], y=g["avg"].round(0), name=t("Average workload %"), marker_color=ui.ACCENT,
                        text=g["avg"].round(0), texttemplate="%{text:.0f}%")
            fig.add_scatter(x=g["location"], y=g["over"], name=t("Employees over capacity"), mode="markers+text",
                            text=g["over"], textposition="top center", marker=dict(size=14, color="#b3261e"), yaxis="y2")
            fig.update_layout(title=t("Workload by location"), yaxis=dict(title="%"),
                              yaxis2=dict(overlaying="y", side="right", showgrid=False, title=t("Over capacity")))
            st.plotly_chart(ui.style_fig(fig), key="d_loc")

    c5, c6 = st.columns(2)
    with c5:
        bp = p[p["budget"] > 0] if not p.empty else p
        if not bp.empty:
            fig = go.Figure()
            fig.add_bar(x=bp["code"], y=bp["budget"], name=t("Approved budget"), marker_color="#c9d6e8")
            fig.add_bar(x=bp["code"], y=bp["planned_spend"], name=t("Planned to date"), marker_color="#7fa7d9")
            fig.add_bar(x=bp["code"], y=bp["actual_spend"], name=t("Actual"), marker_color=ui.NAVY)
            fig.update_layout(barmode="group", title=t("Budget vs actual expenditure") + f" ({cur}, " + t("sample estimates") + ")")
            st.plotly_chart(ui.style_fig(fig), key="d_budget")
    with c6:
        if not p.empty:
            pp = p.sort_values("progress")
            colors = {"On track": "#3a9a68", "At risk": "#e06c1f", "Critical": "#b3261e", "Completed": "#7fa7d9", "Cancelled": "#8a94a6"}
            fig = px.bar(pp, y="code", x="progress", orientation="h", color="health", color_discrete_map=colors, text="progress",
                         title=t("Project progress (weighted by estimated hours)"), labels={"code": "", "progress": "%"},
                         hover_data={"name": True, "health_reasons": True})
            fig.for_each_trace(lambda tr_: tr_.update(name=tf(tr_.name)))
            fig.update_traces(texttemplate="%{text:.0f}%")
            fig.update_xaxes(range=[0, 105])
            st.plotly_chart(ui.style_fig(fig), key="d_prog")

    c7, c8 = st.columns(2)
    with c7:
        if not open_r.empty:
            order = ["Critical", "High", "Medium", "Low"]
            r = open_r.groupby("priority").size().reindex(order, fill_value=0).reset_index(name="n")
            r["label"] = r["priority"].map(tf)
            fig = px.bar(r, x="label", y="n", color="priority", color_discrete_map=ui.PRIORITY_COLORS, text="n",
                         title=t("Open risks by severity"), labels={"label": "", "n": t("Risks")})
            st.plotly_chart(ui.style_fig(fig, legend=False), key="d_risk")
    with c8:
        ta = db.df("""SELECT tr.name, ta.status, ta.employee_id FROM training_assignments ta JOIN trainings tr ON tr.id = ta.training_id
                      WHERE ta.company_id = ?""", (cid,))
        if not ta.empty:
            ta = ta[ta["employee_id"].isin(emp_ids)]
            g = ta.groupby("name").agg(rate=("status", lambda x: (x == "Completed").mean() * 100)).reset_index().sort_values("rate")
            fig = px.bar(g, y="name", x="rate", orientation="h", text="rate", title=t("Training completion by course"),
                         labels={"name": "", "rate": "%"})
            fig.update_traces(marker_color=ui.ACCENT, texttemplate="%{text:.0f}%")
            fig.update_xaxes(range=[0, 105])
            st.plotly_chart(ui.style_fig(fig, legend=False), key="d_train")

    c9, c10 = st.columns(2)
    with c9:
        up = tasks[open_mask & (tasks["due"] >= today) & (tasks["due"] <= today + timedelta(days=56))].copy()
        if not up.empty:
            up["week"] = pd.to_datetime(up["due"]).dt.to_period("W").apply(lambda x: x.start_time.date())
            g = up.groupby(["week", "priority"]).size().reset_index(name="n")
            g["prio"] = g["priority"].map(tf)
            fig = px.bar(g, x="week", y="n", color="priority", color_discrete_map=ui.PRIORITY_COLORS,
                         title=t("Upcoming deadlines (next 8 weeks, open tasks)"), labels={"week": t("Week of"), "n": t("Tasks")})
            fig.for_each_trace(lambda tr_: tr_.update(name=tf(tr_.name)))
            st.plotly_chart(ui.style_fig(fig), key="d_deadlines")
        else:
            st.info(t("No upcoming deadlines in the next 8 weeks."))
    with c10:
        tr_df = engine_risk.trend(cid)
        if not tr_df.empty:
            if sel_pri:
                tr_df = tr_df[tr_df["priority"].isin(sel_pri)]
            tr_df["prio"] = tr_df["priority"].map(tf)
            fig = px.line(tr_df, x="week", y="count", color="priority", color_discrete_map=ui.PRIORITY_COLORS, markers=True,
                          title=t("Open risks over time (from risk created / resolved dates)"), labels={"week": "", "count": t("Open risks")})
            fig.for_each_trace(lambda tr_: tr_.update(name=tf(tr_.name)))
            st.plotly_chart(ui.style_fig(fig), key="d_trend")

    # ---- attention list -------------------------------------------------------
    st.subheader("⚠️ " + t("Needs attention"))
    a1, a2 = st.columns(2)
    with a1:
        st.markdown("**" + t("Top open risks") + "**")
        if not open_r.empty:
            ui.table(open_r.head(8), {"code": "Code", "display_title": "Risk", "score": "Score", "priority": "Priority", "owner": "Owner"},
                     translate_values=("priority",))
    with a2:
        st.markdown("**" + t("Projects not on track") + "**")
        nt = p[p["health"].isin(["At risk", "Critical"])] if not p.empty else p
        ui.table(nt, {"code": "Code", "name": "Project", "health": "Health", "health_reasons": "Why"}, translate_values=("health",))
