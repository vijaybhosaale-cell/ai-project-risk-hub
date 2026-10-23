"""Walk a newly registered company through the 9-step setup wizard."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["HUB_DB_PATH"] = os.path.join(tempfile.gettempdir(), "hub_wiz.db")
import smoke_patch  # noqa
from streamlit.testing.v1 import AppTest
from hub import db, seed, auth
if os.path.exists(db.DB_PATH): os.remove(db.DB_PATH)
seed.ensure_demo()
cid = db.execute("INSERT INTO companies (name, currency, language, setup_complete, created_at) VALUES ('Wizard Co','EUR','en',0,?)", (db.now(),))
uid = auth.create_user(cid, "Wanda", "wanda@wiz.example", "Password1234", "Company Administrator")
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
at = AppTest.from_file("../app.py", default_timeout=90); at.session_state["user"] = {"id": uid}; at.run()
ok(any("Company settings" in x.value for x in at.title) and not at.exception, "wizard opens first")
def submit(label):
    [b for b in at.button if b.label.startswith(label)][0].click().run()
    if at.exception: print("   EXC", at.exception[0].message[:200])
def ti(label): return [t for t in at.text_input if t.label.startswith(label)][0]
def step(n):
    [b for b in at.button if b.label == str(n)][0].click().run()
ti("Industry").set_value("IT services"); submit("Save and continue")
ok(at.session_state["wiz_step"] == 1, "step 1 saved -> step 2")
ti("Location name").set_value("Paris"); submit("Add location")
ok(db.scalar("SELECT COUNT(*) FROM locations WHERE company_id=?", (cid,)) == 1, "location added")
step(3); ti("Name").set_value("Eve Dev"); ti("Skills").set_value("Python"); submit("Add employee")
ti("Name").set_value("Max Ops"); submit("Add employee")
ok(db.scalar("SELECT COUNT(*) FROM employees WHERE company_id=?", (cid,)) == 2, "employees added")
step(5); ti("Client name").set_value("Client One"); submit("Add client")
ok(db.scalar("SELECT COUNT(*) FROM clients WHERE company_id=?", (cid,)) == 1, "client added")
step(4); ti("Project name").set_value("Portal"); [m for m in at.multiselect if m.label == "Team members"][0].set_value([e["id"] for e in db.t_rows("employees", cid)])
submit("Add project")
ok(db.scalar("SELECT COUNT(*) FROM projects WHERE company_id=?", (cid,)) == 1 and db.scalar("SELECT COUNT(*) FROM allocations WHERE company_id=?", (cid,)) == 2, "project + team allocations added")
step(6); ti("Subcontractor name").set_value("Sub One"); submit("Add subcontractor")
ok(db.scalar("SELECT COUNT(*) FROM subcontractors WHERE company_id=?", (cid,)) == 1, "subcontractor added")
step(7); submit("Save and continue")
step(8); submit("Save notification settings")
step(9); submit("✅")
ok(db.company(cid)["setup_complete"] == 1 and any("dashboard" in x.value.lower() for x in at.title) and not at.exception, "setup completed -> dashboard")
ok(db.scalar("SELECT COUNT(*) FROM employees WHERE company_id=?", (seed and cid,)) == 2 and db.scalar("SELECT COUNT(*) FROM employees WHERE company_id != ?", (cid,)) == 88, "data stays per company")
