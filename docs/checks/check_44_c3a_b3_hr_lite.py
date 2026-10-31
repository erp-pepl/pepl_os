# PEPL OS v0.44.0 - Check 44: C3a-B3 HR-lite - the operator follows his Employee (name, joining date, Left ->
# Inactive), Eligible Shifts (Warn on the Shift panel / Block refuses the entry and the kiosk), and the Skill Matrix
# (levels, expired and expiring skills, qualified operators per machine group, what is missing on each operator).
# Runs on 0.44.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the
# end (except the kiosk's short-lived session entry in the cache, which expires by itself). Then look at the
# screens in the browser: see the steps in the chat.
VERSION = "0.44.0"
PARAMS = "PEPL System Parameters"
OPERATOR = "PEPL Operator"
SPR = "PEPL Shift Production Entry"
K = "pepl_os.pepl_production.kiosk."
REPORT = "PEPL Skill Matrix"
LEVEL3 = "3 - Runs independently"
LEVEL2 = "2 - Runs under supervision"
passed = []
failed = []


def check(ok, label):
    if ok:
        passed.append(label)
        print("PASS  " + label)
    else:
        failed.append(label)
        print("FAIL  " + label)


def refused(label, action, words):
    try:
        action()
        check(False, label + " (it was accepted)")
    except Exception as e:
        text = frappe.utils.strip_html(str(e))
        check(words.lower() in text.lower(), label + " -> " + text[:200])


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
yesterday = frappe.utils.add_days(today, -1)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
meta = frappe.get_meta(OPERATOR)
check(bool(meta.get_field("employee")) and meta.get_field("eligible_shifts").fieldtype == "Table MultiSelect", "1. the Operator form has Employee and Eligible Shifts")
pmeta = frappe.get_meta(PARAMS)
check(all(pmeta.get_field(f) for f in ("custom_shift_eligibility_mode", "custom_skill_expiry_warning_days", "custom_skill_min_cover")),
      "1. System Parameters > Production > Operators (HR-lite): Shift Eligibility Check (" + str(frappe.db.get_single_value(PARAMS, "custom_shift_eligibility_mode"))
      + "), Skill Expiry Warning Days (" + str(frappe.db.get_single_value(PARAMS, "custom_skill_expiry_warning_days")) + "), Minimum Qualified Operators ("
      + str(frappe.db.get_single_value(PARAMS, "custom_skill_min_cover")) + ")")
check(frappe.db.get_value("Report", REPORT, "report_type") == "Script Report" and bool(frappe.get_all("Workspace Link", filters={"parent": "Production Command Centre", "link_to": REPORT})),
      "1. report '" + REPORT + "' exists and is listed on the Production Command Centre")

params = frappe.get_doc(PARAMS)
params.custom_shift_eligibility_mode = "Warn"
params.custom_skill_expiry_warning_days = 30
params.custom_skill_min_cover = 2
params.custom_skill_min_level = LEVEL3
params.skill_check_mode = "Advisory"
params.custom_spr_tool_photo_required = 0
params.custom_spr_max_unaccounted_minutes = 15
params.save()

# ---------------- 2. the operator follows his Employee ----------------
if not frappe.db.exists("Gender", "Male"):
    frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert()
emp = frappe.get_doc({"doctype": "Employee", "first_name": "Mahesh", "last_name": "Patil " + RUN, "company": company, "gender": "Male",
                      "date_of_birth": "1990-01-01", "date_of_joining": "2020-04-01", "status": "Active"}).insert()
OP1 = "CHK44-OP1-" + RUN
op1 = frappe.get_doc({"doctype": OPERATOR, "employee_code": OP1, "operator_name": "typed name", "pin": pin, "employee": emp.name}).insert()
check(op1.operator_name == emp.employee_name and str(op1.joining_date) == "2020-04-01", "2. operator " + OP1 + " takes the Employee's name '" + str(op1.operator_name) + "' and joining date " + str(op1.joining_date))
refused("2. the same Employee cannot be a second operator", lambda: frappe.get_doc({"doctype": OPERATOR, "employee_code": "CHK44-OP9-" + RUN, "operator_name": "x", "employee": emp.name}).insert(), "already operator")
emp.reload()
emp.status = "Left"
emp.relieving_date = today
emp.save()
check(frappe.db.get_value(OPERATOR, OP1, "status") == "Inactive", "2. the Employee is set to Left -> the operator is Inactive by itself")
refused("2. ... so he can no longer sign in on the kiosk", lambda: frappe.call(K + "sign_in", machine="x", shift="x", posting_date=today, employee_code=OP1, pin=pin), "not recognised")

# ---------------- 3. eligible shifts ----------------
DAY = "CHK44 Day " + RUN
EVENING = "CHK44 Evening " + RUN
MILLS = "CHK44 MILL " + RUN
LATHES = "CHK44 LATHE " + RUN
MILL = "CHK44 MILL-01 " + RUN
NO_LOAD = "CHK44 No Load " + RUN
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": EVENING, "start_time": "16:30:00", "end_time": "01:00:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "Workstation Type", "workstation_type": MILLS}).insert()
frappe.get_doc({"doctype": "Workstation Type", "workstation_type": LATHES}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL, "workstation_type": MILLS}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
OP2 = "CHK44-OP2-" + RUN
refused("3. a Default Shift outside the Eligible Shifts is refused",
        lambda: frappe.get_doc({"doctype": OPERATOR, "employee_code": "CHK44-OP8-" + RUN, "operator_name": "x", "default_shift": EVENING, "eligible_shifts": [{"shift": DAY}]}).insert(),
        "not one of the Eligible Shifts")
