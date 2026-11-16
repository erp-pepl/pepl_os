# PEPL OS v0.62.1 - Check 62: CR2 - tender data (PEPL Tender, PEPL CST Cost Sheet) open only to the three
# Tender Access users; tender Sales Orders open to everyone, their Tender Reference / NIT Number hidden.
# Runs on 0.62.1 or later, after setup_cr2.py. System Console, Type = Python, logged in as **Administrator**.
# Leave "Commit" UNTICKED: the test assignment in section 8 is undone at the end.
VERSION = "0.62.1"
TA = "pepl_os.pepl_governance.tender_access"
EXPECTED = ["ankit@parasramkagroup.com", "sudam@parasramkagroup.com", "aviral@parasramkagroup.com"]
ROLE = "PEPL Tender Access"
GATED = ["PEPL Tender", "PEPL CST Cost Sheet"]
passed = []
failed = []


def check(ok, label):
    if ok:
        passed.append(label)
        print("PASS  " + label)
    else:
        failed.append(label)
        print("FAIL  " + label)


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


def perm(doctype, role, level=0):
    rows = frappe.get_all("Custom DocPerm", filters={"parent": doctype, "role": role, "permlevel": level},
                          fields=["read", "write", "create", "delete", "submit"])
    return rows[0] if rows else None


expected = sorted([e.lower() for e in EXPECTED])
installed = frappe.db.get_value("Installed Application", {"app_name": "pepl_os"}, "app_version")

# ---------------- 1. installed, run by Administrator, the list in the site configuration ----------------
check(version_parts(installed) >= version_parts(VERSION), "1. pepl_os " + str(installed) + " installed (needs " + VERSION + ")")
check(frappe.session.user == "Administrator", "1. run by Administrator (run by " + frappe.session.user + ")")
status = frappe.call(TA + ".access_status")
check(status.get("active"), "1. restriction is ON (site configuration pepl_tender_access_users is set)")
check(sorted(status.get("listed") or []) == expected, "1. the list is exactly the three: " + ", ".join(status.get("listed") or []))
check(not status.get("not_a_user") and not status.get("disabled"),
      "1. all three are enabled logins (missing: " + str(status.get("not_a_user")) + ", disabled: " + str(status.get("disabled")) + ")")

# ---------------- 2. the role ----------------
holders = sorted([h.lower() for h in status.get("role_holders") or []])
check(holders == expected, "2. " + ROLE + " held by exactly the three: " + ", ".join(holders))
in_profiles = frappe.get_all("Has Role", filters={"role": ROLE, "parenttype": "Role Profile"}, pluck="parent")
check(not in_profiles, "2. " + ROLE + " is in no Role Profile (" + ", ".join(in_profiles) + ")")

# ---------------- 3. rights ----------------
t = perm("PEPL Tender", ROLE)
check(bool(t) and t.read and t.write and t.create and t.delete and t.submit, "3. " + ROLE + ": read, write, create, delete, submit on PEPL Tender")
c = perm("PEPL CST Cost Sheet", ROLE)
check(bool(c) and c.read and c.write and c.create and c.delete, "3. " + ROLE + ": read, write, create, delete on PEPL CST Cost Sheet")
for doctype in GATED:
    check(not perm(doctype, "PEPL CEO"), "3. the CEO has no view of " + doctype)
level1 = frappe.get_all("Custom DocPerm", filters={"parent": "Sales Order", "permlevel": 1, "read": 1}, pluck="role")
check(level1 == [ROLE], "3. Sales Order level 1 (tender fields) readable only by " + ROLE + ": " + ", ".join(level1))
levels = status.get("sales_order_field_levels") or {}
check(levels.get("custom_tender_reference") == 1 and levels.get("custom_nit_number") == 1,
      "3. Sales Order Tender Reference and NIT Number at level 1: " + str(levels))
sector = frappe.db.get_value("Custom Field", {"dt": "Sales Order", "fieldname": "custom_sector"}, "permlevel") or 0
check(sector == 0, "3. Sales Order PEPL Sector stays visible to everyone (level " + str(sector) + ")")
check(status.get("guarded_methods"), "3. the 7 pepl_sales tender / Cost Sheet methods ask PEPL first")
check(status.get("sales_order_guard"), "3. only the three can make a Sales Order from a tender (0.62.1 guard installed)")

# ---------------- 4. Role Profiles ----------------
def profile_roles(name):
    return frappe.get_all("Has Role", filters={"parent": name, "parenttype": "Role Profile"}, pluck="role")


