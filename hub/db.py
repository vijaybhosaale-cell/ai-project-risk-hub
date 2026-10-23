"""SQLite storage layer.

Every tenant-owned table carries a ``company_id`` column. All page code reads the
company id from the authenticated session (never from user input) and passes it
to the helpers below, which is how company-level data isolation is enforced in
this prototype.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

import pandas as pd

DB_PATH = os.environ.get(
    "HUB_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "hub.db"),
)
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, email TEXT, industry TEXT, country TEXT, timezone TEXT,
    language TEXT DEFAULT 'en', currency TEXT DEFAULT 'EUR',
    declared_employees INTEGER, declared_projects INTEGER, declared_locations TEXT,
    objectives TEXT, reporting_prefs TEXT, case_facts TEXT,
    setup_complete INTEGER DEFAULT 0, is_demo INTEGER DEFAULT 0, active INTEGER DEFAULT 1,
    settings TEXT DEFAULT '{}', created_at TEXT
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER, name TEXT, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
    role TEXT NOT NULL, employee_id INTEGER, subcontractor_id INTEGER,
    active INTEGER DEFAULT 1, failed_attempts INTEGER DEFAULT 0, locked_until TEXT,
    last_login TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS reset_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, token_hash TEXT,
    expires_at TEXT, used INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    name TEXT, address TEXT, manager TEXT, employee_count INTEGER, active_projects INTEGER, timezone TEXT
);
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    emp_code TEXT, name TEXT, email TEXT, phone TEXT, location_id INTEGER,
    department TEXT, job_role TEXT, skills TEXT, weekly_capacity REAL DEFAULT 35,
    working_hours TEXT, employment_status TEXT DEFAULT 'Active', manager_id INTEGER,
    remote_eligible INTEGER DEFAULT 0, join_date TEXT, is_new_hire INTEGER DEFAULT 0,
    mfa_status TEXT DEFAULT 'Not recorded', device_status TEXT DEFAULT 'Not recorded',
    vpn_status TEXT DEFAULT 'Not recorded', edr_status TEXT DEFAULT 'Not recorded',
    leave_date TEXT, active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    name TEXT, contact TEXT, email TEXT, country TEXT, is_eu INTEGER DEFAULT 1,
    recurring INTEGER DEFAULT 1, contract_start TEXT, contract_end TEXT, renewal_date TEXT,
    contract_value REAL, sla TEXT, sla_response_hours INTEGER, deliverables TEXT,
    dp_obligations TEXT, incident_obligations TEXT, evidence_notes TEXT
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    code TEXT, name TEXT, description TEXT, client_id INTEGER, manager_id INTEGER,
    location_id INTEGER, start_date TEXT, end_date TEXT, budget REAL DEFAULT 0,
    planned_spend REAL DEFAULT 0, actual_spend REAL DEFAULT 0, forecast_spend REAL DEFAULT 0,
    estimated_effort REAL DEFAULT 0, status TEXT DEFAULT 'Active', priority TEXT DEFAULT 'Medium',
    sla_ref TEXT, archived INTEGER DEFAULT 0, financials_are_estimates INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    employee_id INTEGER, project_id INTEGER, hours_per_week REAL, project_role TEXT
);
CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    project_id INTEGER, name TEXT, due_date TEXT, status TEXT DEFAULT 'Planned'
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    code TEXT, project_id INTEGER, title TEXT, description TEXT, assignee_id INTEGER,
    contributors TEXT, subcontractor_id INTEGER, start_date TEXT, due_date TEXT,
    est_hours REAL DEFAULT 0, actual_hours REAL DEFAULT 0, priority TEXT DEFAULT 'Medium',
    status TEXT DEFAULT 'Not Started', depends_on TEXT, completion INTEGER DEFAULT 0,
    required_skills TEXT, risk_level TEXT DEFAULT 'Low', is_critical INTEGER DEFAULT 0,
    documents TEXT, flagged INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    task_id INTEGER, field TEXT, old_value TEXT, new_value TEXT, reason TEXT, user TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS reassignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    task_id INTEGER, from_employee INTEGER, to_employee INTEGER, reason TEXT,
    status TEXT DEFAULT 'Pending', requested_by TEXT, decided_by TEXT, created_at TEXT, decided_at TEXT
);
CREATE TABLE IF NOT EXISTS absences (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    employee_id INTEGER, absence_type TEXT, start_date TEXT, end_date TEXT, reason TEXT,
    created_by TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS budget_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    project_id INTEGER, month TEXT, planned REAL, actual REAL, is_estimate INTEGER DEFAULT 1, note TEXT
);
CREATE TABLE IF NOT EXISTS risks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    code TEXT, title TEXT, title_fr TEXT, category TEXT, case_category TEXT,
    probability INTEGER, impact INTEGER, status TEXT DEFAULT 'Open',
    evidence_status TEXT DEFAULT 'Unconfirmed hypothesis', source TEXT, rule_key TEXT,
    project_id INTEGER, employee_id INTEGER, owner TEXT, cause TEXT, event TEXT, consequences TEXT,
    evidence_needed TEXT, recommended_action TEXT, explanation TEXT, explanation_fr TEXT,
    created_at TEXT, updated_at TEXT, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS risk_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    risk_id INTEGER, action TEXT, owner TEXT, due_date TEXT, status TEXT DEFAULT 'Open',
    note TEXT, user TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS trainings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    name TEXT, category TEXT, required_for TEXT, duration_hours REAL
);
CREATE TABLE IF NOT EXISTS training_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    employee_id INTEGER, training_id INTEGER, due_date TEXT, status TEXT DEFAULT 'Assigned',
    completion INTEGER DEFAULT 0, score INTEGER, completed_date TEXT
);
CREATE TABLE IF NOT EXISTS onboarding_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    employee_id INTEGER, step_no INTEGER, done INTEGER DEFAULT 0, done_date TEXT, evidence TEXT
);
CREATE TABLE IF NOT EXISTS access_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    employee_id INTEGER, lifecycle_event TEXT, system TEXT, permission TEXT, privileged INTEGER DEFAULT 0,
    justification TEXT, requester TEXT, approver TEXT, approval_status TEXT DEFAULT 'Pending',
    activation_status TEXT DEFAULT 'Not activated', review_date TEXT, last_reviewed TEXT,
    revocation_status TEXT DEFAULT 'Not required', created_at TEXT
);
CREATE TABLE IF NOT EXISTS subcontractors (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    name TEXT, company_name TEXT, contact TEXT, email TEXT, phone TEXT,
    contract_start TEXT, contract_end TEXT, client_id INTEGER, project_id INTEGER,
    estimated_cost REAL, security_assessment TEXT DEFAULT 'Not started', obligations TEXT,
    data_access TEXT, access_expiry TEXT, incident_notification TEXT,
    performance TEXT DEFAULT 'On track', security_concern TEXT, delivery_concern TEXT, corrective_action TEXT
);
CREATE TABLE IF NOT EXISTS compliance_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    client_id INTEGER, evidence_type TEXT, status TEXT DEFAULT 'Missing', owner TEXT,
    due_date TEXT, last_review TEXT, reference TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS cloud_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    name TEXT, provider TEXT, owner TEXT, criticality TEXT, provider_sla TEXT, dependencies TEXT,
    outages_12m INTEGER DEFAULT 0, last_restore_test TEXT, rto_hours REAL, rpo_hours REAL,
    recovery_evidence TEXT DEFAULT 'Not recorded'
);
CREATE TABLE IF NOT EXISTS digital_tools (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    name TEXT, owner TEXT, approved TEXT DEFAULT 'Approved', config_review_date TEXT,
    integrations TEXT, change_records TEXT, concern TEXT, remediation TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    signal_date TEXT, signal_type TEXT, title TEXT, system TEXT, location_id INTEGER,
    team TEXT, supplier TEXT, severity TEXT, status TEXT DEFAULT 'Warning signal',
    root_cause TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER,
    channel TEXT, recipient TEXT, subject TEXT, body TEXT, status TEXT, error TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER,
    user TEXT, action TEXT, entity TEXT, entity_id TEXT, details TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    user_id INTEGER, kind TEXT, title TEXT, body TEXT, page TEXT, created_at TEXT, read_at TEXT
);
CREATE TABLE IF NOT EXISTS resource_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL,
    kind TEXT, task_id INTEGER, project_id INTEGER, employee_id INTEGER, subcontractor_id INTEGER,
    skills TEXT, hours_per_week REAL, start_date TEXT, end_date TEXT, new_due_date TEXT,
    justification TEXT, status TEXT DEFAULT 'Pending', requested_by TEXT, decided_by TEXT,
    decision_note TEXT, created_at TEXT, decided_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, token_hash TEXT UNIQUE,
    created_at TEXT, expires_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_inbox_u ON inbox(user_id, read_at);
CREATE INDEX IF NOT EXISTS ix_emp_c ON employees(company_id);
CREATE INDEX IF NOT EXISTS ix_task_c ON tasks(company_id);
CREATE INDEX IF NOT EXISTS ix_alloc_c ON allocations(company_id);
CREATE INDEX IF NOT EXISTS ix_risk_c ON risks(company_id);
"""

