"""Click every button / form-submit on every page (as company admin) and check nothing crashes."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["HUB_DB_PATH"] = os.path.join(tempfile.gettempdir(), "hub_click.db")
import smoke_patch  # noqa
from streamlit.testing.v1 import AppTest
from hub import db, seed
import app_pages
if os.path.exists(db.DB_PATH): os.remove(db.DB_PATH)
seed.ensure_demo()
SKIP = {"Sign out", "↩ Sign out", "♻️ Reset demo data"}
who = sys.argv[1] if len(sys.argv) > 1 else "admin"
u = db.one("SELECT * FROM users WHERE email=?", (f"{who}@novatech-demo.example",))
only = [x for x in os.environ.get("PAGES", "").split(",") if x]
fails = 0
def fresh(page):
    at = AppTest.from_file("../app.py", default_timeout=90)
    at.session_state["user"] = {"id": u["id"]}; at.session_state["nav"] = page; at.session_state["wizard_seen"] = True
    at.run(); return at
for page in app_pages.keys_for(u["role"]):
    if only and page not in only: continue
    at = fresh(page)
    labels = [b.label for b in at.button]
    for i, lab in enumerate(labels):
        if lab in SKIP or lab.startswith("↩"): continue
        at = fresh(page)
        try:
            at.button[i].click().run()
        except Exception as e:
            print("HARNESS", page, lab, str(e)[:120]); continue
        if at.exception:
            fails += 1
            print("FAIL", page, repr(lab), at.exception[0].message[:200]); print("   ", at.exception[0].stack_trace[-2:])
    print("ok", page, len(labels), "buttons")
print("FAILURES", fails)
