"""Notification log and test sending."""
from __future__ import annotations

import streamlit as st

from hub import db, notify, ui
from hub.i18n import t


def render(ctx: dict) -> None:
    cid, edit = ctx["cid"], ctx["can_edit"]
    ui.page_header("notifications", t("Notifications"), t("E-mail and NTFY push notifications"))
    s = db.settings(cid)
    c1, c2 = st.columns(2)
    c1.markdown(f"**NTFY**: {'✅ ' + t('enabled') if s['ntfy']['enabled'] and s['ntfy']['topic'] else '⚪ ' + t('not configured')}"
                f" · {s['ntfy']['server']}/{s['ntfy']['topic'] or '…'}")
    c2.markdown(f"**{t('E-mail')}**: {'✅ ' + t('enabled') if s['email']['enabled'] and s['email']['smtp_host'] else '⚪ ' + t('not configured')}"
                f" · {s['email']['smtp_host'] or '-'}")
    st.caption(t("Configure channels in Company settings → Notifications. The SMTP password is read from the SMTP_PASSWORD secret, never stored in the database."))
    if edit:
        b1, b2, _ = st.columns([1, 1, 3])
        if b1.button("📲 " + t("Send test NTFY")):
            ok, msg = notify.send_ntfy(cid, "Test from Risk Intelligence Hub", "This is a test notification.")
            (st.success if ok else st.warning)(f"NTFY: {msg}")
        if b2.button("✉️ " + t("Send test e-mail")):
            ok, msg = notify.send_email(cid, "Test from Risk Intelligence Hub", "This is a test e-mail.")
            (st.success if ok else st.warning)(f"E-mail: {msg}")
    log = db.t_df("notifications", cid, order="id DESC")
    ui.table(log, {"ts": "When", "channel": "Channel", "recipient": "Recipient", "subject": "Subject", "status": "Status", "error": "Error"},
             translate_values=("status",), height=440)
