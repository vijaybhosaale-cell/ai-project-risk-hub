"""Role-based welcome page with a guided path through the platform."""
from __future__ import annotations

import html
import json

import streamlit as st

from hub import ui
from hub.i18n import lang, t

PATHS = {
    "Company Administrator": [
        ("dashboard", "Check the company's health at a glance: workload, projects, budget and risks."),
        ("allocation", "Find employees allocated above their capacity across several projects."),
        ("risks", "Review the risk register: case-study risks R1-R12 plus risks raised from live data."),
        ("users", "Create accounts for your managers and employees and give them roles."),
        ("settings", "Run or edit the setup wizard, thresholds and notifications."),
    ],
    "Project Manager": [
        ("dashboard", "See projects at risk, overdue tasks and upcoming deadlines."),
        ("allocation", "Check who is overloaded and approve or request reassignments."),
        ("gantt", "Review the timeline; move task dates with a logged reason."),
        ("tasks", "Update task status, priorities and deadlines."),
        ("risks", "Acknowledge and assign the risks on your projects."),
    ],
    "Team Leader": [
        ("my_work", "Update progress on your own tasks."),
        ("tasks", "Follow your team's tasks and flag blocked work."),
        ("absences", "Record a team member's absence and see the impact."),
        ("allocation", "Check your team's workload."),
    ],
    "Employee": [
        ("my_work", "See your tasks and update their progress; check your training."),
        ("gantt", "See where your tasks sit in the project timeline."),
    ],
    "HR / Training Manager": [
        ("onboarding", "Follow the 25 recent recruits: checklist, training and access."),
        ("employees", "Maintain employee records, capacity and status."),
        ("absences", "Record leave and see which projects are affected."),
        ("access", "Track joiner / mover / leaver access requests."),
    ],
    "Risk / Compliance Manager": [
        ("risks", "Review, assign and track remediation of risks."),
        ("risk_areas", "Record cloud, remote-work and tool evidence; analyse unusual signals."),
        ("gdpr", "Maintain the GDPR evidence register for European clients."),
        ("access", "Run access reviews and check leaver revocations."),
        ("audit", "Inspect the audit trail."),
    ],
    "Finance Manager": [
        ("budget", "Compare approved, actual and forecast spend."),
        ("projects", "See project health including budget pressure."),
        ("clients", "Review contracts, renewals and recurring revenue."),
        ("reports", "Download the management report."),
    ],
    "Subcontractor": [
        ("my_work", "See the tasks and deadlines assigned to your company and update progress."),
    ],
}
LABELS = {"dashboard": "Executive dashboard", "allocation": "Resource allocation", "risks": "Risk register",
          "users": "Users & roles", "settings": "Company settings & setup", "gantt": "Gantt chart", "tasks": "Tasks",
          "my_work": "My work", "absences": "Absences & availability", "onboarding": "Onboarding & training",
          "employees": "Employees", "access": "Access lifecycle (JML)", "risk_areas": "Risk areas & signals",
          "gdpr": "GDPR evidence", "audit": "Audit log", "budget": "Budget & finance", "projects": "Projects",
          "clients": "Clients & contracts", "reports": "Management reports"}


def _go(page: str) -> None:
    st.session_state["nav"] = page


def render(ctx: dict) -> None:
    user, company, role = ctx["user"], ctx["company"], ctx["role"]
    st.title(t("Welcome, {name}", name=user["name"].split(" (")[0]))
    st.markdown(f'<div class="subtle">{html.escape(t("You are signed in as"))} <b>{html.escape(t(role))}</b>'
                f' · {html.escape(company["name"] if company else "")}</div>', unsafe_allow_html=True)
    st.write("")
    c1, c2 = st.columns([1.5, 1])
    with c1:
        st.subheader("🧭 " + t("Your suggested path"))
        steps = PATHS.get(role, [])
        spoken = []
        for i, (page, desc) in enumerate(steps, 1):
            a, b = st.columns([4, 1.3])
            a.markdown(f'<div class="step"><div class="n">{i}</div><div><b>{html.escape(t(LABELS[page]))}</b><br>'
                       f'<span class="subtle">{html.escape(t(desc))}</span></div></div>', unsafe_allow_html=True)
            b.button(t("Open") + " →", key=f"gs_{page}", on_click=_go, args=(page,), width="stretch")
            spoken.append(f"{i}. {t(LABELS[page])}: {t(desc)}")
        st.write("")
        intro = t("Welcome to the AI Project and Risk Intelligence Hub. Here is your suggested path.")
        ui.listen_button(intro + " " + " ".join(spoken) + " " + t("Every page also has a How to use this page box at the top."), "gs")
        st.caption(t("Tip: every page has a '❓ How to use this page' box with a 🔊 Listen button. Use the left menu to move between modules; the language switch is in the sidebar."))
    with c2:
        st.subheader("ℹ️ " + t("About this workspace"))
        if company and company.get("is_demo"):
            facts = json.loads(company.get("case_facts") or "{}")
            st.markdown(
                f"""<div class="card"><h4>NOVATECH SERVICES — {html.escape(t('case-study data'))}</h4>
                <div class="subtle">{html.escape(t(facts.get('source', '')))}</div><ul style="margin-top:8px">
                <li>{t('Employees')}: <b>{facts.get('employees')}</b></li>
                <li>{t('Active clients')}: <b>{facts.get('active_clients')}</b></li>
                <li>{t('Annual revenue')}: <b>€12M</b> · {t('growth')} <b>+35%</b> {t('over two years')}</li>
                <li>{t('Recruited over two years')}: <b>25</b></li>
                <li>{t('Locations')}: <b>Angers, Nantes, Rennes</b></li>
                <li>{t('Remote-eligible employees')}: <b>40%</b></li>
                <li>{t('European clients share of recurring revenue')}: <b>70%</b></li>
                </ul><div class="subtle">{html.escape(t('Strong cloud dependence, new digital tools, subcontractors on client projects, and more small incidents and unusual signals reported by management.'))}</div></div>""",
                unsafe_allow_html=True)
        st.markdown(f"""<div class="card"><h4>🛡️ {html.escape(t('How risk scoring works'))}</h4>
            <div class="subtle">{html.escape(t('Score = Probability × Impact (1–5 each). 1–7 Low · 8–14 Medium · 15–19 High · 20–25 Critical. Every risk shows why it was raised. The engine is rule-based and explainable; no AI model has been trained.'))}</div></div>""",
                    unsafe_allow_html=True)
    _ = lang
