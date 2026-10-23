# AI Project & Risk Intelligence Hub

A working multi-tenant SaaS prototype for managing projects, people, multi-project resource allocation, budgets, subcontractors, clients, onboarding/training, access lifecycle (JML), GDPR evidence and an **explainable risk engine** — in English and French.

The **NOVATECH SERVICES** workspace is a demonstration company built from the risk-management case study (85 employees, 230 clients, €12M revenue, Angers / Nantes / Rennes). Company-level facts are case-study data; all people, clients, contracts, figures and signals are **fictional sample records**. Nothing in the demo is a confirmed incident.

**Live demo:** https://ai-project-risk-intelligence.streamlit.app/ — on the sign-in page, use the "Explore the NOVATECH demo as…" buttons (one click per role, demo workspace only), or sign in with a demo account below.

**Best URL for presenting:** https://ai-project-risk-intelligence.streamlit.app/~/+/ (the app without the Streamlit Cloud frame: cleaner, and Back / Forward / Refresh behave exactly like a normal website).

Every module has its own URL (e.g. `/dashboard`, `/allocation`), so the browser's **Back / Forward / Refresh** stay inside the app, and an in-app **← Back** button is shown on every page. You stay signed in after a refresh (8-hour session).

### Employee logins (demo workspace only)

Each of the 85 demo employees has a personal login: **employee1 … employee85** with password **pass@1 … pass@85** (same number). The full list (name, department, open tasks) is on the sign-in page under "Employee logins". When a manager assigns, reassigns or re-dates a task, approves a request or records an absence, the employee sees it immediately in **🔔 Inbox** and **My work**.

### E-mail through Gmail

1. Google Account → **Security** → turn on **2-Step Verification**.
2. Open https://myaccount.google.com/apppasswords → name it *Risk Hub* → **Create** → copy the 16-character password.
3. share.streamlit.io → the app → **⋮ → Settings → Secrets**, add:
   ```toml
   SMTP_USER = "your.address@gmail.com"
   SMTP_PASSWORD = "abcd efgh ijkl mnop"
   EMAIL_TO = "your.address@gmail.com"
   ```
4. Save, wait for the restart, then **Notifications → Send test e-mail**.

## 5-minute presentation walkthrough

1. **Sign-in page** – show *Register a company* (multi-tenant SaaS), then click **Company Administrator** under "Explore the NOVATECH demo".
2. **Getting started** – role-based path; press 🔊 *Listen* to hear the guidance (English or French).
3. **Executive dashboard** – 16 live KPIs and 10 charts; change the *Location* filter to Rennes.
4. **Resource allocation → Overcapacity analysis** – select **Samuel Blanc**: 35 h capacity, P01 20 h + P02 15 h + P05 10 h = 45 h → +10 h warning, affected tasks, delay exposure, recommendations. Find an alternative employee → *Request reassignment* (nothing changes until approved) → *Approvals* tab → Approve. If nobody is available: **Subcontractor support**, **Hiring / extra capacity** or **Deadline change** request (approved by another manager).
4b. Sign in as the employee who received the task (e.g. **employee2 / pass@2**) → the assignment is in **🔔 Inbox** and **My work**.
5. **Risk register** – heat map; open **R2** (case-study risk, unconfirmed hypothesis) and **A-001** (raised automatically from the overcapacity, with its explanation).
6. **Gantt chart** – project P02: milestones, dependencies, overdue/critical tasks; change a due date with a reason → risks recalculated.
7. **Absences** – record an absence → impact on tasks and projects, alternatives, notification log.
8. **Onboarding & training / Access (JML) / GDPR evidence** – the 25 recruits, least-privilege, leaver revocations, evidence matrix.
9. **Switch to Français** in the sidebar, then sign out and sign in as **Employee** or **Subcontractor** to show role-based permissions.
10. **Security notes** – what is implemented vs. what production still needs.

## Known limitations (honest status)

* Risk detection is rule-based; no AI/ML model is trained. `hub/ai_interface.py` is ready for one.
* Gantt dates are edited with a form (the Plotly chart has no drag-and-drop).
* E-mail sending needs the Gmail (or other SMTP) secrets above; NTFY works with the free ntfy.sh server once a topic is set in Company settings. Without configuration, e-mails are logged as "Not sent" — the in-app Inbox always works.
* Forgot-password e-mails require SMTP; otherwise the company administrator issues a one-time temporary password.
* The Joiner-Mover-Leaver module tracks status only; it does not change accounts in external systems.
* Streamlit Community Cloud storage is not persistent: data entered live is lost on restart and the demo is regenerated.
* UI text is fully bilingual; demo records (task titles, client names, R1–R12 details) are mostly in English.