op2 = frappe.get_doc({"doctype": OPERATOR, "employee_code": OP2, "operator_name": "Ramesh " + RUN, "pin": pin, "default_shift": DAY, "eligible_shifts": [{"shift": DAY}],
                      "skills": [{"workstation_type": MILLS, "level": LEVEL3}, {"workstation_type": LATHES, "level": LEVEL2}]}).insert()


def evening_entry():
    doc = frappe.get_doc({"doctype": SPR, "posting_date": yesterday, "shift": EVENING, "workstation": MILL, "operator": OP2, "company": company})
    doc.append("downtime", {"downtime_category": NO_LOAD, "from_time": "16:30", "to_time": "01:00"})
    return doc.insert()


entry = evening_entry()
panel = frappe.call("pepl_os.pepl_production.spr.get_spr_panel", name=entry.name).get("rows") or []
warn = [r for r in panel if "not set to work" in r.get("text")]
check(bool(warn) and warn[0].get("colour") == "orange", "3. Warn: the evening entry is saved and its Shift panel says -> " + (warn[0].get("text") if warn else "nothing"))
frappe.delete_doc(SPR, entry.name)
params = frappe.get_doc(PARAMS)
params.custom_shift_eligibility_mode = "Block"
params.save()
refused("3. Block: the evening entry is refused", evening_entry, "not set to work the")
refused("3. Block: the kiosk refuses the evening shift", lambda: frappe.call(K + "sign_in", machine=MILL, shift=EVENING, posting_date=today, employee_code=OP2, pin=pin), "not set to work the")
out = frappe.call(K + "sign_in", machine=MILL, shift=DAY, posting_date=today, employee_code=OP2, pin=pin)
check(bool(out.get("token")), "3. Block: the day shift (his eligible shift) signs in on the kiosk")
frappe.call(K + "sign_out", token=out.get("token"))

# ---------------- 4. skills and the Skill Matrix ----------------
OP3 = "CHK44-OP3-" + RUN
frappe.get_doc({"doctype": OPERATOR, "employee_code": OP3, "operator_name": "Suresh " + RUN, "pin": pin,
                "skills": [{"workstation_type": MILLS, "level": LEVEL3, "valid_until": frappe.utils.add_days(today, -3)},
                           {"workstation_type": LATHES, "level": LEVEL3, "valid_until": frappe.utils.add_days(today, 10)}]}).insert()
rows = frappe.call("pepl_os.pepl_production.masters.get_operator_panel", name=OP3).get("rows") or []
soon = [r.get("text") for r in rows if "expires on" in r.get("text")]
check(bool(soon) and "(10 days)" in soon[0], "4. the operator panel warns of a skill expiring soon -> " + (soon[0] if soon else "nothing"))
out = frappe.call("frappe.desk.query_report.run", report_name=REPORT, filters={"status": "Active", "workstation_type": MILLS})
data = out.get("result") or []
key = [c.get("fieldname") for c in out.get("columns") or [] if c.get("label") == MILLS]
key = key[0] if key else "none"
r2 = [r for r in data if r.get("operator") == OP2]
r3 = [r for r in data if r.get("operator") == OP3]
cover = [r for r in data if r.get("is_cover")]
print("INFO  Skill Matrix for " + MILLS + ": " + OP2 + " = " + str(r2[0].get(key) if r2 else "-") + ", " + OP3 + " = " + str(r3[0].get(key) if r3 else "-")
      + ", qualified = " + str(cover[0].get(key) if cover else "-"))
check(bool(r2) and r2[0].get(key) == "3" and r2[0].get(key + "_colour") == "green", "4. " + OP2 + " shows level 3 on " + MILLS + ", green")
check(bool(r3) and r3[0].get(key) == "3 expired" and r3[0].get(key + "_colour") == "red", "4. " + OP3 + " shows his expired skill red")
check(bool(cover) and cover[0].get(key) == "1" and cover[0].get(key + "_colour") == "red", "4. qualified operators on " + MILLS + ": 1 (the expired one does not count) - red, fewer than 2")
check(MILLS in str(out.get("message")), "4. the line above the report names the thin machine group -> " + str(out.get("message"))[-120:])
issues = (r3[0].get("issues") if r3 else "") or ""
check("no default shift" in issues and "not linked to an Employee" in issues and "expired" in issues, "4. To Do for " + OP3 + " -> " + issues)
check(bool(r2) and r2[0].get("eligible_shifts") == DAY, "4. the matrix shows " + OP2 + "'s eligible shifts: " + str(r2[0].get("eligible_shifts") if r2 else "-"))

# ---------------- 5. settings ----------------


def bad_mode():
    p = frappe.get_doc(PARAMS)
    p.custom_shift_eligibility_mode = "Maybe"
    p.save()


def bad_cover():
    p = frappe.get_doc(PARAMS)
    p.custom_skill_min_cover = -1
    p.save()


refused("5. Shift Eligibility Check other than Warn / Block is refused", bad_mode, "Shift Eligibility Check")
refused("5. a negative Minimum Qualified Operators is refused", bad_cover, "Minimum Qualified Operators")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
