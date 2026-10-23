"""Derived metrics shared by the dashboard, project pages and reports."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import db, engine_alloc, engine_risk

OPEN_TASK = engine_alloc.OPEN_TASK


def projects_health(cid: int) -> pd.DataFrame:
    """Health rules (documented):
    Critical  = an open Critical risk on the project, OR actual spend > budget, OR end date passed with progress < 100%.
    At risk   = an open High risk, OR overdue tasks/milestones, OR spend >= warning threshold, OR an over-allocated team member,
                OR status 'On Hold'.
    On track  = none of the above. Completed tasks alone never make a project healthy if serious risks remain open."""
    today = date.today()
    s = db.settings(cid)
    p = db.df("""SELECT p.*, c.name AS client, e.name AS manager, l.name AS location FROM projects p
                 LEFT JOIN clients c ON c.id = p.client_id LEFT JOIN employees e ON e.id = p.manager_id
                 LEFT JOIN locations l ON l.id = p.location_id WHERE p.company_id = ? AND p.archived = 0""", (cid,))
    if p.empty:
        return p
    prog = engine_alloc.project_progress(cid)
    p = p.merge(prog, left_on="id", right_on="project_id", how="left").drop(columns=["project_id"], errors="ignore")
    p["progress"] = p["progress"].fillna(0).round(0)
    tasks = db.t_df("tasks", cid)
    ms = db.t_df("milestones", cid)
    risks = engine_risk.register(cid)
    wl = engine_alloc.workload(cid)
    over_emps = set(wl[wl["band"] == "Overcapacity"]["employee_id"]) if not wl.empty else set()
    alloc = engine_alloc.active_allocations(cid)
    rows = []
    for _, r in p.iterrows():
        pt = tasks[tasks["project_id"] == r["id"]] if not tasks.empty else tasks
        open_t = pt[pt["status"].isin(OPEN_TASK)] if not pt.empty else pt
        od = int((pd.to_datetime(open_t["due_date"]).dt.date < today).sum()) if not open_t.empty else 0
        pm = ms[(ms["project_id"] == r["id"]) & (ms["status"] != "Completed")] if not ms.empty else ms
        od_ms = int((pd.to_datetime(pm["due_date"]).dt.date < today).sum()) if not pm.empty else 0
        pr = risks[(risks["project_id"] == r["id"]) & (risks["status"].isin(engine_risk.OPEN_STATUSES))] if not risks.empty else risks
        crit = int((pr["priority"] == "Critical").sum()) if not pr.empty else 0
        high = int((pr["priority"] == "High").sum()) if not pr.empty else 0
        bu = (r["actual_spend"] / r["budget"] * 100) if r["budget"] else 0
        team = set(alloc[alloc["project_id"] == r["id"]]["employee_id"]) if not alloc.empty else set()
        over_team = len(team & over_emps)
        end = date.fromisoformat(r["end_date"]) if r["end_date"] else None
        reasons = []
        if r["status"] in ("Completed", "Cancelled"):
            health = "Completed" if r["status"] == "Completed" else "Cancelled"
        else:
            if crit:
                reasons.append(f"{crit} critical risk(s)")
            if r["budget"] and bu > 100:
                reasons.append(f"budget {bu:.0f}%")
            if end and end < today and r["progress"] < 100:
                reasons.append("end date passed")
            critical = bool(reasons)
            if high:
                reasons.append(f"{high} high risk(s)")
            if od:
                reasons.append(f"{od} overdue task(s)")
            if od_ms:
                reasons.append(f"{od_ms} overdue milestone(s)")
            if r["budget"] and s["budget_warning_pct"] <= bu <= 100:
                reasons.append(f"budget {bu:.0f}%")
            if over_team:
                reasons.append(f"{over_team} over-allocated member(s)")
            if r["status"] == "On Hold":
                reasons.append("on hold")
            health = "Critical" if critical else ("At risk" if reasons else "On track")
        rows.append({"id": r["id"], "overdue_tasks": od, "overdue_milestones": od_ms, "open_critical": crit,
                     "open_high": high, "budget_util": round(bu, 1), "team_size": len(team), "over_team": over_team,
                     "health": health, "health_reasons": "; ".join(reasons)})
    return p.merge(pd.DataFrame(rows), on="id")


def subcontractor_tasks_at_risk(cid: int) -> pd.DataFrame:
    today = date.today()
    t = db.df("""SELECT t.*, s.name AS subcontractor, p.code AS project_code FROM tasks t
                 JOIN subcontractors s ON s.id = t.subcontractor_id JOIN projects p ON p.id = t.project_id
                 WHERE t.company_id = ? AND t.status IN ('Not Started','In Progress','Blocked','Under Review')""", (cid,))
    if t.empty:
        return t
    t["due"] = pd.to_datetime(t["due_date"]).dt.date
    mask = (t["due"] < today) | ((t["due"] <= today + timedelta(days=7)) & (t["completion"] < 50)) | (t["status"] == "Blocked")
    return t[mask]


def training_rate(cid: int, employee_ids: set | None = None) -> float:
    ta = db.t_df("training_assignments", cid)
    if employee_ids is not None and not ta.empty:
        ta = ta[ta["employee_id"].isin(employee_ids)]
    if ta.empty:
        return 0.0
    return round((ta["status"] == "Completed").mean() * 100, 1)
