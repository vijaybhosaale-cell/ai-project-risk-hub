"""Notifications: NTFY (HTTP push) and SMTP e-mail. Every attempt is logged."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

import requests

from . import db


def _secret(name: str) -> str:
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, "")


def _log(cid, channel, recipient, subject, body, status, error=""):
    db.execute(
        "INSERT INTO notifications (company_id, channel, recipient, subject, body, status, error, ts) VALUES (?,?,?,?,?,?,?,?)",
        (cid, channel, recipient, subject, body, status, error[:500], db.now()),
    )


def send_ntfy(cid: int, subject: str, body: str, priority: str = "default") -> tuple[bool, str]:
    s = db.settings(cid)["ntfy"]
    topic = s.get("topic", "").strip()
    if not s.get("enabled") or not topic:
        _log(cid, "ntfy", topic or "-", subject, body, "Not sent (not configured)")
        return False, "NTFY not configured"
    url = f"{s.get('server', 'https://ntfy.sh').rstrip('/')}/{topic}"
    try:
        r = requests.post(url, data=body.encode("utf-8"),
                          headers={"Title": subject.encode("ascii", "ignore").decode() or "Hub alert",
                                   "Priority": priority, "Tags": "warning"}, timeout=8)
        ok = r.status_code < 300
        _log(cid, "ntfy", topic, subject, body, "Sent" if ok else "Failed", "" if ok else f"HTTP {r.status_code}: {r.text[:200]}")
        return ok, "Sent" if ok else f"HTTP {r.status_code}"
    except Exception as e:  # network errors are logged, never raised to the UI
        _log(cid, "ntfy", topic, subject, body, "Failed", str(e))
        return False, str(e)


def send_email(cid: int, subject: str, body: str, to: str | None = None) -> tuple[bool, str]:
    s = db.settings(cid)["email"]
    recipients = (to or s.get("recipients", "")).strip()
    password = _secret("SMTP_PASSWORD")
    if not s.get("enabled") or not s.get("smtp_host") or not recipients:
        _log(cid, "email", recipients or "-", subject, body, "Not sent (not configured)")
        return False, "E-mail not configured"
    if not password:
        _log(cid, "email", recipients, subject, body, "Not sent (no SMTP_PASSWORD secret)")
        return False, "SMTP_PASSWORD secret missing"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s.get("sender") or s.get("smtp_user")
    msg["To"] = recipients
    msg.set_content(body)
    try:
        with smtplib.SMTP(s["smtp_host"], int(s.get("smtp_port") or 587), timeout=10) as server:
            server.starttls()
            server.login(s.get("smtp_user"), password)
            server.send_message(msg)
        _log(cid, "email", recipients, subject, body, "Sent")
        return True, "Sent"
    except Exception as e:
        _log(cid, "email", recipients, subject, body, "Failed", str(e))
        return False, str(e)


def notify(cid: int, event: str, subject: str, body: str, priority: str = "default") -> list[str]:
    """Send through every configured channel if the event type is enabled."""
    s = db.settings(cid)
    if not s["notify_on"].get(event, True):
        return []
    results = []
    ok, msg = send_ntfy(cid, subject, body, priority)
    results.append(f"NTFY: {msg}")
    ok, msg = send_email(cid, subject, body)
    results.append(f"E-mail: {msg}")
    return results
