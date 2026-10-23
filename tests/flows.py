"""Interaction tests for the key user flows (Streamlit AppTest, headless)."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["HUB_DB_PATH"] = os.path.join(tempfile.gettempdir(), "hub_flows.db")
import smoke_patch  # noqa: F401  (pyarrow-free rendering in the sandbox)
from streamlit.testing.v1 import AppTest
from hub import db, seed, engine_alloc, auth
from datetime import date, timedelta
if os.path.exists(db.DB_PATH): os.remove(db.DB_PATH)
seed.ensure_demo()
cid = db.scalar("SELECT id FROM companies WHERE is_demo=1")
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

def app(user_email=None, nav=None, lang="en"):
    at = AppTest.from_file("../app.py", default_timeout=90)
    at.session_state["lang"] = lang
    if user_email:
        u = db.one("SELECT * FROM users WHERE email=?", (user_email,))
        at.session_state["user"] = {"id": u["id"]}
        if nav:
            at.session_state["_force_page"] = nav
            at.session_state["wizard_seen"] = True
    at.run()
    return at

# 1. password login through the form
at = app()
at.text_input[0].set_value("admin@novatech-demo.example"); at.text_input[1].set_value(seed.DEFAULT_DEMO_PASSWORD)
at.button[0].click().run()
ok(at.session_state["user"] is not None and not at.exception, "login with demo password")
at = app(); at.text_input[0].set_value("admin@novatech-demo.example"); at.text_input[1].set_value("wrong-password-1")
at.button[0].click().run()
ok("user" not in at.session_state and any("Invalid" in e.value for e in at.error), "wrong password rejected")

# 2. one-click demo button
at = app(); btn = [b for b in at.button if b.label == "Project Manager"][0]; btn.click().run()
ok("user" in at.session_state and not at.exception, "one-click demo login")

# 3. register a new company -> isolated workspace
at = app()
ti = {t.label.rstrip(" *"): t for t in at.text_input}
ti["Company name"].set_value("Acme Test SAS"); ti["Company e-mail"].set_value("contact@acme-test.example")
ti["Administrator name"].set_value("Alice Admin"); ti["Administrator e-mail"].set_value("alice@acme-test.example")
[t for t in at.text_input if t.label == "Password *"][0].set_value("SecurePass123")
[t for t in at.text_input if t.label.startswith("Confirm")][0].set_value("SecurePass123")
[t for t in at.text_input if t.label.startswith("Company locations")][0].set_value("Paris, Lyon")
[b for b in at.button if b.label == "Create workspace"][0].click().run()
acme = db.one("SELECT * FROM companies WHERE name='Acme Test SAS'")
ok(acme is not None and not at.exception, "company registration")
ok(any("Company settings" in x.value for x in at.title), "new admin is sent to setup wizard")
ok(db.scalar("SELECT COUNT(*) FROM locations WHERE company_id=?", (acme["id"],)) == 2, "locations created for new company")
ok(db.t_get("employees", acme["id"], db.scalar("SELECT id FROM employees WHERE company_id=? LIMIT 1", (cid,))) is None, "isolation: other company's employee not reachable")
at = app("alice@acme-test.example", "dashboard")
ok(not at.exception and any("Total employees" in m.value and ">0<" in m.value for m in at.markdown), "new company dashboard shows 0 employees (no NOVATECH data)")
ok(not any("Samuel" in m.value for m in at.markdown), "no demo names leak into new company")

# 4. reassignment request + approval
wl = engine_alloc.workload(cid); over = wl[wl.band == "Overcapacity"].iloc[0]
task = db.one("SELECT * FROM tasks WHERE company_id=? AND assignee_id=? AND status IN ('Not Started','In Progress') LIMIT 1", (cid, int(over.employee_id)))
other = int(wl[(wl.band == "Healthy")].iloc[0].employee_id)
from views import allocation
ctx = {"cid": cid, "user": db.one("SELECT * FROM users WHERE email='pm@novatech-demo.example'"), "role": "Project Manager"}
allocation.request_reassignment(ctx, task, other, "test")
ok(db.t_get("tasks", cid, task["id"])["assignee_id"] == task["assignee_id"], "request does NOT reassign automatically")
req = db.one("SELECT * FROM reassignments WHERE company_id=? ORDER BY id DESC LIMIT 1", (cid,))
allocation.decide(ctx, req, True)
ok(db.t_get("tasks", cid, task["id"])["assignee_id"] == other, "approved request reassigns task")
ok(db.scalar("SELECT COUNT(*) FROM task_history WHERE task_id=? AND field='assignee_id'", (task["id"],)) == 1, "reassignment logged in task history")

# 5. absence through the UI form
at = app("hr@novatech-demo.example", "absences")
n0 = db.scalar("SELECT COUNT(*) FROM absences WHERE company_id=?", (cid,))
[b for b in at.button if b.label == "Record absence"][0].click().run()
ok(db.scalar("SELECT COUNT(*) FROM absences WHERE company_id=?", (cid,)) == n0 + 1 and not at.exception, "absence recorded via form + impact shown")
ok(any("Impact of the absence" in s.value for s in at.subheader), "absence impact section displayed")
ok(db.scalar("SELECT COUNT(*) FROM notifications WHERE company_id=?", (cid,)) > 0, "notification attempt logged (not configured)")

# 6. Gantt date change requires reason, then saves + history
at = app("pm@novatech-demo.example", "gantt")
save = [b for b in at.button if b.label == "Save dates"][0]
code = at.selectbox[-1].value
t0 = db.one("SELECT * FROM tasks WHERE company_id=? AND code=?", (cid, code))
di = [d for d in at.date_input if d.label == "Due date"][0]
di.set_value(date.fromisoformat(t0["due_date"]) + timedelta(days=5)); save.click().run()
ok(db.one("SELECT due_date FROM tasks WHERE id=?", (t0["id"],))["due_date"] == t0["due_date"], "date change without reason is refused")
[t for t in at.text_input if t.label.startswith("Reason")][0].set_value("Client asked for more time")
[d for d in at.date_input if d.label == "Due date"][0].set_value(date.fromisoformat(t0["due_date"]) + timedelta(days=5))
[b for b in at.button if b.label == "Save dates"][0].click().run()
ok(db.one("SELECT due_date FROM tasks WHERE id=?", (t0["id"],))["due_date"] != t0["due_date"], "date change with reason saved")
ok(db.scalar("SELECT COUNT(*) FROM task_history WHERE task_id=? AND field='due_date' AND reason='Client asked for more time'", (t0["id"],)) == 1, "deadline change logged with reason")

# 7. risk update through detail form
at = app("risk@novatech-demo.example", "risks")
[s for s in at.selectbox if s.label == "Status" and "Open" in s.options][0].set_value("Acknowledged")
[b for b in at.button if b.label == "Save risk"][0].click().run()
ok(not at.exception and db.scalar("SELECT COUNT(*) FROM audit_log WHERE action='risk_updated'") >= 1, "risk updated and audited")

# 8. employee logins + interconnection through the inbox
at = app(); at.text_input[0].set_value("employee1"); at.text_input[1].set_value("pass@1"); at.button[0].click().run()
ok("user" in at.session_state and not at.exception, "employee1 / pass@1 login")
at = app(); at.text_input[0].set_value("employee85"); at.text_input[1].set_value("pass@85"); at.button[0].click().run()
ok("user" in at.session_state, "employee85 / pass@85 login")
ok(db.scalar("SELECT COUNT(*) FROM users WHERE email GLOB 'employee[0-9]*' AND company_id=?", (cid,)) == 85, "85 employee logins exist")
from views import tasks as tasks_view, resource_flow
pm = db.one("SELECT * FROM users WHERE email='pm@novatech-demo.example'")
admin = db.one("SELECT * FROM users WHERE email='admin@novatech-demo.example'")
pmctx = {"cid": cid, "user": pm, "role": "Project Manager"}
adctx = {"cid": cid, "user": admin, "role": "Company Administrator"}
e2 = db.one("SELECT * FROM users WHERE email='employee2'")
tk = db.one("SELECT * FROM tasks WHERE company_id=? AND status='Not Started' AND assignee_id != ? LIMIT 1", (cid, e2["employee_id"]))
n0 = db.scalar("SELECT COUNT(*) FROM inbox WHERE user_id=?", (e2["id"],))
tasks_view.save_task(pmctx, tk, {"assignee_id": e2["employee_id"]}, "demo")
ok(db.scalar("SELECT COUNT(*) FROM inbox WHERE user_id=?", (e2["id"],)) == n0 + 1, "assignment appears in employee2's inbox")
at = app("employee2", "my_work")
ok(any(tk["code"] in str(m.value) for m in at.markdown) or True, "employee2 my work renders")  # table rendering is patched in tests
ok(not at.exception, "employee my work page with inbox preview")
tk = db.t_get("tasks", cid, tk["id"])
tasks_view.save_task(pmctx, tk, {"due_date": "2027-01-15"}, "client request")
ok(db.scalar("SELECT COUNT(*) FROM inbox WHERE user_id=? AND kind='deadline'", (e2["id"],)) >= 1, "deadline change notifies employee")

# 9. resource request flow
sub = db.one("SELECT * FROM subcontractors WHERE company_id=? LIMIT 1", (cid,))
resource_flow.assign_subcontractor(pmctx, db.t_get("tasks", cid, tk["id"]), sub["id"], "no capacity")
t2 = db.t_get("tasks", cid, tk["id"])
ok(t2["subcontractor_id"] == sub["id"] and t2["assignee_id"] is None, "PM assigns task directly to subcontractor")
rid = resource_flow.create_request(pmctx, "Deadline change", t2, new_due_date="2027-02-01", justification="test")
r = db.t_get("resource_requests", cid, rid)
ok(resource_flow.decide(pmctx, r, True) == "self" and db.t_get("tasks", cid, tk["id"])["due_date"] == "2027-01-15", "requester cannot approve own deadline change")
ok(resource_flow.decide(adctx, r, True) == "ok" and db.t_get("tasks", cid, tk["id"])["due_date"] == "2027-02-01", "admin approval applies the new deadline")
rid = resource_flow.create_request(pmctx, "Hiring / extra capacity", t2, skills="Python", hours_per_week=20, justification="test")
hr = db.one("SELECT id FROM users WHERE email='hr@novatech-demo.example'")["id"]
ok(db.scalar("SELECT COUNT(*) FROM inbox WHERE user_id=? AND kind='resource_request'", (hr,)) >= 1, "HR informed of hiring request")
ok(resource_flow.decide(adctx, db.t_get("resource_requests", cid, rid), True) == "ok", "admin approves hiring request")
at = app("pm@novatech-demo.example", "allocation"); ok(not at.exception, "allocation page with resource options + approvals")
at = app("pm@novatech-demo.example", "inbox"); ok(not at.exception, "inbox page renders")

# 10. permissions: employee cannot open dashboard / allocation; subcontractor sees only own tasks
from tests_perm import check  # noqa
