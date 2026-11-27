# PEPL OS v0.82.0 - Check 82: Cycle 4 H5 - statutory data (PF / ESIC / PAN / Aadhaar / bank) (runs on 0.82.0 or later).
# System Console, Type = Python, as Administrator. Leave "Commit" UNTICKED: the Check makes its own test Employees,
# tries the rules and rolls everything back at the end. Pop-ups during the run are the refusals it provokes on purpose.
VERSION = "0.82.0"
ST = "pepl_os.pepl_people.statutory"
RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "")[:14]
VALID_AADHAAR = "234123412346"
WRONG_CHECK_DIGIT = "234123412345"
LEVEL6 = ["custom_uan", "custom_esic_ip_number", "custom_aadhaar", "custom_aadhaar_masked", "custom_father_or_husband_name",
          "custom_pf_applicable", "custom_esic_applicable", "bank_name", "bank_ac_no", "iban", "ifsc_code", "micr_code",
          "pan_number", "provident_fund_account", "ctc"]
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


def new_employee(first, values):
    base = {"doctype": "Employee", "first_name": first, "last_name": RUN, "company": company, "gender": "Male",
            "date_of_birth": "1990-01-01", "date_of_joining": "2024-04-01", "status": "Active"}
    for k in values:
        base[k] = values[k]
    return frappe.get_doc(base).insert(ignore_permissions=True)


def refused(first, values):
    try:
        new_employee(first, values)
    except Exception:
        return True
    return False


installed = frappe.db.get_value("Installed Application", {"app_name": "pepl_os"}, "app_version")
print("INFO  run " + RUN + " (test records end with it; all rolled back)")

# ---------------- 1. fields and access ----------------
check(version_parts(installed) >= version_parts(VERSION), "1. pepl_os " + str(installed) + " (needs " + VERSION + ")")
for field in LEVEL6:
    custom = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": field}, "permlevel")
    setter = frappe.db.get_value("Property Setter", {"doc_type": "Employee", "field_name": field, "property": "permlevel"}, "value")
    level = setter if setter is not None else custom
    check(str(level) == "6", "1. " + field + " at permission level 6 (" + str(level) + ")")
check(frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": "custom_aadhaar"}, "fieldtype") == "Password", "1. Aadhaar is an encrypted (Password) field")
level6 = frappe.get_all("Custom DocPerm", filters={"parent": "Employee", "permlevel": 6}, fields=["role", "read", "write"])
roles6 = sorted([r.role for r in level6 if r.read])
check(roles6 == ["HR Manager", "System Manager"], "1. level 6 read only by HR Manager and System Manager (" + ", ".join(roles6) + ")")
check(all(r.write for r in level6 if r.role in ["HR Manager", "System Manager"]), "1. HR Manager and System Manager can change level 6")
check("PEPL CEO" not in roles6 and "HR User" not in roles6, "1. the CEO and the HR Assistant do not see PF / ESIC / PAN / bank / Aadhaar")
check(frappe.db.exists("Report", "PEPL Statutory Data Readiness"), "1. report PEPL Statutory Data Readiness")
rep_roles = frappe.get_all("Has Role", filters={"parent": "PEPL Statutory Data Readiness", "parenttype": "Report"}, pluck="role")
check("PEPL CEO" not in rep_roles and "HR User" not in rep_roles, "1. the readiness report is for HR Manager / System Manager only (" + ", ".join(rep_roles) + ")")

# ---------------- 2. the rules on test Employees ----------------
company = frappe.get_all("Company", pluck="name")[0]
if not frappe.db.exists("Gender", "Male"):
    frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
check(refused("C82 BadUAN", {"custom_uan": "12345"}), "2. a UAN that is not 12 digits is refused")
check(refused("C82 BadIP", {"custom_esic_ip_number": "12345678901"}), "2. an ESIC IP number that is not 10 digits is refused")
check(refused("C82 BadPAN", {"pan_number": "ABC123"}), "2. a PAN not like ABCDE1234F is refused")
check(refused("C82 BadAadhaar", {"custom_aadhaar": WRONG_CHECK_DIGIT}), "2. an Aadhaar number with a wrong check digit is refused")
uan = "9" + RUN[-11:]
ip = "8" + RUN[-9:]
emp = new_employee("C82 Good", {"custom_uan": uan[:4] + " " + uan[4:], "custom_esic_ip_number": ip, "pan_number": "abcde1234f",
                                "custom_aadhaar": "2341 2341 2346", "custom_pf_applicable": 1, "custom_esic_applicable": 1})
check(emp.custom_uan == uan and emp.pan_number == "ABCDE1234F", "2. UAN kept without spaces, PAN in capitals")
check(emp.custom_aadhaar_masked == "XXXX XXXX 2346", "2. Aadhaar shown masked: " + str(emp.custom_aadhaar_masked))
stored = str(frappe.db.get_value("Employee", emp.name, "custom_aadhaar") or "")
check("2341" not in stored, "2. the Aadhaar number is not in the Employee table (kept encrypted)")
check(refused("C82 SameUAN", {"custom_uan": uan}), "2. the same UAN on a second Employee is refused")
check(refused("C82 SameIP", {"custom_esic_ip_number": ip}), "2. the same ESIC IP number on a second Employee is refused")
shown = frappe.call(ST + ".show_aadhaar", employee=emp.name)
check(shown == VALID_AADHAAR, "2. Show Aadhaar gives the full number to the System Manager")
check(frappe.db.exists("Access Log", {"reference_document": emp.name, "method": "Show Aadhaar"}), "2. the showing is recorded in the Access Log")
rows = frappe.call("frappe.desk.query_report.run", report_name="PEPL Statutory Data Readiness", filters={"only_missing": 1})
mine = [r for r in (rows.get("result") or []) if r.get("name") == emp.name]
check(bool(mine) and "father" in (mine[0].get("missing") or "") and "UAN" not in (mine[0].get("missing") or ""), "2. readiness: father's / husband's name and bank still missing, UAN not")
print("INFO  readiness: " + str(rows.get("message")))

frappe.db.rollback()
print("")
print("Check 82: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
