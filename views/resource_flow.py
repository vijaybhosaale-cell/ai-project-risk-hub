"""'Nobody available?' resource options: subcontractor support, hiring / extra capacity request,
deadline-change request. Every option either is a direct decision of an authorised manager or
creates a request that another manager approves. Nothing changes silently."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from hub import audit, db, engine_risk, events, ui
from hub.i18n import t, tf

DIRECT = {"Company Administrator", "Project Manager"}
APPROVERS = {
    "Subcontractor support": {"Company Administrator", "Project Manager"},
    "Hiring / extra capacity": {"Company Administrator"},
    "Deadline change": {"Company Administrator", "Project Manager"},
}
KINDS = list(APPROVERS)


def _who(ctx) -> str:
    return ctx["user"]["name"].split(" (")[0]


def create_request(ctx, kind: str, task: dict | None, **data) -> int:
    cid = ctx["cid"]
    rid = db.t_insert("resource_requests", cid, {
        "kind": kind, "task_id": task["id"] if task else None, "project_id": task["project_id"] if task else data.get("project_id"),
        "employee_id": task.get("assignee_id") if task else None, "subcontractor_id": data.get("subcontractor_id"),
        "skills": data.get("skills"), "hours_per_week": data.get("hours_per_week"), "start_date": data.get("start_date"),
        "end_date": data.get("end_date"), "new_due_date": data.get("new_due_date"), "justification": data.get("justification"),
        "status": "Pending", "requested_by": ctx["user"]["email"], "created_at": db.now()})
    audit.log(cid, ctx["user"]["email"], "resource_request_created", "resource_request", rid, f"{kind}: {data.get('justification', '')}")
    label = f"{task['code']} · {task['title']}" if task else data.get("skills", "")
    events.emit(cid, "resource_request", f"Approval needed — {kind}: {label}",
                f"Requested by {_who(ctx)}. {data.get('justification', '')}", roles=APPROVERS[kind], page="allocation",
                exclude_user=ctx["user"]["id"])
    if kind == "Hiring / extra capacity":
        events.emit(cid, "resource_request", f"Hiring / capacity request raised: {label}", data.get("justification", ""),
                    roles=["HR / Training Manager"], page="allocation", email=False)
    return rid


def assign_subcontractor(ctx, task: dict, sub_id: int, note: str) -> None:
    """Direct decision by an authorised manager: the subcontractor takes over the task."""
    from views.tasks import save_task
    cur = db.t_get("tasks", ctx["cid"], int(task["id"]))
    save_task(ctx, cur, {"subcontractor_id": int(sub_id), "assignee_id": None}, f"Subcontractor support: {note}")


def decide(ctx, req: dict, approve: bool, note: str = "") -> str:
    cid = ctx["cid"]
    if req["requested_by"] == ctx["user"]["email"]:
        return "self"
    if ctx["role"] not in APPROVERS.get(req["kind"], set()):
        return "role"
    db.t_update("resource_requests", cid, int(req["id"]), {"status": "Approved" if approve else "Rejected", "decided_by": ctx["user"]["email"],
                                                            "decided_at": db.now(), "decision_note": note})
    task = db.t_get("tasks", cid, int(req["task_id"])) if req.get("task_id") and not pd.isna(req["task_id"]) else None
    if approve and task:
        from views.tasks import save_task
        if req["kind"] == "Deadline change" and req.get("new_due_date"):
            save_task(ctx, task, {"due_date": req["new_due_date"]}, f"Approved deadline change: {req['justification']}")
        elif req["kind"] == "Subcontractor support" and req.get("subcontractor_id") and not pd.isna(req["subcontractor_id"]):
            save_task(ctx, task, {"subcontractor_id": int(req["subcontractor_id"]), "assignee_id": None},
                      f"Approved subcontractor support: {req['justification']}")
    if approve and req["kind"] == "Hiring / extra capacity":
        events.emit(cid, "approval", "Hiring / extra capacity approved — start recruitment",
                    f"{req['skills'] or ''} · {req['hours_per_week'] or ''} h/week · {req['justification'] or ''}",
                    roles=["HR / Training Manager"], page="allocation")
    requester = events.employee_user_by_email(cid, req["requested_by"])
    if requester:
        events.emit(cid, "approval" if approve else "rejected", f"{req['kind']} {'approved' if approve else 'rejected'}",
                    f"Decided by {_who(ctx)}. {note}".strip(), users=[requester], page="allocation", email=False)
    audit.log(cid, ctx["user"]["email"], "resource_request_" + ("approved" if approve else "rejected"), "resource_request", req["id"], note)
    engine_risk.run(cid)
    return "ok"


def render_options(ctx, task: dict, no_candidates: bool) -> None:
    """Shown under the candidate list for a selected task."""
    cid, role = ctx["cid"], ctx["role"]
    st.markdown("**" + (t("Nobody available? Other options") if no_candidates else t("Other options")) + "**")
    o1, o2, o3 = st.tabs(["🤝 " + t("Subcontractor support"), "🧑‍💼 " + t("Hiring / extra capacity"), "📅 " + t("Deadline change")])
    with o1:
        subs = db.t_rows("subcontractors", cid, order="name")
        if not subs:
            st.info(t("No subcontractor registered yet. Add one in Subcontractors."))
        else:
            with st.form(f"rf_sub_{task['code']}"):
                sid = st.selectbox(t("Subcontractor"), [s["id"] for s in subs],
                                   format_func=lambda i: next(f"{s['name']} · {tf(s['security_assessment'])} · {tf(s['performance'])}" for s in subs if s["id"] == i))
                note = st.text_input(t("Reason"), value=t("No internal capacity available"))
                direct = role in DIRECT
                st.caption(t("As a manager you can assign directly; the employee and the subcontractor are notified.") if direct
                           else t("This creates a request that a project manager approves."))
                if st.form_submit_button(t("Assign to subcontractor") if direct else t("Request subcontractor support"), type="primary"):
                    if direct:
                        assign_subcontractor(ctx, task, sid, note)
                        st.success(t("Task assigned to the subcontractor. History, inbox and risks updated."))
                    else:
                        create_request(ctx, "Subcontractor support", task, subcontractor_id=sid, justification=note)
                        st.success(t("Request sent for approval."))
    with o2:
        with st.form(f"rf_hire_{task['code']}"):
            c1, c2 = st.columns(2)
            skills = c1.text_input(t("Profile / skills needed"), value=task.get("required_skills") or "")
            hrs = c2.number_input(t("Hours per week"), 1.0, 60.0, 20.0)
            sd = c1.date_input(t("From"), date.today() + timedelta(days=7))
            ed = c2.date_input(t("To"), date.today() + timedelta(days=90))
            just = st.text_area(t("Business justification"), value=t("Recurring overcapacity on {c}; no qualified colleague available.", c=task["code"]))
            st.caption(t("Approved by the company administrator; HR is informed to start recruitment or temporary staffing."))
            if st.form_submit_button(t("Submit hiring / capacity request"), type="primary"):
                create_request(ctx, "Hiring / extra capacity", task, skills=skills, hours_per_week=hrs, start_date=str(sd),
                               end_date=str(ed), justification=just)
                st.success(t("Request sent for approval."))
    with o3:
        with st.form(f"rf_dl_{task['code']}"):
            cur = date.fromisoformat(str(task["due_date"])[:10])
            nd = st.date_input(t("Proposed new due date"), cur + timedelta(days=7))
            just = st.text_input(t("Reason") + " *")
            st.caption(t("Current due date: {d}. A different manager must approve; the change is then logged in the task history and the employee is notified.", d=cur))
            if st.form_submit_button(t("Request deadline change"), type="primary"):
                if not just.strip():
                    st.error(t("A reason is required for any date change."))
                elif nd <= cur:
                    st.error(t("The new date must be after the current due date."))
                else:
                    create_request(ctx, "Deadline change", task, new_due_date=str(nd), justification=just)
                    st.success(t("Request sent for approval."))


def render_approvals(ctx) -> None:
    cid, role = ctx["cid"], ctx["role"]
    rq = db.df("""SELECT r.*, t.code, t.title, t.due_date, e.name AS employee, s.name AS subcontractor FROM resource_requests r
                  LEFT JOIN tasks t ON t.id = r.task_id LEFT JOIN employees e ON e.id = r.employee_id
                  LEFT JOIN subcontractors s ON s.id = r.subcontractor_id WHERE r.company_id = ? ORDER BY r.id DESC""", (cid,))
    st.markdown("**" + t("Resource requests (subcontractor, hiring, deadline)") + "**")
    pend = rq[rq["status"] == "Pending"] if not rq.empty else rq
    if pend.empty:
        st.info(t("No pending resource requests."))
    for _, r in pend.iterrows():
        with st.container(border=True):
            detail = {"Deadline change": f"{r['due_date']} → **{r['new_due_date']}**",
                      "Subcontractor support": f"→ **{r['subcontractor'] or '-'}**",
                      "Hiring / extra capacity": f"{r['skills'] or ''} · {r['hours_per_week'] or ''} h/{t('week')} · {r['start_date']} → {r['end_date']}"}[r["kind"]]
            st.markdown(f"🧩 **{t(r['kind'])}** · {r['code'] or ''} {r['title'] or ''} — {detail}  \n"
                        f"<span class='subtle'>{t('Reason')}: {r['justification'] or '-'} · {t('Requested by')} {r['requested_by']} · {r['created_at']}</span>",
                        unsafe_allow_html=True)
            if role in APPROVERS.get(r["kind"], set()):
                b1, b2, _ = st.columns([1, 1, 4])
                if b1.button("✅ " + t("Approve"), key=f"rra_{r['id']}"):
                    res = decide(ctx, r.to_dict(), True)
                    if res == "self":
                        st.error(t("You cannot approve your own request (segregation of duties)."))
                    else:
                        st.rerun()
                if b2.button("✖ " + t("Reject"), key=f"rrr_{r['id']}"):
                    res = decide(ctx, r.to_dict(), False)
                    if res == "self":
                        st.error(t("You cannot approve your own request (segregation of duties)."))
                    else:
                        st.rerun()
            else:
                st.caption(t("Waiting for: {r}", r=", ".join(t(x) for x in APPROVERS[r["kind"]])))
    if not rq.empty:
        ui.table(rq, {"kind": "Type", "code": "Task", "justification": "Reason", "status": "Status", "requested_by": "Requested by",
                      "decided_by": "Decided by", "decided_at": "Decided at"}, translate_values=("kind", "status"))
