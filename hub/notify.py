"""Notifications: NTFY (HTTP push) and SMTP e-mail. Every attempt is logged."""
from __future__ import annotations

import os
import smtplib
import threading
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


_MUTED = {"on": False}  # used while generating demo data, so no e-mails are sent at start-up


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


def email_config(cid: int) -> dict:
    """E-mail settings: company settings first, then deployment secrets (e.g. Gmail).

    Secrets (Streamlit Cloud > Manage app > Settings > Secrets):
      SMTP_USER = "your.address@gmail.com"
      SMTP_PASSWORD = "the 16-character Gmail App password"
      EMAIL_TO = "where notifications are sent (comma-separated)"
      SMTP_HOST / SMTP_PORT are optional (default smtp.gmail.com / 587).
    EMAIL_TO is used for the demo workspace; real companies set their own recipients in Company settings.
    """
    s = db.settings(cid)["email"]
    comp = db.company(cid) or {}
    user = s.get("smtp_user") or _secret("SMTP_USER")
    host = s.get("smtp_host") or _secret("SMTP_HOST") or ("smtp.gmail.com" if user.endswith("@gmail.com") else "")
    port = int(s.get("smtp_port") or _secret("SMTP_PORT") or 587)
    recipients = (s.get("recipients") or (_secret("EMAIL_TO") if comp.get("is_demo") else "")).strip()
    password = _secret("SMTP_PASSWORD").replace(" ", "")
    from_secrets = bool(_secret("SMTP_USER") and password)
    enabled = bool(s.get("enabled")) or (from_secrets and bool(recipients))
    return {"enabled": enabled, "host": host, "port": port, "user": user, "password": password,
            "sender": s.get("sender") or user, "recipients": recipients}


def send_email(cid: int, subject: str, body: str, to: str | None = None) -> tuple[bool, str]:
    c = email_config(cid)
    recipients = (to or c["recipients"]).strip()
    if not c["enabled"] or not c["host"] or not recipients:
        _log(cid, "email", recipients or "-", subject, body, "Not sent (not configured)")
        return False, "E-mail not configured"
    if not c["password"]:
        _log(cid, "email", recipients, subject, body, "Not sent (no SMTP_PASSWORD secret)")
        return False, "SMTP_PASSWORD secret missing"
    comp = (db.company(cid) or {}).get("name", "")
    msg = EmailMessage()
    msg["Subject"] = f"[{comp}] {subject}" if comp else subject
    msg["From"] = c["sender"]
    msg["To"] = recipients
    msg.set_content(body + "\n\n-- AI Project & Risk Intelligence Hub (automatic notification)")
    try:
        with smtplib.SMTP(c["host"], c["port"], timeout=10) as server:
            server.starttls()
            server.login(c["user"], c["password"])
            server.send_message(msg)
        _log(cid, "email", recipients, subject, body, "Sent")
        return True, "Sent"
    except Exception as e:
        _log(cid, "email", recipients, subject, body, "Failed", str(e))
        return False, str(e)


def notify(cid: int, event: str, subject: str, body: str, priority: str = "default") -> list[str]:
    """Send through every configured channel if the event type is enabled."""
    s = db.settings(cid)
    if not s["notify_on"].get(event, True) or _MUTED.get("on"):
        return []
    def _send():
        send_ntfy(cid, subject, body, priority)
        send_email(cid, subject, body)
    # Sent in the background so the page never waits for the mail server.
    threading.Thread(target=_send, daemon=True).start()
    return ["NTFY / e-mail: queued (see Notifications log)"]
