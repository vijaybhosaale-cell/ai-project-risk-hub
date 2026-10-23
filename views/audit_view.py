"""Audit log viewer."""
from __future__ import annotations

import streamlit as st

from hub import db, ui
from hub.i18n import t


def render(ctx: dict) -> None:
    cid = ctx["cid"]
    ui.page_header("audit", t("Audit log"), t("Who changed what, and when"))
    log = db.t_df("audit_log", cid, order="id DESC")
    if log.empty:
        st.info(t("No audit entries yet."))
        return
    f = st.columns(3)
    us = f[0].multiselect(t("User"), sorted(log["user"].dropna().unique()), placeholder=t("All"))
    ac = f[1].multiselect(t("Action"), sorted(log["action"].dropna().unique()), placeholder=t("All"))
    q = f[2].text_input("🔍 " + t("Search"))
    if us:
        log = log[log["user"].isin(us)]
    if ac:
        log = log[log["action"].isin(ac)]
    if q:
        log = log[log.apply(lambda r: q.lower() in " ".join(str(v) for v in r.values).lower(), axis=1)]
    ui.table(log, {"ts": "When", "user": "User", "action": "Action", "entity": "Entity", "entity_id": "ID", "details": "Details"}, height=520)
    st.download_button(t("Download CSV"), log.to_csv(index=False).encode(), "audit_log.csv", "text/csv")
