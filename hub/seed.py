"""NOVATECH SERVICES demonstration workspace.

All people, clients, contracts, figures and signals below are FICTIONAL demonstration
records generated deterministically. Company-level facts come from the case study and
are labelled as such. Dates are generated relative to today so the demo always looks
current, and the workspace is re-created automatically when the database is empty.
"""
from __future__ import annotations

import json
import os
import random
from datetime import date, timedelta

from . import auth, db, engine_risk

DEMO_DOMAIN = "novatech-demo.example"
DEFAULT_DEMO_PASSWORD = "NovaTech-Demo-2026"

CASE_FACTS = {
    "employees": 85, "active_clients": 230, "annual_revenue_eur": 12_000_000,
    "revenue_growth_2y_pct": 35, "recruits_2y": 25, "locations": ["Angers", "Nantes", "Rennes"],
    "remote_pct": 40, "eu_recurring_revenue_pct": 70,
    "notes": [
        "Strong dependence on cloud infrastructure",
        "Several new digital tools have been deployed",
        "Subcontractors participate in client projects",
        "Management has reported more small incidents and unusual signals",
    ],
    "source": "Case study (NOVATECH SERVICES risk-management exercise) - not independently verified",
}

FIRST = ["Camille", "Lucas", "Léa", "Hugo", "Chloé", "Louis", "Manon", "Jules", "Inès", "Gabriel", "Sarah", "Arthur",
         "Emma", "Nathan", "Jade", "Tom", "Lina", "Théo", "Zoé", "Raphaël", "Anaïs", "Maxime", "Clara", "Antoine",
         "Julie", "Paul", "Margaux", "Victor", "Elise", "Romain", "Lucie", "Samuel", "Noémie", "Yanis", "Pauline", "Adam",
         "Océane", "Mathis", "Amira", "Karim"]
LAST = ["Martin", "Bernard", "Durand", "Petit", "Leroy", "Moreau", "Simon", "Laurent", "Lefebvre", "Michel", "Garcia",
        "David", "Bertrand", "Roux", "Vincent", "Fournier", "Morel", "Girard", "André", "Mercier", "Dupont", "Lambert",
        "Bonnet", "François", "Martinez", "Legrand", "Garnier", "Faure", "Rousseau", "Blanc", "Guérin", "Muller", "Henry",
        "Roussel", "Nicolas", "Perrin", "Morin", "Mathieu", "Clément", "Gauthier"]

DEPTS = [  # (department, count, job role, skills)
    ("Management", 3, "Director", "Leadership,Strategy,Client relations"),
    ("Project Management", 8, "Project Manager", "Project management,Planning,Client relations,Risk management"),
    ("Software Engineering", 22, "Software Engineer", "Python,JavaScript,Java,APIs,React,Testing"),
    ("Cloud & Infrastructure", 10, "Cloud Engineer", "AWS,Azure,Kubernetes,Networking,Linux,Backup"),
    ("Data & BI", 8, "Data Engineer", "SQL,Python,Power BI,Data modelling,ETL"),
    ("Cybersecurity", 5, "Security Analyst", "SIEM,Vulnerability management,IAM,Incident response,GDPR"),
    ("Service Desk", 10, "Support Engineer", "ITSM,Microsoft 365,Networking,Customer support"),
    ("Sales & Accounts", 8, "Account Manager", "Sales,Client relations,Contracts"),
    ("HR & Training", 4, "HR Officer", "HR,Training,Onboarding"),
    ("Finance & Procurement", 4, "Finance Officer", "Finance,Procurement,Budgeting"),
    ("Quality & Compliance", 3, "Compliance Officer", "GDPR,ISO 27001,Audit,Risk management"),
]
SKILL_POOL = {
    "Software Engineering": ["Python", "JavaScript", "Java", "APIs", "React", "Testing", "Mobile", "DevOps"],
    "Cloud & Infrastructure": ["AWS", "Azure", "Kubernetes", "Networking", "Linux", "Backup", "Terraform"],
    "Data & BI": ["SQL", "Python", "Power BI", "Data modelling", "ETL"],
}