## Run locally (free, no paid services)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. On first start the SQLite database (`data/hub.db`) is created and the NOVATECH demo workspace is generated automatically. If the database is deleted or reset (e.g. Streamlit Cloud restart), it is regenerated on the next start.

### Demo accounts

| Role | E-mail |
|---|---|
| Company Administrator | `admin@novatech-demo.example` |
| Project Manager | `pm@novatech-demo.example` |
| Team Leader | `lead@novatech-demo.example` |
| Employee | `employee@novatech-demo.example` |
| HR / Training Manager | `hr@novatech-demo.example` |
| Risk / Compliance Manager | `risk@novatech-demo.example` |
| Finance Manager | `finance@novatech-demo.example` |
| Subcontractor | `subcontractor@novatech-demo.example` |

All demo accounts use the password set in the `DEMO_PASSWORD` secret / environment variable (fallback for local demos: `NovaTech-Demo-2026`). Change it for any shared deployment.

### First administrator (secure setup)

* **Company administrators** create their own account with **Register a company** on the first screen (password ≥ 10 characters with letters and digits, hashed with PBKDF2-SHA256).
* The **SaaS platform administrator** is never hard-coded. Set `PLATFORM_ADMIN_EMAIL` and `PLATFORM_ADMIN_PASSWORD` in `.streamlit/secrets.toml` (see `secrets.toml.example`) or as environment variables; the account is created at start-up if it does not exist.

## Deploy on Streamlit Community Cloud (free)

1. Push this repository to GitHub.
2. On https://share.streamlit.io → **Create app** → choose the repo, branch `main`, main file `app.py`.
3. In **Advanced settings → Secrets**, paste the content of `.streamlit/secrets.toml.example` with your own values.

Note: Community Cloud storage is ephemeral — data entered during a demo is lost when the app restarts, and the demo workspace is re-created automatically.

## Main modules

| Module | What it does |
|---|---|
| Executive dashboard | 16 KPI cards and 10 interactive charts computed live from the database, with location / project / risk / date filters |
| Resource allocation | Capacity counted once per employee across all projects; employee × project matrix; overcapacity analysis with affected tasks, deadlines, delay exposure and ranked alternative employees; reassignment requires manager approval |
| Risk register | Score = Probability × Impact (1–5); bands 1–7 Low, 8–14 Medium, 15–19 High, 20–25 Critical; case-study risks R1–R12 plus 15 explainable detection rules; evidence status (confirmed fact / hypothesis / warning signal / incident under investigation / resolved) |
| Gantt chart | Tasks, milestones, dependencies, progress, critical and overdue tasks; date editing with mandatory reason and history |
| Projects / Tasks | Portfolio health (never "healthy" while serious risks remain), progress weighting, task history, deadline-change log |
| Absences | Records leave and shows affected tasks, capacity impact and alternatives; recalculates risks; notifies the manager |
| Budget | Approved / planned / actual / forecast / variance, flags overruns; demo figures labelled as estimates |
| Risk areas & signals | Cloud services, remote-work controls, digital tools / shadow IT, incidents & unusual signals with grouping |
| Onboarding & training | 10-step checklist for recent recruits, role-based training, least-privilege suggestions |
| Access lifecycle (JML) | Requests, approvals, activation, reviews, leaver revocation (tracking only; no external IdP integration) |
| Subcontractors / Clients / GDPR evidence | Third-party tracking, contract & SLA portfolio, evidence register for European clients |
| Notifications | NTFY push and SMTP e-mail, every attempt logged |
| Reports / Audit log | Excel and printable HTML management report; full audit trail |

## Rules used by the engines

* **Workload %** = hours allocated across all active projects ÷ effective weekly capacity (capacity minus recorded absence). Bands are configurable (default: < 60 % under-used, ≤ 85 % healthy, ≤ 100 % high, > 100 % overcapacity).
* **Delay exposure** = over-allocated hours ÷ (capacity ÷ 5) = working days per week that cannot be delivered.
* **Project progress** = Σ(estimated hours × completion) ÷ Σ(estimated hours), cancelled tasks excluded.
* **Risk engine**: rule-based, explainable; no machine-learning model is trained. `hub/ai_interface.py` is the integration point for a future ML / LLM advisor.

## Tests

```bash
python tests/smoke.py   # renders every page for every role in English and French (Streamlit AppTest)
```

## Project structure

```
app.py               entry point, authentication gate and navigation
hub/                 database, auth, i18n, engines (allocation, risk), seed data, notifications, UI helpers
views/               one module per page
tests/               automated smoke tests
```
