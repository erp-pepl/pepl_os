# PEPL OS v0.79.4 - setup_cr3_logins rev 2: one named login per person, with the Role Profiles PEPL signed off in the
# Access Planning Pack (tab "6 People"). System Console, Type = Python, logged in as Administrator.
#
# 1. Paste the people into PEOPLE below (the consultant's filled copy is kept OUTSIDE the repository: it holds
#    names, e-mails and mobile numbers).
# 2. Run with DRY_RUN = 1 and Commit UNTICKED: it only prints what it would do and every problem found.
# 3. When it prints "READY", set DRY_RUN = 0, tick Commit, Execute again.
# Safe to run again: an existing login gets exactly the profiles listed here (other profiles are taken off).
# No password is set and no e-mail is sent unless SEND_WELCOME_EMAIL = 1 (needs the outgoing e-mail account).
DRY_RUN = 1
SEND_WELCOME_EMAIL = 0
# Logins that also get System Manager (Decision 10), through the Role Profile "PEPL System Manager". They need the
# two-factor code once two-factor login is switched on (see docs/cr3_access_plan_guide.md, step 6).
SYSTEM_MANAGERS = []
# [full name, login e-mail, mobile, [job profile, more profiles or add-ons ...]]
PEOPLE = [
    # ["Ramesh Kumar", "ramesh.kumar@example.com", "98XXXXXXXX", ["PEPL Stores"]],
]

ADD_ONS = ["PEPL Item Master", "PEPL Supplier Master", "PEPL Sales Invoicing"]
SM_PROFILE = "PEPL System Manager"
GENERIC = ["stores", "store", "purchase", "accounts", "account", "admin", "hr", "office", "info", "sales", "production", "quality", "dispatch"]
problems = []
warnings = []

profile_field = (frappe.get_all("DocField", filters={"parent": "User", "options": "User Role Profile"}, pluck="fieldname") or [None])[0]
if frappe.session.user != "Administrator":
    problems.append("run this as Administrator (now: " + frappe.session.user + ")")
if not profile_field:
    problems.append("this ERPNext has no multi-profile field on User (User Role Profile); tell the consultant")

listed = []
try:
    listed = frappe.call("pepl_os.pepl_governance.tender_access.access_status").get("listed") or []
except Exception as e:
    warnings.append("could not read the tender access list: " + str(e))

seen = []
for row in PEOPLE:
    # One name per line: the System Console does not allow "a, b = ..." (NameError _unpack_sequence_).
    name = row[0]
    email = (row[1] or "").strip().lower()
    mobile = row[2]
    profiles = row[3]
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        problems.append(name + ": no valid login e-mail (" + str(row[1]) + ")")
        continue
    if email in seen:
        problems.append(email + " is listed twice")
    seen.append(email)
    if not profiles:
        problems.append(email + ": no profile")
    for p in profiles:
        if not frappe.db.exists("Role Profile", p):
            problems.append(email + ": Role Profile '" + p + "' does not exist (deploy 0.79.0 first)")
    if profiles and all(p in ADD_ONS for p in profiles):
        problems.append(email + ": only add-on profiles; give a job profile too")
    if email.split("@")[0].split(".")[0] in GENERIC:
        warnings.append(email + " looks like a shared mailbox: PEPL confirmed it is used by " + name + " alone?")
    if "PEPL Tender Only" in profiles and email not in listed:
        warnings.append(email + " has PEPL Tender Only but is not in the tender access list: tenders will not open for this login")
    if email in listed and "PEPL Tender Only" not in profiles:
        warnings.append(email + " is in the tender access list but has no PEPL Tender Only: can open tenders, cannot make their Sales Orders")
for email in SYSTEM_MANAGERS:
    if email.lower() not in seen:
        problems.append("System Manager " + email + " is not in PEOPLE")

for w in warnings:
    print("WARN  " + w)
for p in problems:
    print("STOP  " + p)
print("")
print(str(len(PEOPLE)) + " people, " + str(len(problems)) + " problem(s), " + str(len(warnings)) + " warning(s)")

if problems:
    print("Nothing done: fix the STOP lines first.")
elif DRY_RUN:
    for row in PEOPLE:
        email = row[1].strip().lower()
        action = "update" if frappe.db.exists("User", email) else "create"
        extra = [SM_PROFILE] if email in [s.lower() for s in SYSTEM_MANAGERS] else []
        print("WOULD " + action + " " + email + " (" + row[0] + "): " + ", ".join(row[3] + extra))
    print("READY - set DRY_RUN = 0, tick Commit, Execute again.")
else:
    if SYSTEM_MANAGERS and not frappe.db.exists("Role Profile", SM_PROFILE):
        frappe.get_doc({"doctype": "Role Profile", "role_profile": SM_PROFILE, "roles": [{"role": "System Manager"}]}).insert()
        print("Created Role Profile " + SM_PROFILE + " (System Manager)")
    for row in PEOPLE:
        name = row[0]
        email = row[1].strip().lower()
        mobile = row[2]
        profiles = list(row[3])
        if email in [s.lower() for s in SYSTEM_MANAGERS]:
            profiles.append(SM_PROFILE)
        parts = name.split(" ", 1)
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
            user.set(profile_field, [{"role_profile": p} for p in profiles])
            user.enabled = 1
            if mobile and not user.mobile_no:
                user.mobile_no = mobile
            user.save()
            print("Updated " + email)
        else:
            values = {
                "doctype": "User",
                "email": email,
                "first_name": parts[0],
                "last_name": parts[1] if len(parts) > 1 else "",
                "mobile_no": mobile or "",
                "user_type": "System User",
                "enabled": 1,
                "send_welcome_email": SEND_WELCOME_EMAIL,
                profile_field: [{"role_profile": p} for p in profiles],
            }
            frappe.get_doc(values).insert()
            print("Created " + email)
    print("")
    for row in PEOPLE:
        email = row[1].strip().lower()
        have = frappe.get_all("User Role Profile", filters={"parent": email, "parenttype": "User"}, pluck="role_profile")
        roles = frappe.get_all("Has Role", filters={"parent": email, "parenttype": "User"}, pluck="role")
        print(email + "  profiles: " + ", ".join(sorted(have)) + "  |  roles: " + str(len(roles)))
    print("DONE - Commit must be ticked for this to be saved.")