# Tables whose rows belong to exactly one company.
TENANT_TABLES = {
    "locations", "employees", "clients", "projects", "allocations", "milestones", "tasks",
    "task_history", "reassignments", "absences", "budget_lines", "risks", "risk_actions",
    "trainings", "training_assignments", "onboarding_steps", "access_requests", "subcontractors",
    "compliance_evidence", "cloud_services", "digital_tools", "signals", "notifications", "audit_log",
    "inbox", "resource_requests",
}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def conn():
    with _lock:
        con = _connect()
        try:
            yield con
            con.commit()
        finally:
            con.close()


def init_schema() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def query(sql: str, params: tuple | list = ()) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def one(sql: str, params: tuple | list = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql: str, params: tuple | list = ()):
    with conn() as c:
        r = c.execute(sql, params).fetchone()
        return r[0] if r else None


def execute(sql: str, params: tuple | list = ()) -> int:
    with conn() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def df(sql: str, params: tuple | list = ()) -> pd.DataFrame:
    with conn() as c:
        return pd.read_sql_query(sql, c, params=params)


# ---- tenant-scoped helpers -------------------------------------------------

def _check(table: str) -> None:
    if table not in TENANT_TABLES:
        raise ValueError(f"Unknown tenant table {table}")


def t_df(table: str, cid: int, where: str = "", params: tuple = (), order: str = "id") -> pd.DataFrame:
    _check(table)
    sql = f"SELECT * FROM {table} WHERE company_id = ?" + (f" AND {where}" if where else "") + f" ORDER BY {order}"
    return df(sql, (cid, *params))