check(sorted(profile_roles("PEPL Tender Only")) == ["PEPL Tender Manager", "Sales User"], "4. Role Profile PEPL Tender Only = PEPL Tender Manager + Sales User")
check("PEPL Tender Viewer" not in profile_roles("PEPL CEO"), "4. Role Profile PEPL CEO has no PEPL Tender Viewer")
for old, new in [["PEPL Sales & Tender Manager", "PEPL Sales Manager"], ["PEPL Sales & Tender Executive", "PEPL Sales Executive"]]:
    tender_roles = [r for r in profile_roles(new) + profile_roles(old) if r.startswith("PEPL Tender")]
    check(frappe.db.exists("Role Profile", new) and not tender_roles,
          "4. " + new + " exists and no Sales profile carries a tender role (" + ", ".join(tender_roles) + ")")

# ---------------- 5. what every login sees ----------------
tenders = frappe.db.count("PEPL Tender")
sheets = frappe.db.count("PEPL CST Cost Sheet")
print("INFO  on this site: " + str(tenders) + " tender(s), " + str(sheets) + " Cost Sheet(s)")
users = frappe.get_all("User", filters={"enabled": 1, "user_type": "System User", "name": ["not in", ["Administrator", "Guest"]]}, pluck="name")
outsiders_seeing = []
order_openers = []
tender_order = None
for user in users:
    seen = frappe.call(TA + ".what_user_sees", user=user)
    counts = seen.get("counts")
    tender_order = seen.get("tender_sales_order")
    if user.lower() in expected:
        check(counts.get("PEPL Tender") == tenders and counts.get("PEPL CST Cost Sheet") == sheets,
              "5. " + user + " (listed) sees all " + str(tenders) + " tenders and " + str(sheets) + " Cost Sheets: " + str(counts))
    else:
        if sum(counts.values()) or seen.get("opens_a_tender"):
            outsiders_seeing.append(user + " " + str(counts) + (" opens a tender" if seen.get("opens_a_tender") else ""))
        if seen.get("opens_tender_sales_order"):
            order_openers.append(user)
check(not outsiders_seeing, "5. none of the other " + str(len(users) - len(expected)) + " logins sees a tender, Cost Sheet, or their history / comments / files / ToDos"
      + ("" if not outsiders_seeing else ": " + "; ".join(outsiders_seeing)))
managers = frappe.get_all("Has Role", filters={"role": "System Manager", "parenttype": "User", "parent": ["in", users]}, pluck="parent")
print("INFO  System Managers outside the list (they cannot open tenders): " + (", ".join([m for m in managers if m.lower() not in expected]) or "none"))

# ---------------- 6. tender Sales Orders stay open ----------------
if tender_order and order_openers:
    check(True, "6. tender Sales Order " + tender_order + " still opens for " + str(len(order_openers)) + " login(s) outside the list, e.g. " + order_openers[0])
elif tender_order:
    print("INFO  6. no login outside the list has Sales Order access, so " + tender_order + " was not tried")
else:
    print("INFO  6. no Sales Order made from a tender on this site: skipped")

# ---------------- 7. nothing passed on ----------------
todos = [t.name + " " + str(t.allocated_to) for t in frappe.get_all("ToDo", filters={"reference_type": ["in", GATED], "status": "Open"}, fields=["name", "allocated_to"])
         if (t.allocated_to or "").lower() not in expected and t.allocated_to != "Administrator"]
check(not todos, "7. no open tender / Cost Sheet ToDo held by anyone else (" + ", ".join(todos) + ")")
shares = [s.share_name + " " + str(s.user) for s in frappe.get_all("DocShare", filters={"share_doctype": ["in", GATED]}, fields=["share_name", "user", "everyone"])
          if s.everyone or (s.user or "").lower() not in expected]
check(not shares, "7. no tender / Cost Sheet shared with anyone else (" + ", ".join(shares) + ")")

# ---------------- 8. an assignment for an outsider goes to the first listed user ----------------
sample = frappe.get_all("PEPL Tender", pluck="name", limit=1)
outsider = [u for u in users if u.lower() not in expected]
if sample and outsider:
    todo = frappe.get_doc({"doctype": "ToDo", "allocated_to": outsider[0], "reference_type": "PEPL Tender",
                           "reference_name": sample[0], "description": "Check 62 test (undone)"}).insert()
    check((todo.allocated_to or "").lower() in expected, "8. a tender alert for " + outsider[0] + " went to " + str(todo.allocated_to) + " instead")
else:
    print("INFO  8. needs a tender and a login outside the list: skipped")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
