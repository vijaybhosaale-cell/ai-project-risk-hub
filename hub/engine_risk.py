"""Explainable rule-based risk engine.

Score = Probability x Impact (1-5 each). Bands (configurable): 1-7 Low, 8-14 Medium,
15-19 High, 20-25 Critical. No machine-learning model is trained or used here; see
``ai_interface.py`` for the plug-in point where an ML/LLM advisor can be added later.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import db, engine_alloc

RISK_STATUSES = ["Open", "Acknowledged", "Assigned", "In remediation", "Condition cleared", "Resolved"]
EVIDENCE_STATUSES = ["Confirmed fact", "Unconfirmed hypothesis", "Warning signal",
                     "Incident under investigation", "Resolved issue"]
CASE_CATEGORIES = [
    "1. Cloud infrastructure dependency", "2. Remote working", "3. New employees",
    "4. New digital tools", "5. Subcontractors", "6. European clients & recurring revenue",
    "7. Incidents & unusual signals", "Project delivery & capacity", "Financial", "Reputation",
]
OPEN_STATUSES = ("Open", "Acknowledged", "Assigned", "In remediation")


def priority(score: int, cid: int | None = None) -> str:
    b = db.settings(cid)["risk_bands"] if cid else {"medium": 8, "high": 15, "critical": 20}
    if score >= b["critical"]:
        return "Critical"
    if score >= b["high"]:
        return "High"
    if score >= b["medium"]:
        return "Medium"
    return "Low"


PRIORITY_COLORS = {"Critical": "#b3261e", "High": "#e06c1f", "Medium": "#d9a400", "Low": "#3aa76d"}


def _c(x: int) -> int:
    return int(max(1, min(5, x)))


def _d(x):
    try:
        return date.fromisoformat(str(x)[:10]) if x else None
    except ValueError:
        return None


def detect(cid: int, ref: date | None = None) -> list[dict]:
    """Run every rule against the company's stored data and return findings."""
    ref = ref or date.today()
    s = db.settings(cid)
    window = s.get("deadline_window_days", 14)
    track = s.get("track", {})
    out: list[dict] = []
    projects = {p["id"]: p for p in db.t_rows("projects", cid, "archived = 0")}
    emps = {e["id"]: e for e in db.t_rows("employees", cid)}
    tasks = db.t_rows("tasks", cid)
    open_tasks = [t for t in tasks if t["status"] in engine_alloc.OPEN_TASK]

    def add(**k):
        k.setdefault("project_id", None)
        k.setdefault("employee_id", None)
        out.append(k)

    # 1. Employee overcapacity ------------------------------------------------
    wl = engine_alloc.workload(cid, ref)
    if track.get("operational", True) and not wl.empty:
        for _, r in wl[wl["band"] == "Overcapacity"].iterrows():
            et = [t for t in open_tasks if t["assignee_id"] == r["employee_id"]]
            crit = any(t["is_critical"] or t["priority"] in ("High", "Critical") for t in et)
            p = 3 if r["utilisation"] <= 115 else 4 if r["utilisation"] <= 130 else 5
            i = _c(3 + (1 if r["upcoming_deadlines"] > 0 else 0) + (1 if crit else 0))
            add(rule_key=f"overcap:{r['employee_id']}", category="Resource / capacity",
                case_category="Project delivery & capacity", probability=p, impact=i,
                employee_id=int(r["employee_id"]), owner="Project managers",
                title=f"Employee overcapacity: {r['name']}", title_fr=f"Surcharge de travail : {r['name']}",
                evidence_status="Confirmed fact",
                explanation=(f"{r['name']} is allocated {r['allocated']}h/week across {r['projects']} project(s) "
                             f"({r['project_list']}) against an effective capacity of {r['effective_capacity']}h "
                             f"({r['utilisation']}%, +{r['over_hours']}h). {r['upcoming_deadlines']} deadline(s) fall in the next "
                             f"{window} days; estimated delay exposure {r['delay_exposure_days_per_week']} working day(s)/week."),
                explanation_fr=(f"{r['name']} est affecté(e) à {r['allocated']} h/semaine sur {r['projects']} projet(s) "
                                f"({r['project_list']}) pour une capacité effective de {r['effective_capacity']} h "
                                f"({r['utilisation']} %, +{r['over_hours']} h). {r['upcoming_deadlines']} échéance(s) dans les "
                                f"{window} prochains jours ; exposition au retard estimée {r['delay_exposure_days_per_week']} jour(s)/semaine."),
                evidence_needed="Allocation records, task assignments, deadlines",
                recommended_action="Review allocation; reassign selected tasks to a qualified available colleague after manager approval; review priorities.")

    # 2. Absence affecting critical tasks --------------------------------------
    for a in db.t_rows("absences", cid):
        a_s, a_e = _d(a["start_date"]), _d(a["end_date"]) or _d(a["start_date"])
        if not a_s or a_e < ref or a_s > ref + timedelta(days=window):
            continue
        e = emps.get(a["employee_id"])
        if not e:
            continue
        hit = [t for t in open_tasks if t["assignee_id"] == e["id"] and _d(t["due_date"])
               and _d(t["due_date"]) <= a_e + timedelta(days=3)]
        if not hit:
            continue
        crit = [t for t in hit if t["is_critical"] or t["priority"] in ("High", "Critical")]
        add(rule_key=f"absence:{a['id']}", category="Resource / availability",
            case_category="Project delivery & capacity", probability=4,
            impact=_c(3 + (1 if crit else 0) + (1 if len(hit) >= 3 else 0)), employee_id=e["id"],
            project_id=hit[0]["project_id"], owner="Project managers", evidence_status="Confirmed fact",
            title=f"Absence affects tasks: {e['name']}", title_fr=f"Absence impactant des tâches : {e['name']}",
            explanation=(f"{e['name']} is unavailable ({a['absence_type']}) from {a_s} to {a_e}. {len(hit)} open task(s) "
                         f"are due during or just after the absence, {len(crit)} of them high priority/critical: "
                         + ", ".join(t["code"] for t in hit[:6]) + "."),
            explanation_fr=(f"{e['name']} est indisponible ({a['absence_type']}) du {a_s} au {a_e}. {len(hit)} tâche(s) ouverte(s) "
                            f"arrivent à échéance pendant ou juste après l'absence, dont {len(crit)} prioritaire(s)/critique(s)."),
            evidence_needed="Absence record, task due dates",
            recommended_action="Identify a qualified replacement (manager approval), or agree revised deadlines with the client.")

    # 3. Missed milestones & 4. Delayed tasks & 5. Dependency conflicts per project
    ms = db.t_rows("milestones", cid)
    by_code = {t["id"]: t for t in tasks}
    for pid, p in projects.items():
        if p["status"] in ("Completed", "Cancelled"):
            continue
        hi = p["priority"] in ("High", "Critical")
        missed = [m for m in ms if m["project_id"] == pid and m["status"] != "Completed" and _d(m["due_date"]) and _d(m["due_date"]) < ref]
        if missed:
            add(rule_key=f"milestone:{pid}", category="Schedule", case_category="Project delivery & capacity",
                probability=4, impact=_c(3 + hi + (len(missed) > 1)), project_id=pid, owner="Project manager",
                evidence_status="Confirmed fact",
                title=f"Missed milestone(s) on {p['code']}", title_fr=f"Jalon(s) manqué(s) sur {p['code']}",
                explanation=f"{len(missed)} milestone(s) past due and not completed: " + "; ".join(f"{m['name']} ({m['due_date']})" for m in missed),
                explanation_fr=f"{len(missed)} jalon(s) dépassé(s) et non terminé(s) : " + "; ".join(f"{m['name']} ({m['due_date']})" for m in missed),
                evidence_needed="Milestone plan, client acceptance records",
                recommended_action="Re-baseline the plan with the client; confirm recovery actions and owners.")
        od = [t for t in open_tasks if t["project_id"] == pid and _d(t["due_date"]) and _d(t["due_date"]) < ref]
        if od:
            n = len(od)
            critical = any(t["is_critical"] or t["priority"] in ("High", "Critical") for t in od)
            add(rule_key=f"delayed:{pid}", category="Schedule", case_category="Project delivery & capacity",
                probability=3 if n == 1 else 4 if n <= 3 else 5, impact=_c(3 + critical + hi), project_id=pid,
                owner="Project manager", evidence_status="Confirmed fact",
                title=f"Delayed tasks on {p['code']}", title_fr=f"Tâches en retard sur {p['code']}",
                explanation=f"{n} open task(s) are past their due date: " + ", ".join(f"{t['code']} ({t['due_date']})" for t in od[:8]),
                explanation_fr=f"{n} tâche(s) ouverte(s) ont dépassé leur échéance : " + ", ".join(f"{t['code']} ({t['due_date']})" for t in od[:8]),
                evidence_needed="Task status, timesheets",
                recommended_action="Review blocked/overdue tasks in the next stand-up; agree new dates (logged with reason) or add support.")
        conflicts = []
        for t in open_tasks:
            if t["project_id"] != pid or not t["depends_on"]:
                continue
            for dep in str(t["depends_on"]).split(","):
                dep = dep.strip()
                if not dep.isdigit():
                    continue
                d = by_code.get(int(dep))
                if d and d["status"] != "Completed" and _d(d["due_date"]) and _d(t["start_date"]) and _d(d["due_date"]) > _d(t["start_date"]):
                    conflicts.append(f"{t['code']} starts {t['start_date']} before {d['code']} ends {d['due_date']}")
                elif d and d["status"] == "Blocked":
                    conflicts.append(f"{t['code']} depends on blocked task {d['code']}")
        if conflicts:
            add(rule_key=f"dependency:{pid}", category="Schedule / dependency", case_category="Project delivery & capacity",
                probability=3, impact=_c(3 + hi), project_id=pid, owner="Project manager", evidence_status="Confirmed fact",
                title=f"Dependency conflicts on {p['code']}", title_fr=f"Conflits de dépendances sur {p['code']}",
                explanation="; ".join(conflicts[:6]),
                explanation_fr="Conflits détectés : " + "; ".join(conflicts[:6]),
                evidence_needed="Task plan and dependencies",
                recommended_action="Re-sequence dependent tasks in the Gantt or resolve the blocking task first.")
        # 6. Budget
        bud = p["budget"] or 0
        if bud > 0:
            used = (p["actual_spend"] or 0) / bud * 100
            fc = p["forecast_spend"] or 0
            if used >= s.get("budget_warning_pct", 90) or fc > bud:
                pr = 5 if used > 100 else 4 if fc > bud else 3
                add(rule_key=f"budget:{pid}", category="Financial", case_category="Financial",
                    probability=pr, impact=_c(3 + (fc > bud * 1.1)), project_id=pid, owner="Finance manager",
                    evidence_status="Confirmed fact",
                    title=f"Budget pressure on {p['code']}", title_fr=f"Tension budgétaire sur {p['code']}",
                    explanation=f"Actual spend is {used:.0f}% of the approved budget ({p['actual_spend']:,.0f} / {bud:,.0f}); forecast {fc:,.0f}.",
                    explanation_fr=f"Dépenses réelles à {used:.0f} % du budget approuvé ({p['actual_spend']:,.0f} / {bud:,.0f}) ; prévision {fc:,.0f}.",
                    evidence_needed="Budget lines, invoices, timesheets",
                    recommended_action="Review forecast with finance; agree scope/budget change or cost controls.")
        # 11. SLA / end date approaching with low progress
        end = _d(p["end_date"])
        if track.get("sla", True) and end and ref <= end <= ref + timedelta(days=30):
            pt = [t for t in tasks if t["project_id"] == pid and t["status"] != "Cancelled"]
            if pt:
                w = sum((t["est_hours"] or 1) for t in pt)
                prog = sum((t["est_hours"] or 1) * (100 if t["status"] == "Completed" else t["completion"]) for t in pt) / w
                if prog < 80:
                    add(rule_key=f"sla:{pid}", category="Client / SLA", case_category="6. European clients & recurring revenue",
                        probability=4 if prog < 60 else 3, impact=4, project_id=pid, owner="Project manager",
                        evidence_status="Warning signal",
                        title=f"SLA / delivery date at risk: {p['code']}", title_fr=f"SLA / date de livraison menacée : {p['code']}",
                        explanation=f"Project ends {end} ({(end - ref).days} days) but weighted progress is {prog:.0f}%. SLA ref: {p['sla_ref'] or 'n/a'}.",
                        explanation_fr=f"Le projet se termine le {end} ({(end - ref).days} jours) mais l'avancement pondéré est de {prog:.0f} %.",
                        evidence_needed="Contract/SLA terms, project plan",
                        recommended_action="Inform the client early if needed; prioritise remaining deliverables; consider extra capacity.")

    # 7. Subcontractor delays ---------------------------------------------------
    if track.get("supplier", True):
        subs = {x["id"]: x for x in db.t_rows("subcontractors", cid)}
        for sid, sub in subs.items():
            late = [t for t in open_tasks if t["subcontractor_id"] == sid and _d(t["due_date"]) and
                    (_d(t["due_date"]) < ref or (_d(t["due_date"]) <= ref + timedelta(days=7) and (t["completion"] or 0) < 50))]
            if late:
                add(rule_key=f"subdelay:{sid}", category="Third party / delivery", case_category="5. Subcontractors",
                    probability=4, impact=4, project_id=late[0]["project_id"], owner="Project manager / Procurement",
                    evidence_status="Confirmed fact",
                    title=f"Subcontractor delivery risk: {sub['name']}", title_fr=f"Risque de livraison sous-traitant : {sub['name']}",
                    explanation=f"{len(late)} subcontractor task(s) overdue or due within 7 days with <50% completion: " + ", ".join(t["code"] for t in late),
                    explanation_fr=f"{len(late)} tâche(s) sous-traitée(s) en retard ou dues sous 7 jours avec <50 % d'avancement.",
                    evidence_needed="Subcontractor delivery reports, contract milestones",
                    recommended_action="Hold a delivery review with the subcontractor; record a corrective action or replacement plan.")
            exp = _d(sub["access_expiry"])
            if sub["security_assessment"] in ("Not started", "Overdue") and sub["data_access"] and sub["data_access"] != "None":
                add(rule_key=f"subsec:{sid}", category="Third party / security", case_category="5. Subcontractors",
                    probability=3, impact=5, owner="Risk / Compliance manager", evidence_status="Warning signal",
                    title=f"Subcontractor security review missing: {sub['name']}",
                    title_fr=f"Évaluation sécurité sous-traitant manquante : {sub['name']}",
                    explanation=f"{sub['name']} has data access ({sub['data_access']}) but security assessment status is '{sub['security_assessment']}'"
                                + (f"; access expires {exp}." if exp else "; no access expiry date recorded."),
                    explanation_fr=f"{sub['name']} a un accès aux données ({sub['data_access']}) mais l'évaluation sécurité est « {sub['security_assessment']} ».",
                    evidence_needed="Security questionnaire, contract clauses, access logs",
                    recommended_action="Complete a risk-based security assessment; set time-limited least-privilege access.")

    # 8. Incomplete training (new employees) ------------------------------------
    ta = db.df("""SELECT ta.*, e.name, e.is_new_hire FROM training_assignments ta JOIN employees e ON e.id = ta.employee_id
                  WHERE ta.company_id = ? AND e.active = 1""", (cid,))
    if not ta.empty:
        od = ta[(ta["status"] != "Completed") & (pd.to_datetime(ta["due_date"], errors="coerce").dt.date < ref)]
        nh = od[od["is_new_hire"] == 1]
        if len(nh):
            n_emp = nh["employee_id"].nunique()
            add(rule_key="training:newhires", category="Human / awareness", case_category="3. New employees",
                probability=4 if n_emp >= 5 else 3, impact=4, owner="HR / Training manager", evidence_status="Confirmed fact",
                title="New employees with overdue mandatory training", title_fr="Nouveaux salariés avec formations obligatoires en retard",
                explanation=f"{n_emp} recently recruited employee(s) have {len(nh)} overdue training assignment(s) (e.g. security awareness). Links to case risk R4.",
                explanation_fr=f"{n_emp} salarié(s) récemment recruté(s) ont {len(nh)} formation(s) en retard (ex. sensibilisation sécurité). Lié au risque R4.",
                evidence_needed="Training completion records",
                recommended_action="Schedule the overdue sessions; managers to confirm completion before granting additional access.")

    # 9. Missing access reviews / leavers not revoked ---------------------------
    ar = db.t_rows("access_requests", cid)
    overdue_rev = [a for a in ar if a["activation_status"] == "Active" and _d(a["review_date"]) and _d(a["review_date"]) < ref
                   and (not a["last_reviewed"] or _d(a["last_reviewed"]) < _d(a["review_date"]))]
    if overdue_rev:
        priv = sum(1 for a in overdue_rev if a["privileged"])
        add(rule_key="access:reviews", category="Identity / access", case_category="3. New employees",
            probability=4, impact=_c(4 + (priv > 0)), owner="Risk / Compliance manager", evidence_status="Confirmed fact",
            title="Overdue access reviews", title_fr="Revues d'accès en retard",
            explanation=f"{len(overdue_rev)} active access right(s) are past their review date ({priv} privileged). Links to case risks R2/R5.",
            explanation_fr=f"{len(overdue_rev)} droit(s) d'accès actif(s) ont dépassé leur date de revue ({priv} privilégié(s)). Lié aux risques R2/R5.",
            evidence_needed="Access review records, privileged account list",
            recommended_action="Run the access review; remove unneeded rights; record reviewer and date.")
    leavers = [a for a in ar if a["revocation_status"] in ("Pending", "Overdue")]
    if leavers:
        add(rule_key="access:leavers", category="Identity / access", case_category="3. New employees",
            probability=4, impact=5, owner="HR / IT", evidence_status="Confirmed fact",
            title="Leaver access not yet revoked", title_fr="Accès de salariés partis non révoqués",
            explanation=f"{len(leavers)} access right(s) for departed or moved staff are still marked as not revoked. "
                        "This app tracks status only; it does not disable accounts in external systems.",
            explanation_fr=f"{len(leavers)} droit(s) d'accès de salariés partis ou mutés ne sont pas encore révoqués. "
                           "L'application suit le statut uniquement ; elle ne désactive pas les comptes externes.",
            evidence_needed="HR leaver notifications, account-disable timestamps",
            recommended_action="Disable accounts in the identity provider and record the revocation date here.")

    # 10. Missing compliance evidence (GDPR) -----------------------------------
    if track.get("gdpr", True):
        ev = db.df("""SELECT ce.*, c.name AS client FROM compliance_evidence ce JOIN clients c ON c.id = ce.client_id
                      WHERE ce.company_id = ?""", (cid,))
        if not ev.empty:
            miss = ev[ev["status"].isin(["Missing", "Expired"])]
            for client, g in miss.groupby("client"):
                dpa = (g["evidence_type"] == "Data-processing agreement (DPA)").any()
                add(rule_key=f"gdpr:{g['client_id'].iloc[0]}", category="Legal / compliance",
                    case_category="6. European clients & recurring revenue", probability=3, impact=_c(4 + dpa),
                    owner="Risk / Compliance manager", evidence_status="Confirmed fact",
                    title=f"Missing GDPR evidence: {client}", title_fr=f"Preuves RGPD manquantes : {client}",
                    explanation=f"{len(g)} evidence item(s) missing/expired: " + ", ".join(g["evidence_type"]) + ". Links to case risk R7.",
                    explanation_fr=f"{len(g)} preuve(s) manquante(s)/expirée(s) : " + ", ".join(g["evidence_type"]) + ". Lié au risque R7.",
                    evidence_needed="DPA, data map, contract clauses, incident procedure",
                    recommended_action="Collect or renew the evidence and have it reviewed by the privacy lead / legal adviser.")

    # 12. Repeated incidents / unusual signals ---------------------------------
    sig = db.t_df("signals", cid)
    if not sig.empty:
        sig["d"] = pd.to_datetime(sig["signal_date"], errors="coerce").dt.date
        recent = sig[(sig["d"] >= ref - timedelta(days=30)) & (~sig["status"].isin(["Resolved issue", "Closed - no issue"]))]
        for system, g in recent.groupby("system"):
            if len(g) >= 3:
                add(rule_key=f"signals:{system}", category="Cybersecurity / operations", case_category="7. Incidents & unusual signals",
                    probability=3, impact=4, owner="Risk / Compliance manager", evidence_status="Unconfirmed hypothesis",
                    title=f"Repeated signals on {system}", title_fr=f"Signaux répétés sur {system}",
                    explanation=f"{len(g)} signals in the last 30 days relate to {system}. They MAY share a root cause; "
                                "this is not confirmed. Investigation recommended.",
                    explanation_fr=f"{len(g)} signaux sur 30 jours concernent {system}. Ils POURRAIENT avoir une cause commune ; "
                                   "ce n'est pas confirmé. Une investigation est recommandée.",
                    evidence_needed="Ticket details, logs, alerts for the system",
                    recommended_action="Open an investigation; group signals by root cause only once evidence supports it.")

    # 13. Cloud dependency & 15. Backup / recovery -----------------------------
    if track.get("continuity", True):
        for cs in db.t_rows("cloud_services", cid):
            if cs["criticality"] != "Critical":
                continue
            if (cs["outages_12m"] or 0) >= 2:
                add(rule_key=f"cloud:{cs['id']}", category="Technology / continuity", case_category="1. Cloud infrastructure dependency",
                    probability=_c(2 + cs["outages_12m"] // 2), impact=5, owner=cs["owner"] or "IT / Operations",
                    evidence_status="Warning signal",
                    title=f"Critical cloud dependency: {cs['name']}", title_fr=f"Dépendance cloud critique : {cs['name']}",
                    explanation=f"{cs['name']} ({cs['provider']}) is critical and had {cs['outages_12m']} recorded outage(s) in 12 months. Links to case risk R1.",
                    explanation_fr=f"{cs['name']} ({cs['provider']}) est critique et a connu {cs['outages_12m']} panne(s) en 12 mois. Lié au risque R1.",
                    evidence_needed="Provider SLA, outage history, dependency map",
                    recommended_action="Confirm RTO/RPO, review redundancy, prepare an outage communication plan.")
            lr = _d(cs["last_restore_test"])
            if not lr or lr < ref - timedelta(days=180):
                add(rule_key=f"backup:{cs['id']}", category="Continuity / resilience", case_category="1. Cloud infrastructure dependency",
                    probability=3, impact=5, owner=cs["owner"] or "IT", evidence_status="Warning signal",
                    title=f"No recent restore test: {cs['name']}", title_fr=f"Pas de test de restauration récent : {cs['name']}",
                    explanation=f"Last restore test recorded for {cs['name']}: {lr or 'never'}. Recovery cannot be demonstrated. Links to case risk R10.",
                    explanation_fr=f"Dernier test de restauration de {cs['name']} : {lr or 'jamais'}. La reprise ne peut pas être démontrée. Lié au risque R10.",
                    evidence_needed="Backup logs, restore test report",
                    recommended_action="Run and document a restore test against the agreed RTO/RPO.")

    # 14. Security configuration weaknesses ------------------------------------
    if track.get("cyber", True):
        for tl in db.t_rows("digital_tools", cid):
            cr = _d(tl["config_review_date"])
            shadow = tl["approved"] != "Approved"
            if shadow or not cr or cr < ref - timedelta(days=365):
                add(rule_key=f"tool:{tl['id']}", category="Cybersecurity / change management", case_category="4. New digital tools",
                    probability=4 if shadow else 3, impact=4, owner=tl["owner"] or "IT", evidence_status="Warning signal",
                    title=f"Tool configuration not reviewed: {tl['name']}", title_fr=f"Configuration d'outil non revue : {tl['name']}",
                    explanation=(f"{tl['name']}: approval status '{tl['approved']}', last configuration review {cr or 'never'}. "
                                 "Links to case risk R3."),
                    explanation_fr=(f"{tl['name']} : statut « {tl['approved']} », dernière revue de configuration {cr or 'jamais'}. "
                                    "Lié au risque R3."),
                    evidence_needed="Tool inventory, configuration baseline, change records",
                    recommended_action="Assign an owner, run a configuration review, decide approve / remediate / retire.")
        emps_df = db.t_df("employees", cid, "active = 1 AND remote_eligible = 1")
        if not emps_df.empty:
            unverified = emps_df[emps_df["mfa_status"] != "Verified"]
            if len(unverified):
                add(rule_key="remote:mfa", category="Cybersecurity / identity", case_category="2. Remote working",
                    probability=4, impact=5, owner="IT / Security", evidence_status="Warning signal",
                    title="Remote workers without verified MFA", title_fr="Télétravailleurs sans MFA vérifiée",
                    explanation=f"{len(unverified)} of {len(emps_df)} remote-eligible employees have no verified MFA status recorded. "
                                "The control may exist but is not evidenced. Links to case risk R2.",
                    explanation_fr=f"{len(unverified)} des {len(emps_df)} salariés éligibles au télétravail n'ont pas de MFA vérifiée enregistrée. "
                                   "Le contrôle existe peut-être mais n'est pas prouvé. Lié au risque R2.",
                    evidence_needed="MFA coverage report from the identity provider",
                    recommended_action="Export MFA status from the identity provider and record verification per employee.")
    return out


def run(cid: int, user: str = "rule-engine") -> dict:
    """Upsert findings into the risk register. Returns counts."""
    findings = detect(cid)
    existing = {r["rule_key"]: r for r in db.t_rows("risks", cid, "rule_key IS NOT NULL")}
    seen, created, updated, cleared = set(), 0, 0, 0
    next_no = (db.scalar("SELECT COUNT(*) FROM risks WHERE company_id = ? AND source = 'Rule engine'", (cid,)) or 0) + 1
    for f in findings:
        k = f["rule_key"]
        seen.add(k)
        data = {x: f.get(x) for x in ("title", "title_fr", "category", "case_category", "probability", "impact",
                                     "project_id", "employee_id", "explanation", "explanation_fr",
                                     "evidence_needed", "recommended_action")}
        data["updated_at"] = db.now()
        if k in existing:
            r = existing[k]
            if r["status"] in ("Condition cleared", "Resolved"):
                data.update(status="Open", resolved_at=None)
            db.t_update("risks", cid, r["id"], data)
            updated += 1
        else:
            data.update(code=f"A-{next_no:03d}", status="Open", evidence_status=f["evidence_status"],
                        source="Rule engine", rule_key=k, owner=f["owner"], created_at=db.now())
            next_no += 1
            db.t_insert("risks", cid, data)
            created += 1
            if f["probability"] * f["impact"] >= 20:
                from . import notify
                notify.notify(cid, "critical_risk", f"Critical risk raised: {f['title']}", f["explanation"], "high")
    for k, r in existing.items():
        if k not in seen and r["status"] in OPEN_STATUSES:
            db.t_update("risks", cid, r["id"], {"status": "Condition cleared", "updated_at": db.now()})
            cleared += 1
    return {"created": created, "updated": updated, "cleared": cleared, "findings": len(findings)}


def register(cid: int, lang: str = "en") -> pd.DataFrame:
    r = db.df("""SELECT r.*, p.code AS project_code FROM risks r LEFT JOIN projects p ON p.id = r.project_id
                 WHERE r.company_id = ? ORDER BY (r.probability * r.impact) DESC, r.code""", (cid,))
    if r.empty:
        return r
    r["score"] = r["probability"] * r["impact"]
    r["priority"] = r["score"].apply(lambda s: priority(int(s), cid))
    if lang == "fr":
        r["display_title"] = r["title_fr"].fillna("").where(r["title_fr"].fillna("") != "", r["title"])
        r["display_explanation"] = r["explanation_fr"].fillna("").where(r["explanation_fr"].fillna("") != "", r["explanation"])
    else:
        r["display_title"] = r["title"]
        r["display_explanation"] = r["explanation"]
    return r


def trend(cid: int, weeks: int = 12) -> pd.DataFrame:
    """Open risks by priority at the end of each of the last N weeks, derived from created/resolved dates."""
    r = register(cid)
    if r.empty:
        return pd.DataFrame()
    r["c"] = pd.to_datetime(r["created_at"], errors="coerce")
    r["res"] = pd.to_datetime(r["resolved_at"], errors="coerce")
    r.loc[r["status"].isin(["Resolved", "Condition cleared"]) & r["res"].isna(), "res"] = pd.to_datetime(r["updated_at"], errors="coerce")
    today = pd.Timestamp(date.today())
    rows = []
    for w in range(weeks - 1, -1, -1):
        t = today - pd.Timedelta(days=7 * w)
        open_at = r[(r["c"] <= t) & (r["res"].isna() | (r["res"] > t))]
        for pr in ["Critical", "High", "Medium", "Low"]:
            rows.append({"week": t.date(), "priority": pr, "count": int((open_at["priority"] == pr).sum())})
    return pd.DataFrame(rows)
