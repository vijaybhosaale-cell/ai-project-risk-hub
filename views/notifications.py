"""Notification log and test sending."""
from __future__ import annotations

import streamlit as st

from hub import db, notify, ui
from hub.i18n import lang, t

GMAIL_STEPS = {
    "en": """1. In your Google Account, open **Security** and turn on **2-Step Verification**.
2. Open **myaccount.google.com/apppasswords**, type the name *Risk Hub* and click **Create**.
3. Copy the 16-character password Google shows (it is shown only once).
4. On **share.streamlit.io** → your app → **⋮ → Settings → Secrets**, paste the three lines below with your own address and the App password, then **Save**.
5. The app restarts within a minute. Come back here and click **Send test e-mail**.

The App password is stored only in Streamlit's encrypted secrets, never in this app's database. You can revoke it at any time in your Google Account.""",
    "fr": """1. Dans votre compte Google, ouvrez **Sécurité** et activez la **validation en deux étapes**.
2. Ouvrez **myaccount.google.com/apppasswords**, saisissez le nom *Risk Hub* et cliquez sur **Créer**.
3. Copiez le mot de passe de 16 caractères affiché (il n'est affiché qu'une fois).
4. Sur **share.streamlit.io** → votre app → **⋮ → Settings → Secrets**, collez les trois lignes ci-dessous avec votre adresse et le mot de passe d'application, puis **Save**.
5. L'application redémarre en une minute. Revenez ici et cliquez sur **Envoyer un e-mail de test**.

Le mot de passe d'application est stocké uniquement dans les secrets chiffrés de Streamlit, jamais dans la base de données. Vous pouvez le révoquer à tout moment dans votre compte Google.""",
}


def render(ctx: dict) -> None:
    cid, edit = ctx["cid"], ctx["can_edit"]
    ui.page_header("notifications", t("Notifications"), t("E-mail and NTFY push notifications"))
    s = db.settings(cid)
    ec = notify.email_config(cid)
    c1, c2 = st.columns(2)
    c1.markdown(f"**NTFY**: {'✅ ' + t('enabled') if s['ntfy']['enabled'] and s['ntfy']['topic'] else '⚪ ' + t('not configured')}"
                f" · {s['ntfy']['server']}/{s['ntfy']['topic'] or '…'}")
    ok_mail = ec["enabled"] and ec["host"] and ec["password"] and ec["recipients"]
    c2.markdown(f"**{t('E-mail')}**: {'✅ ' + t('enabled') if ok_mail else '⚪ ' + t('not configured')}"
                f" · {ec['host'] or '-'} · {t('to')}: {ec['recipients'] or '-'}")
    st.info("🔔 " + t("Every user also receives these events in their in-app Inbox, with or without e-mail."))
    with st.expander("📧 " + t("How to send e-mails through Gmail (2 minutes)"), expanded=not ok_mail):
        st.markdown(GMAIL_STEPS["fr" if lang() == "fr" else "en"])
        st.code('SMTP_USER = "your.address@gmail.com"\nSMTP_PASSWORD = "abcd efgh ijkl mnop"\nEMAIL_TO = "your.address@gmail.com"', language="toml")
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
