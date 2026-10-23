# AI Project & Risk Intelligence Hub

A working multi-tenant SaaS prototype for managing projects, people, multi-project resource allocation, budgets, subcontractors, clients, onboarding/training, access lifecycle (JML), GDPR evidence and an **explainable risk engine** — in English and French.

The **NOVATECH SERVICES** workspace is a demonstration company built from the risk-management case study (85 employees, 230 clients, €12M revenue, Angers / Nantes / Rennes). Company-level facts are case-study data; all people, clients, contracts, figures and signals are **fictional sample records**. Nothing in the demo is a confirmed incident.

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
