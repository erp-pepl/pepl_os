# PEPL OS v0.62.0 - CR2 set-up: tender data open only to the three Tender Access users.
# System Console, Type = Python, **Commit TICKED** (this one saves). Safe to run again.
# Log in as **Administrator** to run it (after CR2 nobody else, System Managers included, opens tender data).
# Before running: the list must already be in the site configuration (bench: set-config; Frappe Cloud: Site Config),
# key pepl_tender_access_users = the three emails below. This script never changes that list; it applies it:
#  1. Stops if the site configuration does not hold exactly the three emails, or a login is missing.
#  2. Rights: PEPL Tender Access = full rights on PEPL Tender and PEPL CST Cost Sheet; Sales Order Tender Reference
#     and NIT Number at level 1 (only PEPL Tender Access reads them); the CEO's view of tenders removed.
#  3. The role PEPL Tender Access given to exactly the three.
#  4. Role Profile "PEPL Tender Only" added to each of the three (a user without profiles gets its two roles instead).
#  5. Open ToDos on a tender / Cost Sheet held by anyone else go to the first of the three.
#  6. Shares of a tender / Cost Sheet with anyone else are removed.
EXPECTED = ["ankit@parasramkagroup.com", "sudam@parasramkagroup.com", "aviral@parasramkagroup.com"]
CREATE_MISSING_LOGINS = 0  # local bench only: 1 creates the three logins (no e-mail sent); keep 0 on demo / live
TA = "pepl_os.pepl_governance.tender_access"
GATED = ["PEPL Tender", "PEPL CST Cost Sheet"]
PROFILE = "PEPL Tender Only"

apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
print("pepl_os " + str(apps.get("pepl_os")) + ", run by " + frappe.session.user)
problems = []
if frappe.session.user != "Administrator":
    problems.append("log in as Administrator and run again")

status = frappe.call(TA + ".access_status")
listed = status.get("listed") or []
print("Site configuration pepl_tender_access_users: " + (", ".join(listed) or "(empty - restriction OFF)"))
if sorted(listed) != sorted([e.lower() for e in EXPECTED]):
    problems.append("the site configuration must list exactly: " + ", ".join(EXPECTED) + " (see the CR2 guide, step 2)")

profile_field = (frappe.get_all("DocField", filters={"parent": "User", "options": "User Role Profile"}, pluck="fieldname") or [None])[0]
for email in EXPECTED:
    if not frappe.db.exists("User", email):
        if CREATE_MISSING_LOGINS:
            values = {"doctype": "User", "email": email, "first_name": email.split("@")[0].title(), "send_welcome_email": 0, "enabled": 1}
            if profile_field:
                values[profile_field] = [{"role_profile": PROFILE}]
            else:
                values["role_profile_name"] = PROFILE
            frappe.get_doc(values).insert()
            print("Created login " + email + " (Role Profile " + PROFILE + "; set a password in the User form)")
        else:
            problems.append("no login " + email + ": create it (User list > Add User) or set CREATE_MISSING_LOGINS = 1 on the bench")
    elif not frappe.db.get_value("User", email, "enabled"):
        problems.append("login " + email + " is disabled")

if problems:
    for p in problems:
        print("STOP  " + p)
    print("Nothing was changed. Fix the line(s) above and run again.")
else:
    result = frappe.call(TA + ".sync_now")
    print("2. Rights changed: " + (", ".join(result.get("rights")) or "none (already in place)"))
    print("   Sales Order fields moved to level 1: " + (", ".join(result.get("sales_order_fields")) or "none (already there)"))
    role = result.get("role")
    print("3. PEPL Tender Access given to: " + (", ".join(role.get("added")) or "nobody new") + "; taken from: " + (", ".join(role.get("removed")) or "nobody"))

    for email in EXPECTED:
        user = frappe.get_doc("User", email)
        profiles = frappe.get_all("User Role Profile", filters={"parent": user.name, "parenttype": "User"}, pluck="role_profile")
        if PROFILE in profiles:
            print("4. " + email + ": already has " + PROFILE)
        elif profile_field and profiles:
            user.append(profile_field, {"role_profile": PROFILE})
            user.save()
            print("4. " + email + ": " + PROFILE + " added (profiles now " + ", ".join(profiles + [PROFILE]) + ")")
        else:
            have = frappe.get_roles(user.name)
            missing = [r for r in ["PEPL Tender Manager", "Sales User"] if r not in have]
            for r in missing:
                user.append("roles", {"role": r})
            if missing:
                user.save()
            print("4. " + email + ": roles set by hand (no Role Profile); added " + (", ".join(missing) or "nothing (already there)"))
        print("   roles: " + ", ".join(sorted(frappe.get_roles(user.name))))

    moved = 0
    for t in frappe.get_all("ToDo", filters={"reference_type": ["in", GATED], "status": "Open"}, fields=["name", "allocated_to"]):
        if (t.allocated_to or "").lower() not in listed and t.allocated_to != "Administrator":
            todo = frappe.get_doc("ToDo", t.name)
            todo.save()  # PEPL moves it to the first listed user
            moved += 1
            print("5. ToDo " + t.name + ": " + str(t.allocated_to) + " -> " + str(frappe.db.get_value("ToDo", t.name, "allocated_to")))
    if not moved:
        print("5. No open tender ToDo held by anyone else")

    removed = 0
    for s in frappe.get_all("DocShare", filters={"share_doctype": ["in", GATED]}, fields=["name", "user", "everyone", "share_doctype", "share_name"]):
        if s.everyone or (s.user or "").lower() not in listed:
            frappe.delete_doc("DocShare", s.name, ignore_permissions=True)
            removed += 1
            print("6. Share removed: " + s.share_doctype + " " + s.share_name + " with " + ("everyone" if s.everyone else str(s.user)))
    if not removed:
        print("6. No share of a tender / Cost Sheet with anyone else")

    for n in frappe.get_all("Notification", filters={"document_type": ["in", GATED], "enabled": 1}, pluck="name"):
        print("INFO  e-mail Notification '" + n + "' is set on tender data: open it and make sure it goes only to the three")
    print("Done. Commit was ticked, so this is saved. Now run Check 62 (Commit unticked).")
