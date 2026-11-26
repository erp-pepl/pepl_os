# PEPL OS v0.81.0 - Check 81: Cycle 4 H1 - people and logins (runs on 0.81.0 or later).
# System Console, Type = Python, as Administrator. Leave "Commit" UNTICKED: the Check makes its own test login and
# Employees, tries the rules on them and rolls everything back at the end (nothing is saved, even if ticked).
VERSION = "0.81.0"
IDLE = "pepl_os.pepl_people.idle_logout"
PEOPLE = "pepl_os.pepl_people.people"
RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "")[:14]
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


def param(field):
    return frappe.db.get_value("PEPL System Parameters", "PEPL System Parameters", field)


def new_user(email, roles):
    u = frappe.get_doc({"doctype": "User", "email": email, "first_name": "C81", "last_name": RUN, "send_welcome_email": 0, "user_type": "System User"})
    u.insert(ignore_permissions=True)
    for r in roles:
        u.append("roles", {"role": r})
    if roles:
        u.save(ignore_permissions=True)
    return email


def new_employee(first, user=None, number=None):
    values = {"doctype": "Employee", "first_name": first, "last_name": RUN, "company": company, "gender": gender,
              "date_of_birth": "1990-01-01", "date_of_joining": "2024-04-01", "status": "Active"}
    if user:
        values["user_id"] = user
    if number:
        values["employee_number"] = number
    return frappe.get_doc(values).insert(ignore_permissions=True)


installed = frappe.db.get_value("Installed Application", {"app_name": "pepl_os"}, "app_version")
print("INFO  run " + RUN + " (test records end with it; all rolled back)")

# ---------------- 1. installed, hooks, settings ----------------
check(version_parts(installed) >= version_parts(VERSION), "1. pepl_os " + str(installed) + " (needs " + VERSION + ")")
check(IDLE + ".before_request" in (frappe.get_hooks("before_request") or []), "1. every request goes through the idle check")
emp_events = (frappe.get_hooks("doc_events") or {}).get("Employee") or {}
check(PEOPLE + ".validate_employee" in (emp_events.get("validate") or []), "1. Employee validate: PEPL rules")
check(PEOPLE + ".on_employee_update" in (emp_events.get("on_update") or []), "1. Employee on_update: keep login, leaver ToDo, operator link")
check(frappe.db.exists("Custom Field", {"dt": "Employee", "fieldname": "custom_person_type"}), "1. Employee has Person Type")
check(frappe.db.exists("Report", "PEPL People Register"), "1. report PEPL People Register")
s = frappe.call(IDLE + ".idle_status")
print("INFO  idle logout after " + str(s.get("hours")) + " h; exempt roles: " + ", ".join(s.get("exempt_roles") or []) + "; Frappe Session Expiry " + str(s.get("frappe_expiry")))
check(s.get("hours") == 3, "1. Idle Logout (Hours) = 3 (PEPL)")
check("PEPL Kiosk" in (s.get("exempt_roles") or []), "1. kiosk tablets exempt")
check(s.get("notify_system_managers"), "1. System Managers e-mailed each time")
check(s.get("frappe_expiry_hours") > s.get("hours"), "1. Frappe's own Session Expiry (" + str(s.get("frappe_expiry")) + ") longer than the PEPL idle time")
check(s.get("scheduled"), "1. the every-minute idle job is scheduled")
check(bool(s.get("system_managers")), "1. System Managers who get the e-mails: " + ", ".join(s.get("system_managers") or []))
mail = frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1})
print("INFO  outgoing e-mail account: " + (str(mail) if mail else "NONE - the idle e-mails wait in the Email Queue until one is set"))
check(str(param("custom_keep_login_when_employee_leaves")) in ["1", "True"], "1. Keep the Login When an Employee Leaves is ON (PEPL)")
check(str(param("custom_restrict_login_to_own_employee") or "0") in ["0", "False"], "1. logins are not restricted to their own Employee record")
for row in s.get("sessions") or []:
    print("INFO    session " + row["user"] + ": idle " + str(row["idle_minutes"]) + " min" + (" (exempt)" if row["exempt"] else ""))

# ---------------- 2. the rules on test records ----------------
company = frappe.get_all("Company", pluck="name")[0]
if not frappe.db.exists("Gender", "Male"):
    frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
gender = "Male"
person = new_user("c81.person." + RUN + "@example.com", [])
emp = new_employee("C81 Person", user=person, number="C81-" + RUN[-6:])
check(emp.custom_person_type == "Login User", "2. an Employee with a login is a Login User")
check(emp.create_user_permission == 0 and not frappe.db.exists("User Permission", {"user": person, "allow": "Employee"}), "2. the login is not restricted to its own Employee record")
floor = new_employee("C81 Floor")
check(floor.custom_person_type == "Shop Floor", "2. an Employee without a login is Shop Floor")
op = frappe.call(PEOPLE + ".make_operator", employee=emp.name)
check(op == emp.employee_number and frappe.db.get_value("PEPL Operator", op, "employee") == emp.name, "2. Make Operator: operator " + str(op) + " = Employee Number, linked")
refused = False
try:
    emp.reload()
    emp.employee_number = "C81-OTHER"
    emp.save(ignore_permissions=True)
except Exception:
    refused = True
check(refused, "2. an Employee Number different from the operator code is refused")
emp.reload()
emp.status = "Left"
emp.relieving_date = frappe.utils.today()
emp.save(ignore_permissions=True)
check(frappe.db.get_value("User", person, "enabled") == 1, "2. Employee Left: the login stays enabled (ERPNext alone would switch it off)")
todo = frappe.get_all("ToDo", filters={"reference_type": "Employee", "reference_name": emp.name, "status": "Open", "description": ["like", "%PPL-LEAVER-LOGIN%"]}, fields=["allocated_to"])
if str(param("enable_operational_todos")) in ["1", "True"]:
    check(len(todo) == 1, "2. leaver ToDo PPL-LEAVER-LOGIN raised (to " + (todo[0].allocated_to if todo else "-") + ")")
else:
    print("INFO  Daily Operational ToDos are off on this site - no leaver ToDo (switch in System Parameters)")
tablet = new_user("c81.tablet." + RUN + "@example.com", ["PEPL Kiosk"])
refused = False
try:
    new_employee("C81 Tablet", user=tablet)
except Exception:
    refused = True
check(refused, "2. a kiosk (device) login cannot be an Employee's login")
rows = frappe.call("frappe.desk.query_report.run", report_name="PEPL People Register", filters={})
result = rows.get("result") or []
mine = [r for r in result if r.get("employee") == floor.name]
check(bool(mine) and "no Employee Number" in (mine[0].get("gaps") or ""), "2. People Register lists the Shop Floor Employee with 'no Employee Number'")
print("INFO  People Register: " + str(rows.get("message")))

frappe.db.rollback()
print("")
print("Check 81: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