R_CASE = [  # code, title EN, title FR, category, case category, P, I, cause, event, consequences, evidence, controls, owner
    ("R1", "Cloud service outage or provider disruption", "Panne d'un service cloud ou défaillance du fournisseur",
     "Technology / continuity", "1. Cloud infrastructure dependency", 3, 5,
     "Concentration of critical services in Cloud platforms; insufficient redundancy or recovery testing.",
     "A Cloud provider outage, account lockout, network failure or major configuration error makes critical systems unavailable.",
     "Staff cannot deliver services; client deadlines missed; revenue and contractual service levels affected.",
     "Provider SLA and outage history; service dependency map; backup restore and disaster-recovery test results; RTO/RPO definitions.",
     "Map critical services and dependencies; define business-approved RTO/RPO; test restores and disaster recovery; use multi-zone/redundant design where justified; maintain an outage communication plan.",
     "IT / Operations"),
    ("R2", "Compromised employee or administrator account", "Compromission d'un compte salarié ou administrateur",
     "Cybersecurity / identity", "2. Remote working", 4, 5,
     "Phishing, reused passwords, weak authentication, excessive privileges or remote-access gaps.",
     "An attacker gains access to a staff account, then accesses systems or client information.",
     "Data exposure, ransomware, service disruption, incident-response costs and loss of client trust.",
     "MFA coverage; privileged-account list; sign-in anomalies; phishing reports; endpoint alerts; access review records.",
     "Enforce MFA, especially for administrators and remote access; least privilege; separate admin accounts; phishing-resistant authentication for privileged users where feasible; EDR and alerting; revoke sessions and credentials promptly after suspected compromise.",
     "IT / Security"),
    ("R3", "Cloud or SaaS misconfiguration / shadow IT", "Mauvaise configuration cloud/SaaS ou shadow IT",
     "Cybersecurity / change management", "4. New digital tools", 4, 4,
     "Rapid deployment of new tools without consistent ownership, security review or configuration standards.",
     "A storage location, sharing link, API or SaaS setting exposes data or permits unauthorized access.",
     "Client data leakage, downtime, contractual issues, investigation costs and potential regulatory consequences.",
     "Approved-tool inventory; cloud configuration findings; public-sharing settings; API keys and secrets handling; change tickets.",
     "Maintain a central tool and asset inventory; require security review before adoption; use secure configuration baselines and automated posture checks; restrict public sharing; protect secrets; review changes and log administrative actions.",
     "IT / Tool owners"),
    ("R4", "Employee error or inadequate security awareness", "Erreur humaine ou sensibilisation sécurité insuffisante",
     "Human / operational", "3. New employees", 4, 4,
     "Fast recruitment, inconsistent onboarding, workload pressure or unclear procedures.",
     "An employee sends information to the wrong recipient, approves a fraudulent request, mishandles data or changes a system incorrectly.",
     "Data loss, financial loss, service interruption, customer complaints or additional recovery work.",
     "Training completion; near-miss reports; help-desk tickets; data-handling procedures; incident trends by type.",
     "Provide role-based onboarding and short recurring awareness sessions; use clear data-classification and sharing rules; verify payment/account-change requests through a second channel; create simple incident-reporting procedures; review repeat incident patterns without blaming staff.",
     "HR / Managers / IT"),
    ("R5", "Access rights not updated when staff join, move or leave", "Droits d'accès non mis à jour (arrivées, mobilités, départs)",
     "Human / identity", "3. New employees", 3, 5,
     "Manual onboarding/offboarding, unclear ownership or lack of periodic access reviews.",
     "A former employee retains access, or a new/moved employee has excessive permissions.",
     "Unauthorized access, accidental changes, data exposure or inability to attribute actions reliably.",
     "HR-to-IT leaver notifications; account-disable timestamps; privileged-access list; periodic access review records.",
     "Implement a documented Joiner-Mover-Leaver process; link HR notifications to IT tickets; disable access promptly at departure; recover devices and tokens; review access quarterly and after role changes; use centralized identity management where practical.",
     "HR / IT"),
    ("R6", "Subcontractor security or delivery failure", "Défaillance sécurité ou livraison d'un sous-traitant",
     "Third party / supplier", "5. Subcontractors", 3, 5,
     "Subcontractors have access to client systems or data, but due diligence, contracts or monitoring may be incomplete.",
     "A subcontractor suffers a breach, misses a delivery, uses an insecure device or fails to meet agreed service requirements.",
     "Client data or services affected, project delays, contractual disputes, remediation costs and reputational damage.",
     "Supplier register and criticality; security assessments; contract clauses; access logs; incident notifications; service reviews.",
     "Classify suppliers by criticality; perform risk-based due diligence; include confidentiality, security, incident-notification, audit and exit clauses; grant time-limited least-privilege access; monitor service performance; maintain an alternative or exit plan for critical suppliers.",
     "Procurement / Project managers / IT"),
    ("R7", "Personal-data protection or GDPR non-compliance", "Non-conformité RGPD / protection des données personnelles",
     "Legal / compliance", "6. European clients & recurring revenue", 3, 5,
     "Unclear data ownership, excessive collection/retention, weak vendor controls or incomplete records of processing.",
     "Personal data is processed, shared, retained or disclosed without appropriate safeguards or a valid documented basis.",
     "Regulatory investigation, required remediation, possible notification obligations, contractual consequences and loss of trust.",
     "Data inventory; records of processing; retention schedules; data-processing agreements; access controls; incident and request logs.",
     "Map personal data and processing purposes; minimize collection; set retention and deletion rules; review processor contracts and international transfers where relevant; restrict access; document incident escalation and assess notification duties with the privacy lead/legal adviser.",
     "Management / Privacy lead / Legal"),
    ("R8", "Ransomware or destructive malware", "Rançongiciel ou logiciel malveillant destructeur",
     "Cybersecurity / continuity", "7. Incidents & unusual signals", 3, 5,
     "Phishing, vulnerable endpoints, unpatched systems, exposed remote access or compromised supplier connections.",
     "Malware encrypts or destroys company data and disrupts business systems.",
     "Operations stop, recovery costs rise, client delivery is interrupted and data confidentiality may also be affected.",
     "EDR coverage and alerts; patch status; backup isolation; restore tests; vulnerability scan results; incident response exercises.",
     "Maintain supported and patched systems; deploy centrally managed endpoint protection; segment critical systems; restrict admin privileges; maintain immutable/offline backups; test restoration; prepare an incident-response playbook and exercise it.",
     "IT / Security / Operations"),
    ("R9", "Service quality or project delivery deteriorates during growth", "Dégradation de la qualité de service ou des livraisons pendant la croissance",
     "Operational / client", "Project delivery & capacity", 4, 4,
     "More clients, staff and tools without matching processes, capacity planning or clear ownership.",
     "Projects miss deadlines, service levels are breached, or defects and support requests accumulate.",
     "Rework, penalties where contractually applicable, reduced margins, client dissatisfaction and contract loss.",
     "SLA performance; ticket backlog; project milestones; defect/rework trends; resource utilization; client complaints.",
     "Define service owners and escalation paths; track delivery and support KPIs; use change management and release testing; perform capacity planning; review recurring issues and lessons learned with project teams.",
     "Operations / Project managers"),
    ("R10", "Business continuity and backup recovery failure", "Échec de la continuité d'activité et de la restauration des sauvegardes",
     "Continuity / resilience", "1. Cloud infrastructure dependency", 3, 5,
     "Backups may not cover all critical systems, may be accessible to attackers, or may not have been restore-tested.",
     "After an outage, cyber incident or accidental deletion, the company cannot restore systems and data within required times.",
     "Extended interruption, lost work, client service failure and greater recovery cost.",
     "Backup scope and logs; restore test reports; RTO/RPO; continuity plans; named recovery owners.",
     "Perform a business impact analysis; define critical services and recovery targets; maintain protected backups; test restores regularly; document recovery dependencies and contacts; run tabletop and technical recovery exercises.",
     "IT / Business owners"),
    ("R11", "Fraudulent invoice, payment or supplier bank-change request", "Fraude à la facture, au paiement ou au changement de RIB fournisseur",
     "Financial / human", "Financial", 3, 4,
     "Rapid growth, high transaction volume, email impersonation or weak segregation of duties.",
     "An employee pays a fake invoice or sends funds to a fraudulent account.",
     "Direct financial loss, investigation effort and possible supplier relationship disruption.",
     "Payment approval workflow; supplier bank-change logs; unusual payment records; finance incident reports.",
     "Verify bank-detail changes using a known trusted phone number; require dual approval above defined thresholds; separate supplier setup from payment approval; use callback procedures; train finance and project staff on business email compromise.",
     "Finance / Procurement"),
    ("R12", "Reputation and client-confidence damage", "Atteinte à la réputation et à la confiance des clients",
     "Reputation / commercial", "Reputation", 3, 4,
     "A security incident, repeated outages, missed commitments or slow communication with clients.",
     "Clients lose confidence, escalate complaints, decline renewals or share negative feedback.",
     "Reduced recurring revenue, more difficult sales, higher customer-acquisition costs and weakened market position.",
     "Renewal rates; complaint and escalation trends; client satisfaction; incident communications; lost-client reasons.",
     "Resolve root causes rather than only symptoms; communicate incidents promptly and transparently; track client satisfaction and escalations; review commitments before signing; involve account managers in recovery plans.",
     "Management / Account managers"),
]

ONBOARDING_STEPS = [
    "Employee profile created", "Manager assigned", "Required documents recorded",
    "Role-specific training assigned", "Security awareness training assigned", "Training completion reviewed",
    "Access request approved", "Required access activated", "Assigned to an appropriate project", "Onboarding completed",
]
EVIDENCE_TYPES = [
    "Data-processing agreement (DPA)", "Data map / record of processing", "Contract data-protection clauses",
    "Incident notification procedure", "Sub-processor list / transfer assessment", "Retention & deletion rules",
]


