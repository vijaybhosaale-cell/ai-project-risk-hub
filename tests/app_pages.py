"""Helper for tests: page keys visible to a role (mirrors app.allowed_pages)."""
from hub import perms
KEYS = ["getting_started","dashboard","my_work","allocation","risks","gantt","projects","tasks","employees","absences","budget",
        "risk_areas","onboarding","access","subcontractors","clients","gdpr","notifications","reports","audit","users","settings","security","platform"]
def keys_for(role):
    return [k for k in KEYS if (k == "getting_started" and role != "Platform Administrator") or (k != "getting_started" and perms.can_view(role, k))]
