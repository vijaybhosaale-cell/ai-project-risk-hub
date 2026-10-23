"""Personal 🔔 notification inbox (assignments, approvals, absences, risks...)."""
from __future__ import annotations

import html

import streamlit as st

from hub import db, events, router, ui
from hub.i18n import t

PAGE_LABELS = {"my_work": "My work", "allocation": "Resource allocation", "risks": "Risk register", "tasks": "Tasks",
               "absences": "Absences & availability", "access": "Access lifecycle (JML)", "onboarding": "Onboarding & training",
               "gantt": "Gantt chart", "projects": "Projects"}


def render(ctx: dict) -> None:
    uid = ctx["user"]["id"]
    ui.page_header("inbox", t("Inbox"), t("Your notifications: assignments, approvals, absences and risks"))
    rows = db.query("SELECT * FROM inbox WHERE user_id = ? ORDER BY id DESC LIMIT 200", (uid,))
    unread = sum(1 for r in rows if not r["read_at"])
    c1, c2, c3 = st.columns([2, 1.2, 1.2])
    c1.markdown(f"**{t('{n} unread', n=unread)}** · {t('{n} total', n=len(rows))}")
    show = c2.selectbox(t("Show"), ["Unread first", "Unread only", "All"], format_func=t, label_visibility="collapsed")
    if c3.button("✓ " + t("Mark all as read"), width="stretch", disabled=unread == 0):
        db.execute("UPDATE inbox SET read_at = ? WHERE user_id = ? AND read_at IS NULL", (db.now(), uid))
        st.rerun()
    if show == "Unread only":
        rows = [r for r in rows if not r["read_at"]]
    elif show == "Unread first":
        rows = sorted(rows, key=lambda r: (r["read_at"] is not None, -r["id"]))
    if not rows:
        st.info(t("No notifications."))
        return
    for r in rows[:60]:
        icon = events.ICONS.get(r["kind"], "🔔")
        new = not r["read_at"]
        with st.container(border=True):
            a, b = st.columns([6, 1.4])
            a.markdown(f"{icon} {'🟦 ' if new else ''}**{html.escape(r['title'] or '')}**  \n"
                       f"<span class='subtle'>{html.escape(r['body'] or '')}</span>  \n"
                       f"<span class='subtle'>{r['created_at']}</span>", unsafe_allow_html=True)
            with b:
                if r["page"] and router.page(r["page"]) is not None:
                    router.link(r["page"], t("Open") + " →")
                if new and st.button(t("Mark read"), key=f"rd_{r['id']}"):
                    db.execute("UPDATE inbox SET read_at = ? WHERE id = ? AND user_id = ?", (db.now(), r["id"], uid))
                    st.rerun()
    _ = PAGE_LABELS
