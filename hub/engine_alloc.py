"""Central multi-project resource allocation engine.

Rules (documented so the numbers are explainable in a presentation):

* An employee's capacity is counted ONCE (their configurable weekly capacity), never
  per project.
* Allocated hours = sum of weekly hours allocated to that employee across ALL active
  (non-archived, non-completed) projects.
* Effective capacity for the reference week = weekly capacity minus recorded absence
  in that week (absent working days x capacity / 5).
* Workload % = allocated / effective capacity.  Over-allocation = allocated - effective capacity.
* Bands (configurable in Settings): < under -> Underutilised, <= high -> Healthy,
  <= over -> High, > over -> Overcapacity.
* Estimated delay exposure (working days per week) = over-allocated hours / (capacity / 5).
  For an individual task it is pro-rated by the task's share of the employee's open work.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import db

OPEN_TASK = ("Not Started", "In Progress", "Blocked", "Under Review")


def _d(x) -> date | None:
    if not x:
        return None
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def week_bounds(ref: date) -> tuple[date, date]:
    start = ref - timedelta(days=ref.weekday())
    return start, start + timedelta(days=4)


def working_days_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    s, e = max(a_start, b_start), min(a_end, b_end)
    if s > e:
        return 0
    n, d = 0, s
    while d <= e:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def band(util: float, th: dict) -> str:
    if util > th["over"]:
        return "Overcapacity"
    if util > th["high"]:
        return "High"
    if util >= th["under"]:
        return "Healthy"
    return "Underutilised"


BAND_COLORS = {"Underutilised": "#7aa7d6", "Healthy": "#3aa76d", "High": "#e0a526", "Overcapacity": "#d64545"}


def active_allocations(cid: int) -> pd.DataFrame:
    return db.df(
        """SELECT a.*, p.name AS project, p.code AS project_code, p.priority AS project_priority
           FROM allocations a JOIN projects p ON p.id = a.project_id AND p.company_id = a.company_id
           WHERE a.company_id = ? AND p.archived = 0 AND p.status NOT IN ('Completed','Cancelled')""",
        (cid,),
    )


def workload(cid: int, ref: date | None = None) -> pd.DataFrame:
    ref = ref or date.today()
    s = db.settings(cid)
    th = s["thresholds"]
    window = s.get("deadline_window_days", 14)
    wk_s, wk_e = week_bounds(ref)
    emps = db.df(
        """SELECT e.*, l.name AS location FROM employees e LEFT JOIN locations l ON l.id = e.location_id
           WHERE e.company_id = ? AND e.active = 1""", (cid,))
    if emps.empty:
        return emps
    alloc = active_allocations(cid)
    absences = db.t_rows("absences", cid)
    tasks = db.df("SELECT * FROM tasks WHERE company_id = ? AND assignee_id IS NOT NULL", (cid,))
    rows = []
    for _, e in emps.iterrows():
        cap = float(e["weekly_capacity"] or 0)
        absent_days = 0
        absent_now = False
        for a in absences:
            if a["employee_id"] != e["id"]:
                continue
            a_s, a_e = _d(a["start_date"]), _d(a["end_date"]) or _d(a["start_date"])
            if not a_s:
                continue
            absent_days += working_days_overlap(a_s, a_e, wk_s, wk_e)
            if a_s <= ref <= a_e:
                absent_now = True
        absent_days = min(absent_days, 5)
        eff = max(cap - cap / 5 * absent_days, 0)
        ea = alloc[alloc["employee_id"] == e["id"]] if not alloc.empty else alloc
        allocated = float(ea["hours_per_week"].sum()) if not ea.empty else 0.0
        util = (allocated / eff * 100) if eff > 0 else (999.0 if allocated > 0 else 0.0)
        et = tasks[(tasks["assignee_id"] == e["id"]) & (tasks["status"].isin(OPEN_TASK))] if not tasks.empty else tasks
        due = pd.to_datetime(et["due_date"], errors="coerce").dt.date if not et.empty else pd.Series(dtype=object)
        overdue = int((due < ref).sum()) if not et.empty else 0
        upcoming = int(((due >= ref) & (due <= ref + timedelta(days=window))).sum()) if not et.empty else 0
        over = max(allocated - eff, 0)
        rows.append({
            "employee_id": int(e["id"]), "emp_code": e["emp_code"], "name": e["name"],
            "location": e["location"], "department": e["department"], "job_role": e["job_role"],
            "skills": e["skills"], "capacity": cap, "absent_days_this_week": absent_days,
            "absent_now": absent_now, "effective_capacity": round(eff, 1),
            "allocated": round(allocated, 1), "remaining": round(eff - allocated, 1),
            "utilisation": round(util, 1), "over_hours": round(over, 1),
            "band": band(util, th), "projects": int(ea["project_id"].nunique()) if not ea.empty else 0,
            "project_list": ", ".join(ea["project_code"].tolist()) if not ea.empty else "",
            "open_tasks": len(et), "overdue_tasks": overdue, "upcoming_deadlines": upcoming,
            "deadline_conflict": bool(over > 0 and upcoming > 0),
            "delay_exposure_days_per_week": round(over / (cap / 5), 2) if cap else 0.0,
            "remote_eligible": int(e["remote_eligible"] or 0),
        })
    return pd.DataFrame(rows)


def matrix(cid: int) -> pd.DataFrame:
    alloc = active_allocations(cid)
    if alloc.empty:
        return pd.DataFrame()
    emps = db.df("SELECT id, name FROM employees WHERE company_id = ? AND active = 1", (cid,))
    m = alloc.pivot_table(index="employee_id", columns="project_code", values="hours_per_week", aggfunc="sum", fill_value=0)
    m.index = m.index.map(dict(zip(emps["id"], emps["name"])))
    return m


def overcapacity_detail(cid: int, employee_id: int, ref: date | None = None) -> dict:
    ref = ref or date.today()
    wl = workload(cid, ref)
    row = wl[wl["employee_id"] == employee_id]
    if row.empty:
        return {}
    r = row.iloc[0].to_dict()
    window = db.settings(cid).get("deadline_window_days", 14)
    alloc = active_allocations(cid)
    ea = alloc[alloc["employee_id"] == employee_id][["project_code", "project", "hours_per_week", "project_priority"]]
    tasks = db.df(
        """SELECT t.*, p.code AS project_code FROM tasks t JOIN projects p ON p.id = t.project_id
           WHERE t.company_id = ? AND t.assignee_id = ? AND t.status IN ('Not Started','In Progress','Blocked','Under Review')
           ORDER BY t.due_date""", (cid, employee_id))
    if not tasks.empty:
        tasks["remaining_hours"] = (tasks["est_hours"] * (1 - tasks["completion"] / 100)).round(1)
        total_rem = tasks["remaining_hours"].sum() or 1
        share = r["over_hours"] / max(r["allocated"], 1)
        tasks["delay_exposure_days"] = (tasks["remaining_hours"] * share / (r["capacity"] / 5 if r["capacity"] else 7)).round(1)
        tasks["due"] = pd.to_datetime(tasks["due_date"]).dt.date
        tasks["within_window"] = (tasks["due"] <= ref + timedelta(days=window))
        _ = total_rem
    return {"summary": r, "projects": ea, "tasks": tasks}


def candidates(cid: int, required_skills: str, exclude_employee: int | None, needed_hours: float = 0,
               ref: date | None = None, limit: int = 5) -> pd.DataFrame:
    """Rank alternative employees: skill match first, then spare capacity. Never assigns anything."""
    wl = workload(cid, ref)
    if wl.empty:
        return wl
    th = db.settings(cid)["thresholds"]
    req = {s.strip().lower() for s in (required_skills or "").split(",") if s.strip()}
    wl = wl[(wl["employee_id"] != (exclude_employee or -1)) & (~wl["absent_now"])].copy()
    wl["skill_match"] = wl["skills"].fillna("").apply(
        lambda s: len(req & {x.strip().lower() for x in s.split(",")}))
    wl["spare_hours"] = wl["remaining"]
    wl = wl[(wl["utilisation"] < th["high"]) & (wl["spare_hours"] > 0)]
    if req:
        wl = wl[wl["skill_match"] > 0]
    wl["fits_need"] = wl["spare_hours"] >= needed_hours
    wl = wl.sort_values(["skill_match", "fits_need", "spare_hours"], ascending=[False, False, False])
    return wl.head(limit)[["employee_id", "name", "location", "job_role", "skills", "skill_match",
                           "utilisation", "spare_hours", "fits_need"]]


def recommendations(r: dict) -> list[str]:
    recs = []
    if r.get("over_hours", 0) > 0:
        recs = [
            "Reassign selected tasks to an available qualified employee (manager approval required).",
            "Reduce or redistribute this employee's weekly allocation across projects.",
            "Adjust task deadlines after manager approval.",
            "Review project priorities with the project managers involved.",
            "Add capacity or subcontractor support where appropriate.",
        ]
    return recs


def project_progress(cid: int) -> pd.DataFrame:
    """Progress = sum(est_hours x completion) / sum(est_hours), excluding cancelled tasks.
    Tasks without an estimate count with a weight of 1 hour."""
    t = db.df("SELECT project_id, est_hours, completion, status FROM tasks WHERE company_id = ? AND status != 'Cancelled'", (cid,))
    if t.empty:
        return pd.DataFrame(columns=["project_id", "progress"])
    t["w"] = t["est_hours"].fillna(0).clip(lower=0).replace(0, 1)
    t["c"] = t.apply(lambda x: 100 if x["status"] == "Completed" else x["completion"], axis=1)
    t["wc"] = t["w"] * t["c"]
    g = t.groupby("project_id")[["wc", "w"]].sum()
    g["progress"] = (g["wc"] / g["w"]).round(1)
    return g[["progress"]].reset_index()
