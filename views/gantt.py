"""Interactive Gantt chart built from saved tasks and milestones, with a date-edit form."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from hub import audit, db, engine_risk, ui
from hub.i18n import t, tf

STATUSES = ["Not Started", "In Progress", "Blocked", "Under Review", "Completed", "Cancelled"]


def load(cid: int) -> pd.DataFrame:
    return db.df("""SELECT t.*, p.code AS project_code, p.name AS project_name, p.location_id, l.name AS location,
                    e.name AS assignee, s.name AS subcontractor FROM tasks t JOIN projects p ON p.id = t.project_id
                    LEFT JOIN locations l ON l.id = p.location_id LEFT JOIN employees e ON e.id = t.assignee_id
                    LEFT JOIN subcontractors s ON s.id = t.subcontractor_id
                    WHERE t.company_id = ? AND p.archived = 0 ORDER BY p.code, t.start_date""", (cid,))


def render(ctx: dict) -> None:
    cid, edit, user = ctx["cid"], ctx["can_edit"], ctx["user"]
    ui.page_header("gantt", t("Gantt chart"), t("Projects, tasks, milestones, dependencies and progress from saved data"))
    df = load(cid)
    if df.empty:
        st.info(t("No tasks yet."))
        return
    today = date.today()
    f = st.columns(4)
    projs = sorted(df["project_code"].unique())
    default_p = [p for p in ("P02",) if p in projs] or projs[:1]
    if ctx["role"] == "Employee" and user.get("employee_id"):
        mine = df[df["assignee_id"] == user["employee_id"]]["project_code"].unique().tolist()
        default_p = mine or default_p
    sel_p = f[0].multiselect(t("Project"), projs, default=default_p,
                             format_func=lambda c: f"{c} · {df[df['project_code'] == c]['project_name'].iloc[0]}")
    emps = sorted(df["assignee"].dropna().unique())
    sel_e = f[1].multiselect(t("Employee"), emps, placeholder=t("All"))
    sel_l = f[2].multiselect(t("Location"), sorted(df["location"].dropna().unique()), placeholder=t("All"))
    sel_s = f[3].multiselect(t("Status"), STATUSES, placeholder=t("All"), format_func=tf)
    d = df.copy()
    if sel_p:
        d = d[d["project_code"].isin(sel_p)]
    if sel_e:
        d = d[d["assignee"].isin(sel_e)]
    if sel_l:
        d = d[d["location"].isin(sel_l)]
    if sel_s:
        d = d[d["status"].isin(sel_s)]
    show_dep = st.toggle(t("Show dependency arrows"), value=len(sel_p) <= 2)
    if d.empty:
        st.info(t("No tasks match the filters."))
    else:
        d["start"] = pd.to_datetime(d["start_date"])
        d["end"] = pd.to_datetime(d["due_date"]) + pd.Timedelta(days=1)
        d["dur_ms"] = (d["end"] - d["start"]).dt.total_seconds() * 1000
        d["overdue"] = (pd.to_datetime(d["due_date"]).dt.date < today) & d["status"].isin(["Not Started", "In Progress", "Blocked", "Under Review"])
        d["label"] = d["project_code"] + " · " + d["title"].str.slice(0, 34)
        d["who"] = d["assignee"].fillna("") + d["subcontractor"].fillna("").apply(lambda s: f" / {s}" if s else "")
        rows = []
        for pc in d["project_code"].unique():
            rows.append(f"{pc} · ◆ {t('Milestones')}")
            rows += d[d["project_code"] == pc].sort_values("start")["label"].tolist()
        fig = go.Figure()
        for stt in STATUSES:
            g = d[d["status"] == stt]
            if g.empty:
                continue
            fig.add_bar(
                y=g["label"], x=g["dur_ms"], base=g["start"].dt.strftime("%Y-%m-%d"), orientation="h", name=tf(stt),
                marker=dict(color=ui.STATUS_COLORS.get(stt, "#999"), opacity=0.45,
                            line=dict(color=["#b3261e" if o else ("#1b2a3d" if c else "rgba(0,0,0,0)") for o, c in zip(g["overdue"], g["is_critical"])],
                                      width=[3 if o else (2 if c else 0) for o, c in zip(g["overdue"], g["is_critical"])])),
                customdata=g[["code", "who", "completion", "start_date", "due_date", "is_critical", "overdue"]].values,
                hovertemplate="<b>%{customdata[0]}</b> %{y}<br>%{customdata[3]} → %{customdata[4]}<br>" + t("Assigned") +
                              ": %{customdata[1]}<br>" + t("Progress") + ": %{customdata[2]}%<br>" + t("Critical") +
                              ": %{customdata[5]} · " + t("Overdue") + ": %{customdata[6]}<extra></extra>")
            fig.add_bar(y=g["label"], x=g["dur_ms"] * g["completion"] / 100, base=g["start"].dt.strftime("%Y-%m-%d"), orientation="h",
                        marker=dict(color=ui.STATUS_COLORS.get(stt, "#999")), showlegend=False, hoverinfo="skip",
                        width=0.35)
        ms = db.df("""SELECT m.*, p.code FROM milestones m JOIN projects p ON p.id = m.project_id WHERE m.company_id = ?""", (cid,))
        ms = ms[ms["code"].isin(d["project_code"].unique())]
        if not ms.empty:
            ms["row"] = ms["code"] + f" · ◆ {t('Milestones')}"
            ms["late"] = (pd.to_datetime(ms["due_date"]).dt.date < today) & (ms["status"] != "Completed")
            fig.add_scatter(x=ms["due_date"], y=ms["row"], mode="markers+text", name=t("Milestone"),
                            text=ms["name"], textposition="top center", textfont=dict(size=10),
                            marker=dict(symbol="diamond", size=13,
                                        color=["#b3261e" if late else ("#3a9a68" if s == "Completed" else ui.NAVY) for late, s in zip(ms["late"], ms["status"])]),
                            hovertemplate="%{text}<br>%{x}<extra></extra>")
        if show_dep:
            by_id = d.set_index("id")
            for _, r in d.iterrows():
                for dep in str(r["depends_on"] or "").split(","):
                    dep = dep.strip()
                    if dep.isdigit() and int(dep) in by_id.index:
                        pr = by_id.loc[int(dep)]
                        fig.add_annotation(x=r["start_date"], y=r["label"], ax=pr["due_date"], ay=pr["label"], xref="x", yref="y",
                                           axref="x", ayref="y", showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1,
                                           arrowcolor="#8a94a6", opacity=0.8)
        fig.add_vline(x=today.isoformat(), line_color="#b3261e", line_dash="dot", line_width=1.5)
        fig.add_annotation(x=today.isoformat(), y=0, yref="paper", yanchor="bottom", xanchor="left", text=" " + t("Today"), showarrow=False, font=dict(color="#b3261e", size=11), bgcolor="rgba(255,255,255,0.8)")
        fig.update_layout(barmode="overlay", xaxis=dict(type="date"),
                          yaxis=dict(categoryorder="array", categoryarray=list(reversed(rows)), automargin=True),
                          title=t("Timeline · bars = tasks (dark part = progress) · red outline = overdue · dark outline = critical"))
        st.plotly_chart(ui.style_fig(fig, height=max(360, 26 * len(rows) + 140)), key="gantt")
        c = st.columns(4)
        c[0].metric(t("Tasks shown"), len(d))
        c[1].metric(t("Overdue"), int(d["overdue"].sum()))
        c[2].metric(t("Critical tasks"), int(d["is_critical"].sum()))
        c[3].metric(t("Blocked"), int((d["status"] == "Blocked").sum()))

    st.subheader("✏️ " + t("Edit task dates"))
    st.caption(t("Drag-and-drop is not supported by the charting library used here, so dates are edited with this form. Every change is logged with reason, user and time."))
    if not edit:
        st.info(t("Read-only for your role."))
        return
    src = d if not d.empty else df
    code = st.selectbox(t("Task"), src["code"].tolist(), format_func=lambda c: f"{c} · {src.set_index('code').loc[c, 'title']}")
    row = src[src["code"] == code].iloc[0]
    st.caption(t("Current: {s} → {d} · assigned to {a} · status {st}", s=row["start_date"], d=row["due_date"],
                 a=row["assignee"] or row["subcontractor"] or "-", st=tf(row["status"])))
    with st.form("gantt_edit"):
        c1, c2 = st.columns(2)
        ns = c1.date_input(t("Start date"), datetime.fromisoformat(row["start_date"]).date(), key=f"gs_{code}")
        nd = c2.date_input(t("Due date"), datetime.fromisoformat(row["due_date"]).date(), key=f"gd_{code}")
        reason = st.text_input(t("Reason for the change") + " *")
        if st.form_submit_button(t("Save dates"), type="primary"):
            task = db.one("SELECT * FROM tasks WHERE company_id = ? AND code = ?", (cid, code))
            if nd < ns:
                st.error(t("Due date cannot be before start date."))
            elif not reason.strip():
                st.error(t("A reason is required for any date change."))
            elif str(ns) == task["start_date"] and str(nd) == task["due_date"]:
                st.info(t("No change."))
            else:
                for field, new in (("start_date", str(ns)), ("due_date", str(nd))):
                    if task[field] != new:
                        db.t_insert("task_history", cid, {"task_id": task["id"], "field": field, "old_value": task[field], "new_value": new,
                                                          "reason": reason, "user": user["email"], "ts": db.now()})
                db.t_update("tasks", cid, task["id"], {"start_date": str(ns), "due_date": str(nd)})
                audit.log(cid, user["email"], "task_dates_changed", "task", code, f"{task['start_date']}→{ns}, {task['due_date']}→{nd}: {reason}")
                res = engine_risk.run(cid)
                st.success(t("Saved. Gantt and risk indicators recalculated ({c} new, {u} updated, {x} cleared).",
                             c=res["created"], u=res["updated"], x=res["cleared"]))
                st.rerun()
    _ = timedelta
