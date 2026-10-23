"""CSV import for employees (used by the Employees page and the setup wizard)."""
from __future__ import annotations

import io

import pandas as pd

from . import db

EMP_COLUMNS = ["employee_id", "name", "email", "role", "department", "location", "skills", "weekly_capacity",
               "working_hours", "employment_status", "manager_email", "remote_eligible", "join_date"]

TEMPLATE = pd.DataFrame([{
    "employee_id": "E-001", "name": "Jane Example", "email": "jane@example.com", "role": "Software Engineer",
    "department": "Engineering", "location": "Paris", "skills": "Python,SQL", "weekly_capacity": 35,
    "working_hours": "Mon-Fri 09:00-17:00", "employment_status": "Active", "manager_email": "",
    "remote_eligible": 1, "join_date": "2025-09-01"}])


def template_csv() -> bytes:
    return TEMPLATE.to_csv(index=False).encode()


def import_employees(cid: int, raw: bytes) -> tuple[int, list[str]]:
    errors: list[str] = []
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:  # malformed CSV
        return 0, [f"Could not read CSV: {e}"]
    df.columns = [c.strip().lower() for c in df.columns]
    if "name" not in df.columns:
        return 0, ["Missing required column: name"]
    locs = {r["name"].lower(): r["id"] for r in db.t_rows("locations", cid)}
    n = 0
    for i, r in df.iterrows():
        name = str(r.get("name", "")).strip()
        if not name or name == "nan":
            errors.append(f"Row {i + 2}: empty name")
            continue
        loc_name = str(r.get("location", "") or "").strip()
        if loc_name and loc_name.lower() not in locs:
            locs[loc_name.lower()] = db.t_insert("locations", cid, {"name": loc_name, "employee_count": 0, "active_projects": 0})
        try:
            cap = float(r.get("weekly_capacity", 35) or 35)
        except (TypeError, ValueError):
            cap = 35.0
            errors.append(f"Row {i + 2}: invalid weekly_capacity, 35 used")
        db.t_insert("employees", cid, {
            "emp_code": str(r.get("employee_id", "") or f"E-{i + 1:03d}"), "name": name, "email": str(r.get("email", "") or ""),
            "job_role": str(r.get("role", "") or ""), "department": str(r.get("department", "") or ""),
            "location_id": locs.get(loc_name.lower()), "skills": str(r.get("skills", "") or ""), "weekly_capacity": cap,
            "working_hours": str(r.get("working_hours", "") or ""), "employment_status": str(r.get("employment_status", "Active") or "Active"),
            "remote_eligible": int(float(r.get("remote_eligible", 0) or 0)), "join_date": str(r.get("join_date", "") or ""),
            "active": 1})
        n += 1
    return n, errors
