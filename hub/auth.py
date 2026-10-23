"""Authentication: salted PBKDF2-SHA256 hashing, lockout, password reset tokens."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta

from . import db

ITERATIONS = 150_000
MAX_FAILED = 5
LOCK_MINUTES = 15

ROLES = [
    "Platform Administrator",
    "Company Administrator",
    "Project Manager",
    "Team Leader",
    "Employee",
    "HR / Training Manager",
    "Risk / Compliance Manager",
    "Finance Manager",
    "Subcontractor",
]
TENANT_ROLES = ROLES[1:]


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("At least 10 characters")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        problems.append("Must contain letters and digits")
    return problems


def valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))


def authenticate(email: str, password: str) -> tuple[dict | None, str]:
    """Returns (user, message_key)."""
    email = (email or "").strip().lower()
    user = db.one("SELECT * FROM users WHERE lower(email) = ?", (email,))
    if not user:
        # Constant-ish time: still run a hash to avoid user enumeration by timing.
        verify_password(password, "pbkdf2_sha256$1000$00$00")
        return None, "Invalid email or password."
    if not user["active"]:
        return None, "This account is deactivated."
    if user["locked_until"] and user["locked_until"] > db.now():
        return None, "Account temporarily locked after repeated failed attempts. Try again later."
    if user["company_id"]:
        comp = db.company(user["company_id"])
        if comp and not comp["active"]:
            return None, "This company workspace is suspended."
    if not verify_password(password, user["password_hash"]):
        attempts = (user["failed_attempts"] or 0) + 1
        locked = None
        if attempts >= MAX_FAILED:
            locked = (datetime.now() + timedelta(minutes=LOCK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
            attempts = 0
        db.execute("UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?", (attempts, locked, user["id"]))
        db.execute("INSERT INTO audit_log (company_id, user, action, entity, entity_id, details, ts) VALUES (?,?,?,?,?,?,?)",
                   (user["company_id"], email, "login_failed", "user", str(user["id"]), f"attempt {attempts}", db.now()))
        return None, "Invalid email or password."
    db.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login = ? WHERE id = ?", (db.now(), user["id"]))
    db.execute("INSERT INTO audit_log (company_id, user, action, entity, entity_id, details, ts) VALUES (?,?,?,?,?,?,?)",
               (user["company_id"], email, "login", "user", str(user["id"]), "", db.now()))
    return user, "ok"


def create_user(company_id: int | None, name: str, email: str, password: str, role: str,
                employee_id: int | None = None, subcontractor_id: int | None = None,
                pw_hash: str | None = None) -> int:
    return db.execute(
        "INSERT INTO users (company_id, name, email, password_hash, role, employee_id, subcontractor_id, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (company_id, name, email.strip().lower(), pw_hash or hash_password(password), role,
         employee_id, subcontractor_id, db.now()),
    )


def email_taken(email: str) -> bool:
    return db.scalar("SELECT COUNT(*) FROM users WHERE lower(email) = ?", (email.strip().lower(),)) > 0


def create_reset_token(email: str) -> str | None:
    user = db.one("SELECT * FROM users WHERE lower(email) = ? AND active = 1", (email.strip().lower(),))
    if not user:
        return None
    token = secrets.token_urlsafe(18)
    th = hashlib.sha256(token.encode()).hexdigest()
    exp = (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO reset_tokens (user_id, token_hash, expires_at) VALUES (?,?,?)", (user["id"], th, exp))
    return token


def reset_with_token(email: str, token: str, new_password: str) -> bool:
    user = db.one("SELECT * FROM users WHERE lower(email) = ?", (email.strip().lower(),))
    if not user:
        return False
    th = hashlib.sha256(token.strip().encode()).hexdigest()
    row = db.one("SELECT * FROM reset_tokens WHERE user_id = ? AND token_hash = ? AND used = 0 AND expires_at > ?",
                 (user["id"], th, db.now()))
    if not row:
        return False
    db.execute("UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = NULL WHERE id = ?",
               (hash_password(new_password), user["id"]))
    db.execute("UPDATE reset_tokens SET used = 1 WHERE id = ?", (row["id"],))
    db.execute("INSERT INTO audit_log (company_id, user, action, entity, entity_id, details, ts) VALUES (?,?,?,?,?,?,?)",
               (user["company_id"], user["email"], "password_reset", "user", str(user["id"]), "via token", db.now()))
    return True


def temp_password() -> str:
    return "Tmp-" + secrets.token_urlsafe(9) + "7"


SESSION_HOURS = 8


def create_session(user_id: int) -> str:
    """Server-side session for 'stay signed in after refresh'. Only a hash of the token is stored."""
    token = secrets.token_urlsafe(32)
    exp = (datetime.now() + timedelta(hours=SESSION_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO sessions (user_id, token_hash, created_at, expires_at) VALUES (?,?,?,?)",
               (user_id, hashlib.sha256(token.encode()).hexdigest(), db.now(), exp))
    return token


def session_user(token: str | None) -> dict | None:
    if not token or not isinstance(token, str):
        return None
    row = db.one("SELECT * FROM sessions WHERE token_hash = ? AND expires_at > ?",
                 (hashlib.sha256(token.encode()).hexdigest(), db.now()))
    if not row:
        return None
    user = db.one("SELECT * FROM users WHERE id = ? AND active = 1", (row["user_id"],))
    if user and user["company_id"]:
        comp = db.company(user["company_id"])
        if not comp or not comp["active"]:
            return None
    return user


def end_session(token: str | None) -> None:
    if token and isinstance(token, str):
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))
