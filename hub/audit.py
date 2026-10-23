from __future__ import annotations

from . import db


def log(cid: int | None, user: str, action: str, entity: str, entity_id="", details: str = "") -> None:
    db.execute(
        "INSERT INTO audit_log (company_id, user, action, entity, entity_id, details, ts) VALUES (?,?,?,?,?,?,?)",
        (cid, user, action, entity, str(entity_id), details[:1000], db.now()),
    )