def demo_password() -> str:
    try:
        import streamlit as st
        if "DEMO_PASSWORD" in st.secrets:
            return str(st.secrets["DEMO_PASSWORD"])
    except Exception:
        pass
    return os.environ.get("DEMO_PASSWORD", DEFAULT_DEMO_PASSWORD)


def quick_demo_enabled() -> bool:
    """One-click access to the fictional demo workspace (presentation convenience). Disable with DEMO_QUICK_LOGIN=false."""
    val = ""
    try:
        import streamlit as st
        if "DEMO_QUICK_LOGIN" in st.secrets:
            val = str(st.secrets["DEMO_QUICK_LOGIN"])
    except Exception:
        pass
    val = val or os.environ.get("DEMO_QUICK_LOGIN", "true")
    return val.strip().lower() not in ("false", "0", "no", "off")


def _iso(d: date) -> str:
    return d.isoformat()


def seed_demo() -> int:
    from . import notify
    notify._MUTED["on"] = True  # no e-mails while generating the demo
    try:
        return _seed_demo()
    finally:
        notify._MUTED["on"] = False


def _seed_demo() -> int:
    rnd = random.Random(2026)
    today = date.today()
    D = lambda days: _iso(today + timedelta(days=days))  # noqa: E731

    cid = db.execute(
        """INSERT INTO companies (name, email, industry, country, timezone, language, currency, declared_employees,
           declared_projects, declared_locations, objectives, reporting_prefs, case_facts, setup_complete, is_demo, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,1,?)""",
        ("NOVATECH SERVICES", f"contact@{DEMO_DOMAIN}", "Digital services for businesses and local authorities",
         "France", "Europe/Paris", "en", "EUR", 85, 10, "Angers, Nantes, Rennes",
         "Sustain growth (+35% in two years) while keeping delivery quality, security and GDPR compliance under control.",
         "Weekly management report; monthly risk review", json.dumps(CASE_FACTS), db.now()))

    # Locations -----------------------------------------------------------------
    loc_ids = {}
    for name, n, addr in [("Angers", 34, "Angers (demo address)"), ("Nantes", 29, "Nantes (demo address)"), ("Rennes", 22, "Rennes (demo address)")]:
        loc_ids[name] = db.t_insert("locations", cid, {"name": name, "address": addr, "manager": "", "employee_count": n,
                                                       "active_projects": 0, "timezone": "Europe/Paris"})
    loc_cycle = ["Angers"] * 34 + ["Nantes"] * 29 + ["Rennes"] * 22
    rnd.shuffle(loc_cycle)

    # Employees -----------------------------------------------------------------
    names, used = [], set()
    while len(names) < 88:
        n = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
        if n not in used:
            used.add(n)
            names.append(n)
    emp_ids, by_dept = [], {}
    new_hire_slots = set(rnd.sample(range(85), 25))
    remote_slots = set(rnd.sample(range(85), 34))  # 40% remote-eligible
    k = 0
    for dept, count, role, skills in DEPTS:
        for j in range(count):
            nm = names[k]
            if dept in SKILL_POOL:
                sk = ",".join(rnd.sample(SKILL_POOL[dept], 3))
            else:
                sk = skills
            cap = 35.0
            if k % 11 == 5:
                cap = 28.0
            elif k % 17 == 3:
                cap = 39.0
            new = k in new_hire_slots
            join = today - timedelta(days=rnd.randint(20, 720)) if new else today - timedelta(days=rnd.randint(800, 3600))
            remote = k in remote_slots
            mfa = "Not recorded"
            if remote:
                mfa = "Verified" if rnd.random() < 0.65 else "Not recorded"
            rid = db.t_insert("employees", cid, {
                "emp_code": f"NT-{k + 1:03d}", "name": nm,
                "email": nm.lower().replace(" ", ".").translate(str.maketrans("éèëêïîôöàâçü", "eeeeiiooaacu")) + f"@{DEMO_DOMAIN}",
                "phone": f"+33 2 00 00 {k + 1:02d} {k % 97:02d}", "location_id": loc_ids[loc_cycle[k]],
                "department": dept, "job_role": ("Senior " if j == 0 and count > 4 else "") + role, "skills": sk,
                "weekly_capacity": cap, "working_hours": "Mon-Fri 09:00-17:00" if cap >= 35 else "Mon-Thu (80%)",
                "employment_status": "Active", "remote_eligible": int(remote), "join_date": _iso(join),
                "is_new_hire": int(new), "mfa_status": mfa,
                "device_status": "Compliant" if rnd.random() < 0.7 else "Not recorded",
                "vpn_status": "Verified" if remote and rnd.random() < 0.7 else "Not recorded",
                "edr_status": "Verified" if rnd.random() < 0.75 else "Not recorded", "active": 1})
            emp_ids.append(rid)
            by_dept.setdefault(dept, []).append(rid)
            k += 1
    # three former employees (leavers) for the Joiner-Mover-Leaver demo
    leavers = []
    for i in range(3):
        nm = names[85 + i]
        leavers.append(db.t_insert("employees", cid, {
            "emp_code": f"NT-L{i + 1:02d}", "name": nm, "email": nm.lower().replace(" ", ".") + f"@{DEMO_DOMAIN}",
            "location_id": loc_ids[["Angers", "Nantes", "Rennes"][i]], "department": ["Software Engineering", "Service Desk", "Sales & Accounts"][i],
            "job_role": "Former employee", "skills": "", "weekly_capacity": 35, "employment_status": "Left",
            "join_date": D(-900), "leave_date": D(-(10 + i * 9)), "active": 0}))
    # managers: department head = first employee of the department
    for dept, ids in by_dept.items():
        head = ids[0]
        for e in ids[1:]:
            db.t_update("employees", cid, e, {"manager_id": head})
    for name, lid in loc_ids.items():
        mgr = db.one("SELECT name FROM employees WHERE company_id=? AND location_id=? AND department IN ('Management','Project Management') LIMIT 1", (cid, lid))
        db.t_update("locations", cid, lid, {"manager": mgr["name"] if mgr else ""})

    # Clients -------------------------------------------------------------------
    client_specs = [
        ("Communauté Urbaine Loire-Sud (demo)", "France", 1), ("Atlantis Logistics SAS (demo)", "France", 1),
        ("Breizh Agro Coop (demo)", "France", 1), ("EuroRetail GmbH (demo)", "Germany", 1),
        ("Région Maine Transports (demo)", "France", 1), ("Banca Nord Italia (demo)", "Italy", 1),
        ("Maison Artisane SARL (demo)", "France", 1), ("Clinique du Val (demo)", "France", 1),
        ("Commune de Saint-Lys (demo)", "France", 1), ("Nordic Travel AB (demo)", "Sweden", 1),
        ("Helvetia Instruments SA (demo)", "Switzerland", 0), ("Thames Advisory Ltd (demo)", "United Kingdom", 0),
        ("Iberia Foods SL (demo)", "Spain", 1), ("Benelux Parts BV (demo)", "Netherlands", 1),
        ("Ouest Habitat (demo)", "France", 1), ("Lyon Médias (demo)", "France", 1), ("Polska Soft (demo)", "Poland", 1),
        ("Maple Analytics Inc (demo)", "Canada", 0), ("Vienna Care GmbH (demo)", "Austria", 1),
        ("Atelier Numérique 49 (demo)", "France", 1),
    ]
    client_ids = []
    for i, (nm, country, eu) in enumerate(client_specs):
        start = today - timedelta(days=rnd.randint(200, 1100))
        end = start + timedelta(days=365 * rnd.choice([2, 3]))
        if end < today:
            end = today + timedelta(days=rnd.randint(40, 500))
        renewal = end - timedelta(days=60)
        if i in (1, 9):
            renewal = today + timedelta(days=rnd.randint(10, 25))
        client_ids.append(db.t_insert("clients", cid, {
            "name": nm, "contact": f"{rnd.choice(FIRST)} {rnd.choice(LAST)} (demo contact)",
            "email": f"contact{i + 1}@client-demo.example", "country": country, "is_eu": eu, "recurring": int(i % 4 != 3),
            "contract_start": _iso(start), "contract_end": _iso(end), "renewal_date": _iso(renewal),
            "contract_value": float(rnd.randrange(40, 600) * 1000),
            "sla": rnd.choice(["Gold: P1 response 1h, 99.9% availability", "Silver: P1 response 4h, 99.5%", "Standard: next business day"]),
            "sla_response_hours": rnd.choice([1, 4, 8]),
            "deliverables": "Monthly service report; quarterly review", "dp_obligations": "GDPR Art. 28 processor obligations" if eu else "Contractual confidentiality",
            "incident_obligations": "Notify client without undue delay (contract: within 24h)" if eu else "Notify within 72h"}))

    # Subcontractors ---------------------------------------------------------------
    # Projects -------------------------------------------------------------------
    pms = by_dept["Project Management"]
    proj_specs = [  # code, name, client idx, location, start offset, end offset, budget, priority, spend factor, status
        ("P01", "Citizen services portal", 0, "Angers", -150, 60, 320000, "High", 0.62, "Active"),
        ("P02", "Cloud migration - phase 2", 1, "Nantes", -120, 25, 410000, "Critical", 0.93, "Active"),
        ("P03", "ERP integration", 2, "Rennes", -90, 120, 260000, "Medium", 0.41, "Active"),
        ("P04", "Data platform & BI", 3, "Nantes", -60, 150, 380000, "High", 0.30, "Active"),
        ("P05", "Mobile field app", 4, "Angers", -100, 20, 190000, "High", 1.04, "Active"),
        ("P06", "Managed security monitoring (SOC)", 5, "Rennes", -200, 165, 450000, "Critical", 0.55, "Active"),
        ("P07", "E-commerce replatform", 6, "Nantes", -45, 135, 230000, "Medium", 0.22, "Active"),
        ("P08", "Patient-records workflow", 7, "Angers", -30, 180, 280000, "High", 0.12, "Active"),
        ("P09", "Network modernisation", 8, "Rennes", -75, 75, 150000, "Medium", 0.50, "On Hold"),
        ("P10", "Support automation & chatbot", 9, "Angers", -20, 200, 170000, "Low", 0.08, "Active"),
        ("P11", "Website accessibility audit", 15, "Nantes", -210, -20, 60000, "Low", 0.97, "Completed"),
    ]
    proj = {}
    for i, (code, nm, ci, loc, so, eo, bud, prio, sf, status) in enumerate(proj_specs):
        actual = round(bud * sf, -2)
        elapsed = max(min((-so) / max(eo - so, 1), 1), 0.01)
        forecast = round(actual / elapsed if status != "Completed" else actual, -2)
        proj[code] = db.t_insert("projects", cid, {
            "code": code, "name": nm, "description": f"{nm} for {client_specs[ci][0]} (fictional demonstration project).",
            "client_id": client_ids[ci], "manager_id": pms[i % len(pms)], "location_id": loc_ids[loc],
            "start_date": D(so), "end_date": D(eo), "budget": bud, "planned_spend": round(bud * elapsed, -2),
            "actual_spend": actual, "forecast_spend": forecast, "estimated_effort": round(bud / 75),
            "status": status, "priority": prio, "sla_ref": f"SLA-{client_specs[ci][0][:3].upper()}-{i + 1:02d}",
            "archived": 0, "financials_are_estimates": 1})
    proj["INT"] = db.t_insert("projects", cid, {
        "code": "INT", "name": "Internal operations & service desk (BAU)", "description": "Recurring internal work and client support (not a client project).",
        "client_id": None, "manager_id": by_dept["Management"][1], "location_id": loc_ids["Angers"], "start_date": D(-365),
        "end_date": D(365), "budget": 0, "status": "Active", "priority": "Medium", "archived": 0})
    for name, lid in loc_ids.items():
        n = db.scalar("SELECT COUNT(*) FROM projects WHERE company_id=? AND location_id=? AND status='Active'", (cid, lid))
        db.t_update("locations", cid, lid, {"active_projects": n})

    subs_specs = [
        ("CloudOps Partners (demo)", "CloudOps Partners SAS", "P02", "Admin access to client cloud tenant", "Not started", "On track"),
        ("FieldDev Mobile (demo)", "FieldDev Mobile SARL", "P05", "Test data only", "Completed", "Delayed"),
        ("DataBridge Consulting (demo)", "DataBridge Consulting", "P04", "Read access to data warehouse", "In progress", "On track"),
        ("SecureLine Audit (demo)", "SecureLine Audit", "P06", "Log data (pseudonymised)", "Completed", "On track"),
        ("PixelForge Studio (demo)", "PixelForge Studio", "P07", "None", "Not required", "On track"),
    ]
    sub_ids = {}
    for i, (nm, comp, pcode, access, assess, perf) in enumerate(subs_specs):
        p = db.t_get("projects", cid, proj[pcode])
        sub_ids[pcode] = db.t_insert("subcontractors", cid, {
            "name": nm, "company_name": comp, "contact": f"{rnd.choice(FIRST)} {rnd.choice(LAST)} (demo)",
            "email": f"pm{i + 1}@subcontractor-demo.example", "phone": "+33 1 00 00 00 0" + str(i),
            "contract_start": p["start_date"], "contract_end": p["end_date"], "client_id": p["client_id"], "project_id": p["id"],
            "estimated_cost": float(rnd.randrange(15, 90) * 1000), "security_assessment": assess,
            "obligations": "Confidentiality; security clauses; incident notification within 24h; audit right" if i != 0 else "Confidentiality only (security annex not yet signed)",
            "data_access": access, "access_expiry": D(rnd.randint(-5, 90)) if i != 0 else "",
            "incident_notification": "Within 24h to NovaTech PM and security contact",
            "performance": perf, "delivery_concern": "Two deliverables slipped by more than one week" if perf == "Delayed" else "",
            "security_concern": "Security assessment not started although admin access is granted" if i == 0 else "",
            "corrective_action": ""})

    # Allocations ------------------------------------------------------------------
    team_plan = {  # project: [(dept, n, hours)]
        "P01": [("Software Engineering", 5, (10, 20)), ("Data & BI", 1, (8, 10)), ("Cybersecurity", 1, (5, 8)), ("Service Desk", 1, (5, 8))],
        "P02": [("Cloud & Infrastructure", 5, (15, 22)), ("Software Engineering", 2, (10, 15)), ("Cybersecurity", 1, (8, 10))],
        "P03": [("Software Engineering", 4, (12, 18)), ("Data & BI", 2, (10, 15))],
        "P04": [("Data & BI", 4, (15, 20)), ("Cloud & Infrastructure", 1, (8, 12)), ("Software Engineering", 1, (8, 10))],
        "P05": [("Software Engineering", 4, (12, 20)), ("Service Desk", 1, (5, 8))],
        "P06": [("Cybersecurity", 4, (12, 20)), ("Cloud & Infrastructure", 2, (8, 12)), ("Service Desk", 2, (8, 12))],
        "P07": [("Software Engineering", 4, (10, 18)), ("Data & BI", 1, (6, 8))],
        "P08": [("Software Engineering", 3, (10, 15)), ("Quality & Compliance", 1, (6, 10)), ("Data & BI", 1, (8, 10))],
        "P09": [("Cloud & Infrastructure", 2, (10, 15)), ("Service Desk", 1, (5, 8))],
        "P10": [("Software Engineering", 2, (8, 12)), ("Service Desk", 2, (5, 10)), ("Data & BI", 1, (6, 8))],
    }
    # Specialists are shared across projects (realistic in a growing SME), so pools are deliberately small.
    pool_size = {"Software Engineering": 11, "Cloud & Infrastructure": 5, "Data & BI": 4, "Cybersecurity": 4,
                 "Service Desk": 5, "Quality & Compliance": 2}
    pools = {d: list(ids[1:1 + pool_size.get(d, len(ids))]) or list(ids) for d, ids in by_dept.items()}
    for d in pools:
        rnd.shuffle(pools[d])
    ptr = {d: 0 for d in pools}
    alloc_count: dict[int, float] = {}

    def alloc(eid, pcode, hours, role):
        db.t_insert("allocations", cid, {"employee_id": eid, "project_id": proj[pcode], "hours_per_week": float(hours), "project_role": role})
        alloc_count[eid] = alloc_count.get(eid, 0) + hours

    team_members: dict[str, list[int]] = {}
    for pcode, plan in team_plan.items():
        team_members[pcode] = []
        for dept, n, (lo, hi) in plan:
            for _ in range(n):
                pool = pools[dept]
                eid = pool[ptr[dept] % len(pool)]
                ptr[dept] += 1
                if eid in team_members[pcode]:
                    continue
                alloc(eid, pcode, rnd.randint(lo, hi), dept.split(" ")[0])
                team_members[pcode].append(eid)
        pm = db.t_get("projects", cid, proj[pcode])["manager_id"]
        alloc(pm, pcode, 8, "Project manager")
    # the exact example from the specification: 35h capacity, A=20, B=15, C=10 -> 45h (+10h)
    example = by_dept["Software Engineering"][1]
    db.execute("DELETE FROM allocations WHERE company_id=? AND employee_id=?", (cid, example))
    db.t_update("employees", cid, example, {"weekly_capacity": 35.0, "working_hours": "Mon-Fri 09:00-17:00"})
    for pcode, h in (("P01", 20), ("P02", 15), ("P05", 10)):
        alloc(example, pcode, h, "Software")
        if example not in team_members[pcode]:
            team_members[pcode].append(example)
    # internal BAU work for everyone with little project allocation
    for eid in emp_ids:
        cap = db.t_get("employees", cid, eid)["weekly_capacity"]
        have = sum(r["hours_per_week"] for r in db.t_rows("allocations", cid, "employee_id = ?", (eid,)))
        if have < cap * 0.6:
            bau = round(cap * rnd.uniform(0.55, 0.85) - have)
            if bau > 0:
                db.t_insert("allocations", cid, {"employee_id": eid, "project_id": proj["INT"], "hours_per_week": float(bau), "project_role": "BAU"})

    # Tasks & milestones -------------------------------------------------------
    phases = [  # title, share start, share end, skills, est hours
        ("Discovery & requirements", 0.00, 0.12, "Client relations", 60),
        ("Architecture & design", 0.12, 0.25, "APIs", 80),
        ("Build - sprint 1", 0.25, 0.45, "Python", 160),
        ("Build - sprint 2", 0.45, 0.62, "JavaScript", 160),
        ("Integration & data migration", 0.62, 0.75, "SQL", 120),
        ("Security review & hardening", 0.75, 0.83, "Vulnerability management", 60),
        ("Testing & UAT", 0.83, 0.92, "Testing", 100),
        ("Go-live & handover", 0.92, 1.00, "Project management", 40),
    ]
    tcount = 0
    for pcode, pid in proj.items():
        if pcode == "INT":
            continue
        p = db.t_get("projects", cid, pid)
        ps, pe = date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"])
        span = (pe - ps).days
        team = team_members.get(pcode, [p["manager_id"]])
        prev_id = None
        for i, (title, s0, s1, skill, est) in enumerate(phases):
            ts = ps + timedelta(days=int(span * s0))
            te = ps + timedelta(days=max(int(span * s1) - 1, int(span * s0) + 2))
            if p["status"] == "Completed":
                status, comp = "Completed", 100
            elif te < today:
                status, comp = "Completed", 100
                if rnd.random() < 0.22 or (pcode in ("P02", "P05") and i in (3, 4)):
                    status, comp = "In Progress", rnd.choice([60, 75, 85])
            elif ts <= today:
                frac = (today - ts).days / max((te - ts).days, 1)
                comp = int(min(95, max(5, frac * 100 + rnd.randint(-25, 10))))
                status = "In Progress"
                if rnd.random() < 0.12:
                    status = "Blocked"
            else:
                status, comp = "Not Started", 0
            if p["status"] == "On Hold" and status == "In Progress":
                status = "Blocked"
            assignee = p["manager_id"] if i in (0, 7) else team[(i + tcount) % len(team)]
            sub = None
            if pcode in sub_ids and i in (3, 4) and pcode in ("P02", "P05", "P04"):
                sub = sub_ids[pcode]
            tcount += 1
            tid = db.t_insert("tasks", cid, {
                "code": f"{pcode}-T{i + 1:02d}", "project_id": pid, "title": title,
                "description": f"{title} for {p['name']} (demo task).", "assignee_id": assignee,
                "contributors": "", "subcontractor_id": sub, "start_date": _iso(ts), "due_date": _iso(te),
                "est_hours": float(est), "actual_hours": float(round(est * comp / 100 * rnd.uniform(0.9, 1.25))),
                "priority": "Critical" if (p["priority"] == "Critical" and i in (4, 5, 7)) else ("High" if i in (5, 6, 7) else "Medium"),
                "status": status, "depends_on": str(prev_id) if prev_id and i not in (3,) else "",
                "completion": comp, "required_skills": skill, "risk_level": "Medium",
                "is_critical": int(i in (2, 4, 6, 7))})
            prev_id = tid
        for mname, share, mdone in (("Design sign-off", 0.25, True), ("UAT start", 0.80, False), ("Go-live", 1.0, False)):
            md = ps + timedelta(days=int(span * share))
            st = "Completed" if (p["status"] == "Completed" or (md < today and mdone)) else "Planned"
            if pcode == "P05" and mname == "UAT start":
                st = "Planned"
            db.t_insert("milestones", cid, {"project_id": pid, "name": mname, "due_date": _iso(md), "status": st})
    # a dependency conflict for the demo: P04 integration task starts before its predecessor ends
    t = db.one("SELECT id, start_date FROM tasks WHERE company_id=? AND code='P04-T05'", (cid,))
    pred = db.one("SELECT id FROM tasks WHERE company_id=? AND code='P04-T03'", (cid,))
    if t and pred:
        db.t_update("tasks", cid, t["id"], {"depends_on": str(pred["id"])})
        db.t_update("tasks", cid, pred["id"], {"due_date": D(40), "status": "In Progress", "completion": 35})
        db.t_update("tasks", cid, t["id"], {"start_date": D(20)})

    # Budget lines (sample monthly estimates) ------------------------------------
    for pcode, pid in proj.items():
        p = db.t_get("projects", cid, pid)
        if not p["budget"]:
            continue
        ps, pe = date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"])
        months = max((pe.year - ps.year) * 12 + pe.month - ps.month + 1, 1)
        elapsed = [m for m in range(months) if date(ps.year + (ps.month - 1 + m) // 12, (ps.month - 1 + m) % 12 + 1, 1) <= today]
        planned_m = p["budget"] / months
        act_total = p["actual_spend"]
        weights = [rnd.uniform(0.8, 1.2) for _ in elapsed] or [1]
        for idx, m in enumerate(range(months)):
            md = date(ps.year + (ps.month - 1 + m) // 12, (ps.month - 1 + m) % 12 + 1, 1)
            actual = round(act_total * weights[idx] / sum(weights), -2) if m in elapsed else None
            db.t_insert("budget_lines", cid, {"project_id": pid, "month": md.strftime("%Y-%m"), "planned": round(planned_m, -2),
                                              "actual": actual, "is_estimate": 1, "note": "Sample estimate (demo)"})

    # Absences ------------------------------------------------------------------
    crit_owner = db.one("""SELECT assignee_id FROM tasks WHERE company_id=? AND is_critical=1 AND status IN ('Not Started','In Progress')
                           AND due_date BETWEEN ? AND ? AND assignee_id IS NOT NULL ORDER BY due_date LIMIT 1""", (cid, D(4), D(12)))
    absences = [
        (crit_owner["assignee_id"] if crit_owner else emp_ids[40], "Planned leave", 3, 12, "Annual leave (demo)"),
        (by_dept["Cloud & Infrastructure"][2], "Unexpected absence", 0, 4, "Sick leave (demo - no medical detail stored)"),
        (by_dept["Data & BI"][1], "Training time", 7, 8, "Certification training (demo)"),
    ]
    for eid, typ, s0, s1, reason in absences:
        db.t_insert("absences", cid, {"employee_id": eid, "absence_type": typ, "start_date": D(s0), "end_date": D(s1),
                                      "reason": reason, "created_by": "seed", "created_at": db.now()})

    # Training ------------------------------------------------------------------
    trainings = [
        ("Security awareness", "Security", "All", 2), ("Phishing & business email compromise", "Security", "All", 1),
        ("GDPR essentials", "Compliance", "All", 1.5), ("Secure cloud administration", "Technical", "Cloud & Infrastructure", 6),
        ("Secure coding", "Technical", "Software Engineering", 6), ("Incident response basics", "Security", "Cybersecurity,Service Desk", 4),
        ("Payment fraud controls", "Finance", "Finance & Procurement", 2), ("Project management method", "Delivery", "Project Management", 4),
        ("Data protection for data teams", "Compliance", "Data & BI", 3),
    ]
    tr_ids = {}
    for nm, cat, req, hrs in trainings:
        tr_ids[nm] = (db.t_insert("trainings", cid, {"name": nm, "category": cat, "required_for": req, "duration_hours": hrs}), req)
    for eid in emp_ids:
        e = db.t_get("employees", cid, eid)
        join = date.fromisoformat(e["join_date"])
        for nm, (tid, req) in tr_ids.items():
            if req != "All" and e["department"] not in req.split(","):
                continue
            due = max(join + timedelta(days=30), today - timedelta(days=330)) if not e["is_new_hire"] else join + timedelta(days=30)
            if e["is_new_hire"]:
                r = rnd.random()
                if (today - join).days < 30:
                    status, comp = ("In progress", 40) if r < 0.5 else ("Assigned", 0)
                elif r < 0.55:
                    status, comp = "Completed", 100
                elif r < 0.8:
                    status, comp = "In progress", rnd.choice([25, 50, 75])
                else:
                    status, comp = "Assigned", 0
            else:
                status, comp = ("Completed", 100) if rnd.random() < 0.9 else ("In progress", 50)
            db.t_insert("training_assignments", cid, {
                "employee_id": eid, "training_id": tid, "due_date": _iso(due), "status": status, "completion": comp,
                "score": rnd.randint(70, 100) if status == "Completed" else None,
                "completed_date": _iso(min(due, today)) if status == "Completed" else None})

    # Onboarding checklist for the 25 recruits ------------------------------------
    for eid in emp_ids:
        e = db.t_get("employees", cid, eid)
        if not e["is_new_hire"]:
            continue
        age = (today - date.fromisoformat(e["join_date"])).days
        done_upto = 10 if age > 240 and rnd.random() < 0.7 else min(10, 3 + age // 30 + rnd.randint(-1, 1))
        for step in range(1, 11):
            done = step <= done_upto
            if step == 3 and rnd.random() < 0.2:
                done = False  # missing required documents evidence
            db.t_insert("onboarding_steps", cid, {"employee_id": eid, "step_no": step, "done": int(done),
                                                  "done_date": e["join_date"] if done else None,
                                                  "evidence": "Recorded in HR system (demo)" if done else ""})

    # Access requests (Joiner-Mover-Leaver) ---------------------------------------
    systems = {
        "Cloud & Infrastructure": [("Cloud console (production)", "Administrator", 1), ("Microsoft 365", "Standard user", 0)],
        "Cybersecurity": [("SIEM console", "Analyst", 1), ("Microsoft 365", "Standard user", 0)],
        "Software Engineering": [("Git repositories", "Developer", 0), ("Microsoft 365", "Standard user", 0)],
        "Data & BI": [("Data warehouse", "Read/write", 0), ("Microsoft 365", "Standard user", 0)],
        "Finance & Procurement": [("Finance ERP", "Payment approver", 1), ("Microsoft 365", "Standard user", 0)],
    }
    for eid in emp_ids:
        e = db.t_get("employees", cid, eid)
        if not e["is_new_hire"]:
            continue
        for sysname, perm, priv in systems.get(e["department"], [("Microsoft 365", "Standard user", 0), ("Project tool", "Member", 0)]):
            r = rnd.random()
            appr, act = ("Approved", "Active") if r < 0.7 else ("Pending", "Not activated") if r < 0.85 else ("Approved", "Not activated")
            review = date.fromisoformat(e["join_date"]) + timedelta(days=90)
            db.t_insert("access_requests", cid, {
                "employee_id": eid, "lifecycle_event": "Joiner", "system": sysname, "permission": perm, "privileged": priv,
                "justification": f"Required for {e['job_role']} role", "requester": "Line manager (demo)",
                "approver": "IT manager (demo)" if appr == "Approved" else "", "approval_status": appr, "activation_status": act,
                "review_date": _iso(review), "last_reviewed": _iso(review) if rnd.random() < 0.45 else None,
                "revocation_status": "Not required", "created_at": e["join_date"]})
    for i, eid in enumerate(leavers):
        for sysname in ("Microsoft 365", "Project tool", "VPN"):
            db.t_insert("access_requests", cid, {
                "employee_id": eid, "lifecycle_event": "Leaver", "system": sysname, "permission": "Standard user", "privileged": 0,
                "justification": "Employee departure", "requester": "HR (demo)", "approver": "IT manager (demo)",
                "approval_status": "Approved", "activation_status": "Active" if (i == 0 or sysname == "VPN") else "Disabled",
                "review_date": D(-5), "revocation_status": "Pending" if (i == 0 or sysname == "VPN") else "Revoked", "created_at": D(-20)})
    mover = by_dept["Service Desk"][3]
    db.t_insert("access_requests", cid, {
        "employee_id": mover, "lifecycle_event": "Mover", "system": "SIEM console", "permission": "Analyst", "privileged": 1,
        "justification": "Transfer from Service Desk to Cybersecurity team", "requester": "Line manager (demo)", "approver": "",
        "approval_status": "Pending", "activation_status": "Not activated", "review_date": D(60), "revocation_status": "Not required",
        "created_at": D(-3)})

    # GDPR evidence ---------------------------------------------------------------
    for i, clid in enumerate(client_ids[:10]):
        for j, ev in enumerate(EVIDENCE_TYPES):
            r = rnd.random()
            status = "Verified" if r < 0.75 else "In review" if r < 0.9 else "Missing" if r < 0.97 else "Expired"
            if i == 1 and j == 0:
                status = "Missing"
            db.t_insert("compliance_evidence", cid, {
                "client_id": clid, "evidence_type": ev, "status": status, "owner": "Compliance officer (demo)",
                "due_date": D(rnd.randint(-20, 60)), "last_review": D(-rnd.randint(10, 300)) if status == "Verified" else None,
                "reference": f"EVD-{i + 1:02d}-{j + 1}" if status in ("Verified", "In review") else "", "notes": ""})

    # Cloud services, digital tools ------------------------------------------------
    for nm, prov, crit, outages, lr, rto, rpo in [
        ("Production hosting (client portals)", "Public cloud provider A", "Critical", 2, -95, 4, 1),
        ("Microsoft 365 (mail, files)", "Microsoft", "Critical", 1, None, 8, 24),
        ("Identity provider (SSO / MFA)", "Cloud IdP", "Critical", 0, -60, 2, 1),
        ("Backup service", "Backup SaaS", "High", 0, -30, 24, 24),
        ("Client data platform", "Public cloud provider B", "Critical", 3, -260, 8, 4),
        ("Git hosting & CI", "SaaS", "High", 1, -120, 24, 24),
    ]:
        db.t_insert("cloud_services", cid, {"name": nm, "provider": prov, "owner": "IT / Operations (demo)", "criticality": crit,
                                            "provider_sla": "99.9%" if crit == "Critical" else "99.5%", "dependencies": "Identity provider; network",
                                            "outages_12m": outages, "last_restore_test": D(lr) if lr is not None else None,
                                            "rto_hours": rto, "rpo_hours": rpo,
                                            "recovery_evidence": "Restore test report on file" if lr and lr > -180 else "Not recorded"})
    for nm, owner, appr, rev, integ, concern in [
        ("Project management tool", "PMO", "Approved", -120, "SSO, Git", ""),
        ("CRM", "Sales", "Approved", -420, "Email, ERP", "Configuration review older than 12 months"),
        ("E-signature service", "Finance", "Approved", -60, "CRM", ""),
        ("AI meeting note-taker", "Unknown", "Not approved (shadow IT suspected)", None, "Calendar, M365", "Reported in use by some teams; data location unknown"),
        ("File-sharing app", "Delivery teams", "Under review", None, "M365", "Public-link sharing settings not reviewed"),
        ("Team chat", "IT", "Approved", -200, "SSO", ""),
    ]:
        db.t_insert("digital_tools", cid, {"name": nm, "owner": owner, "approved": appr, "config_review_date": D(rev) if rev else None,
                                           "integrations": integ, "change_records": "Change ticket on file" if appr == "Approved" else "",
                                           "concern": concern, "remediation": ""})

    # Signals (fictional, unconfirmed) ---------------------------------------------
    sig_specs = [
        (-3, "Security alert", "Unusual sign-in location flagged", "Microsoft 365", "Angers", "Sales", ""),
        (-6, "Help-desk ticket", "User reported unexpected MFA prompt", "Microsoft 365", "Nantes", "Delivery", ""),
        (-11, "Help-desk ticket", "Repeated password-reset requests", "Microsoft 365", "Rennes", "Support", ""),
        (-19, "Near miss", "Suspicious invoice e-mail reported by staff", "Microsoft 365", "Angers", "Finance", ""),
        (-2, "Incident ticket", "VPN disconnections for remote staff", "VPN gateway", "Nantes", "Delivery", ""),
        (-8, "Help-desk ticket", "Slow VPN reported", "VPN gateway", "Rennes", "Data", ""),
        (-15, "Incident ticket", "VPN gateway restart required", "VPN gateway", "Angers", "IT", ""),
        (-5, "Unusual signal", "Spike in failed logins on client portal", "Client portal", "Angers", "Delivery", ""),
        (-25, "Incident ticket", "Short client-portal outage (12 min)", "Client portal", "Nantes", "Delivery", "Public cloud provider A"),
        (-40, "Near miss", "Wrong recipient on project e-mail (caught before send)", "Microsoft 365", "Rennes", "Delivery", ""),
        (-13, "Unusual signal", "Large file-sharing link created externally", "File-sharing app", "Nantes", "Delivery", ""),
        (-33, "Incident ticket", "Data platform job failure", "Client data platform", "Rennes", "Data", "Public cloud provider B"),
        (-9, "Security alert", "Endpoint protection disabled on a laptop", "Endpoints", "Angers", "Support", ""),
        (-48, "Help-desk ticket", "Subcontractor requested additional admin rights", "Cloud console", "Nantes", "Delivery", "CloudOps Partners (demo)"),
    ]
    for d0, typ, title, system, loc, team, supplier in sig_specs:
        db.t_insert("signals", cid, {"signal_date": D(d0), "signal_type": typ, "title": title + " (demo)", "system": system,
                                     "location_id": loc_ids[loc], "team": team, "supplier": supplier,
                                     "severity": "Medium" if typ in ("Security alert", "Incident ticket") else "Low",
                                     "status": "Under investigation" if d0 > -7 and typ == "Security alert" else "Warning signal",
                                     "root_cause": "", "notes": "Fictional demonstration signal - not a confirmed incident."})

    # Case-study risk register R1-R12 (Group 5 - Risk Identification) ------------------
    created = _iso(today - timedelta(days=28)) + " 09:00:00"
    for code, t_en, t_fr, cat, ccat, p, i, cause, event, cons, ev, ctrl, owner in R_CASE:
        db.t_insert("risks", cid, {
            "code": code, "title": t_en, "title_fr": t_fr, "category": cat, "case_category": ccat, "probability": p, "impact": i,
            "status": "Open", "evidence_status": "Unconfirmed hypothesis",
            "source": "Case study - Group 5 risk identification (V. Bhosale)", "owner": owner, "cause": cause, "event": event,
            "consequences": cons, "evidence_needed": ev, "recommended_action": ctrl,
            "explanation": f"Because of: {cause} Risk event: {event} Consequence: {cons} Provisional estimate to prioritise investigation - not measured company data.",
            "explanation_fr": "Scénario issu de l'identification des risques (Groupe 5). Estimation provisoire pour prioriser l'investigation - pas une donnée mesurée.",
            "created_at": created, "updated_at": created})
    for code, act in (("R2", "Export MFA coverage report from the identity provider"), ("R5", "Run first quarterly access review"),
                      ("R10", "Schedule restore test for client data platform")):
        rid = db.scalar("SELECT id FROM risks WHERE company_id=? AND code=?", (cid, code))
        db.t_insert("risk_actions", cid, {"risk_id": rid, "action": act, "owner": "IT / Security", "due_date": D(14),
                                          "status": "Open", "note": "", "user": "seed", "ts": db.now()})

    # Users: one demo account per role -------------------------------------------
    pw = demo_password()
    pm_emp = db.t_get("projects", cid, proj["P02"])["manager_id"]
    users = [
        ("Demo Company Admin", "admin", "Company Administrator", by_dept["Management"][0], None),
        ("Demo Project Manager", "pm", "Project Manager", pm_emp, None),
        ("Demo Team Leader", "lead", "Team Leader", by_dept["Software Engineering"][0], None),
        ("Demo Employee", "employee", "Employee", example, None),
        ("Demo HR Manager", "hr", "HR / Training Manager", by_dept["HR & Training"][0], None),
        ("Demo Risk Manager", "risk", "Risk / Compliance Manager", by_dept["Quality & Compliance"][0], None),
        ("Demo Finance Manager", "finance", "Finance Manager", by_dept["Finance & Procurement"][0], None),
        ("Demo Subcontractor", "subcontractor", "Subcontractor", None, sub_ids["P02"]),
    ]
    for nm, local, role, eid, sid in users:
        en = db.t_get("employees", cid, eid)["name"] if eid else nm
        auth.create_user(cid, f"{en} ({role})" if eid else nm, f"{local}@{DEMO_DOMAIN}", pw, role, eid, sid)
    # One personal login per demo employee: employee1..employee85 / pass@1..pass@85 (demo workspace only).
    for i, eid in enumerate(emp_ids, start=1):
        e = db.t_get("employees", cid, eid)
        uid = auth.create_user(cid, e["name"], f"employee{i}", "", "Employee", eid,
                               pw_hash=auth.hash_password(f"pass@{i}", iterations=20_000))
        n_open = db.scalar("SELECT COUNT(*) FROM tasks WHERE company_id=? AND assignee_id=? AND status IN ('Not Started','In Progress','Blocked','Under Review')", (cid, eid))
        nxt = db.one("SELECT code, title, due_date FROM tasks WHERE company_id=? AND assignee_id=? AND status IN ('Not Started','In Progress','Blocked','Under Review') ORDER BY due_date LIMIT 1", (cid, eid))
        db.execute("INSERT INTO inbox (company_id, user_id, kind, title, body, page, created_at) VALUES (?,?,?,?,?,?,?)",
                   (cid, uid, "info", f"Welcome {e['name']}",
                    f"You have {n_open} open task(s)." + (f" Next deadline: {nxt['code']} {nxt['title']} on {nxt['due_date']}." if nxt else ""),
                    "my_work", db.now()))

    db.execute("INSERT INTO audit_log (company_id, user, action, entity, entity_id, details, ts) VALUES (?,?,?,?,?,?,?)",
               (cid, "system", "seed_demo", "company", str(cid), "Demonstration workspace created (fictional data)", db.now()))
    engine_risk.run(cid, "seed")
    # Back-date rule-engine risks a little so the trend chart shows a realistic build-up (labelled demo history).
    rows = db.t_rows("risks", cid, "source = 'Rule engine'")
    for n, r in enumerate(rows):
        back = _iso(today - timedelta(days=(n * 5) % 70)) + " 08:00:00"
        db.t_update("risks", cid, r["id"], {"created_at": back})
    return cid


def ensure_platform_admin() -> None:
    """Create the SaaS platform administrator from secrets/env (never a hard-coded password)."""
    email = password = ""
    try:
        import streamlit as st
        email = str(st.secrets.get("PLATFORM_ADMIN_EMAIL", ""))
        password = str(st.secrets.get("PLATFORM_ADMIN_PASSWORD", ""))
    except Exception:
        pass
    email = email or os.environ.get("PLATFORM_ADMIN_EMAIL", "")
    password = password or os.environ.get("PLATFORM_ADMIN_PASSWORD", "")
    if email and password and not auth.email_taken(email):
        auth.create_user(None, "Platform Administrator", email, password, "Platform Administrator")


SEED_VERSION = "2"  # bump when the demo data model changes; the demo workspace is then regenerated


def ensure_demo() -> None:
    db.init_schema()
    current = db.scalar("SELECT value FROM meta WHERE key = 'seed_version'")
    if not db.scalar("SELECT COUNT(*) FROM companies WHERE is_demo = 1"):
        seed_demo()
    elif current != SEED_VERSION:
        reset_demo()
    db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('seed_version', ?)", (SEED_VERSION,))
    ensure_platform_admin()


def reset_demo() -> int:
    """Delete and re-create the demonstration workspace only."""
    old = db.scalar("SELECT id FROM companies WHERE is_demo = 1")
    if old:
        for t in db.TENANT_TABLES:
            db.execute(f"DELETE FROM {t} WHERE company_id = ?", (old,))
        db.execute("DELETE FROM reset_tokens WHERE user_id IN (SELECT id FROM users WHERE company_id = ?)", (old,))
        db.execute("DELETE FROM auth_sessions WHERE user_id IN (SELECT id FROM users WHERE company_id = ?)", (old,))
        db.execute("DELETE FROM users WHERE company_id = ?", (old,))
        db.execute("DELETE FROM companies WHERE id = ?", (old,))
    return seed_demo()
