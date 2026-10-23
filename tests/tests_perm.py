from hub import perms
def check(): pass
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ok(not perms.can_view("Employee", "dashboard") and not perms.can_view("Employee", "allocation"), "employee has no dashboard/allocation access")
ok(not perms.can_edit("Team Leader", "projects") and perms.can_edit("Project Manager", "projects"), "edit rights follow role")
ok(not perms.can_view("Subcontractor", "employees"), "subcontractor cannot see employees")
