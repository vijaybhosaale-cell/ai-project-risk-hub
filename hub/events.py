"""Business events: one call posts to the in-app 🔔 inbox of the right people and
sends the configured e-mail / NTFY notification. This is what keeps manager and
employee views interconnected."""
from __future__ import annotations

from typing import Iterable

from . import db, notify

MANAGER_ROLES = ("Company Administrator", "Project Manager")
ICONS = {"assignment": "📌", "deadline": "📅", "reassignment": "🔁", "approval": "✅", "rejected": "✖️",
         "absence": "🏖️", "critical_risk": "🚨", "resource_request": "🧩", "access": "🔑", "training": "🎓",
         "progress": "📈", "allocation": "⚖️", "info": "ℹ️", "overcapacity": "⚠️"}


def users_for_employees(cid: int, employee_ids: Iterable) -> set[int]:
    ids = [int(e) for e in employee_ids if e]
    if not ids:
        return set()
    q = f"SELECT id FROM users WHERE company_id = ? AND active = 1 AND employee_id IN ({','.join('?' * len(ids))})"
    return {r["id"] for r in db.query(q, (cid, *ids))}


def users_for_roles(cid: int, roles: Iterable[str]) -> set[int]:
    roles = list(roles)
    if not roles:
        return set()
    q = f"SELECT id FROM users WHERE company_id = ? AND active = 1 AND role IN ({','.join('?' * len(roles))})"
    return {r["id"] for r in db.query(q, (cid, *roles))}


def emit(cid: int, kind: str, title: str, body: str = "", *, employees: Iterable = (), roles: Iterable[str] = (),
         users: Iterable[int] = (), page: str | None = None, email: bool = True, exclude_user: int | None = None,
         priority: str = "default") -> int:
    targets = set(int(u) for u in users if u) | users_for_employees(cid, employees) | users_for_roles(cid, roles)
    if exclude_user:
        targets.discard(int(exclude_user))
    now = db.now()
    for uid in targets:
        db.execute("INSERT INTO inbox (company_id, user_id, kind, title, body, page, created_at) VALUES (?,?,?,?,?,?,?)",
                   (cid, uid, kind, title, body, page, now))
    if email:
        notify.notify(cid, kind, title, body, priority)
    return len(targets)


def unread(user_id: int) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM inbox WHERE user_id = ? AND read_at IS NULL", (user_id,)) or 0)


def employee_user_by_email(cid: int, email: str) -> int | None:
    r = db.one("SELECT id FROM users WHERE company_id = ? AND lower(email) = ?", (cid, (email or "").lower()))
    return r["id"] if r else None