def t_rows(table: str, cid: int, where: str = "", params: tuple = (), order: str = "id") -> list[dict]:
    _check(table)
    sql = f"SELECT * FROM {table} WHERE company_id = ?" + (f" AND {where}" if where else "") + f" ORDER BY {order}"
    return query(sql, (cid, *params))


def t_get(table: str, cid: int, rid: int) -> dict | None:
    _check(table)
    return one(f"SELECT * FROM {table} WHERE company_id = ? AND id = ?", (cid, rid))


def t_insert(table: str, cid: int, data: dict) -> int:
    _check(table)
    data = {k: v for k, v in data.items() if k not in ("id", "company_id")}
    cols = ["company_id", *data.keys()]
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    return execute(sql, (cid, *data.values()))


def t_update(table: str, cid: int, rid: int, data: dict) -> None:
    _check(table)
    data = {k: v for k, v in data.items() if k not in ("id", "company_id")}
    if not data:
        return
    sets = ", ".join(f"{k} = ?" for k in data)
    execute(f"UPDATE {table} SET {sets} WHERE company_id = ? AND id = ?", (*data.values(), cid, rid))


def t_delete(table: str, cid: int, rid: int) -> None:
    _check(table)
    execute(f"DELETE FROM {table} WHERE company_id = ? AND id = ?", (cid, rid))


def company(cid: int) -> dict | None:
    return one("SELECT * FROM companies WHERE id = ?", (cid,))


DEFAULT_SETTINGS = {
    "thresholds": {"under": 60, "high": 85, "over": 100},
    "deadline_window_days": 14,
    "budget_warning_pct": 90,
    "risk_bands": {"medium": 8, "high": 15, "critical": 20},
    "track": {"cyber": True, "operational": True, "gdpr": True, "supplier": True,
              "continuity": True, "sla": True},
    "ntfy": {"enabled": False, "server": "https://ntfy.sh", "topic": ""},
    "email": {"enabled": False, "smtp_host": "", "smtp_port": 587, "smtp_user": "",
              "sender": "", "recipients": ""},
    "notify_on": {"absence": True, "critical_risk": True, "reassignment": True, "overcapacity": True,
                  "assignment": True, "deadline": True, "resource_request": True, "approval": True},
}


def settings(cid: int) -> dict:
    c = company(cid)
    s = json.loads((c or {}).get("settings") or "{}")
    merged = json.loads(json.dumps(DEFAULT_SETTINGS))
    for k, v in s.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def save_settings(cid: int, s: dict) -> None:
    execute("UPDATE companies SET settings = ? WHERE id = ?", (json.dumps(s), cid))
