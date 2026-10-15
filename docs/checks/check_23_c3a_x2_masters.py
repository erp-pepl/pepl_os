# PEPL OS v0.23.0 - Check 23: C3a-X2 shop-floor masters - Shift, Downtime Category, Operator (PIN and skills).
# System Console, Type = Python. Leave "Commit" UNTICKED: every test record below is undone at the end.
VERSION = "0.23.0"
PANEL = "pepl_os.pepl_production.masters.get_operator_panel"
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
        return ""
    except Exception as e:
        text = frappe.utils.strip_html(str(e))
        check(words.lower() in text.lower(), label + " -> " + text[:200])
        return text


# ---------------- remove records left by an earlier run that was committed by mistake ----------------
def remove(doctype, names):
    for name in names:
        if frappe.db.exists(doctype, name):
            try:
                frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
                print("INFO  removed leftover " + doctype + " " + name)
            except Exception as e:
                print("WARN  could not remove " + doctype + " " + name + ": " + frappe.utils.strip_html(str(e))[:160])


remove("PEPL Operator", frappe.get_all("PEPL Operator", filters={"name": ["like", "CHK23%"]}, pluck="name"))
remove("PEPL Shift", frappe.get_all("PEPL Shift", filters={"name": ["like", "CHK23%"]}, pluck="name"))
remove("PEPL Downtime Category", frappe.get_all("PEPL Downtime Category", filters={"name": ["like", "CHK23%"]}, pluck="name"))
remove("Workstation", frappe.get_all("Workstation", filters={"name": ["like", "CHK23%"]}, pluck="name"))
remove("Workstation Type", frappe.get_all("Workstation Type", filters={"name": ["like", "CHK23%"]}, pluck="name"))
remove("User", frappe.get_all("User", filters={"name": ["like", "chk23.%"]}, pluck="name"))

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(apps.get("pepl_os") == VERSION, "1. pepl_os version is " + VERSION + " (site has " + str(apps.get("pepl_os")) + ")")
for dt in ("PEPL Shift", "PEPL Downtime Category", "PEPL Operator", "PEPL Operator Skill"):
    check(frappe.db.exists("DocType", dt), "1. DocType " + dt + " exists")
params_meta = frappe.get_meta("PEPL System Parameters")
check(bool(params_meta.get_field("custom_operator_pin_digits")), "1. System Parameters has Production > Operator PIN Digits")
digits = frappe.db.get_single_value("PEPL System Parameters", "custom_operator_pin_digits")
print("INFO  Operator PIN Digits on this site: " + str(digits))
for dt in ("PEPL Shift", "PEPL Downtime Category", "PEPL Operator"):
    check(frappe.get_meta(dt).track_changes, "1. " + dt + ": every change is tracked")

# ---------------- 2. default downtime categories ----------------
DEFAULTS = [
    "Breakdown - Mechanical", "Breakdown - Electrical", "Breakdown - Hydraulic / Pneumatic", "Setup / Changeover",
    "Tool Change", "Waiting for Material", "Waiting for Operator", "Waiting for Drawing / Instruction",
    "Waiting for Inspection", "Quality Problem / Rework", "Power Failure", "Preventive Maintenance", "Calibration",
    "No Plan / No Load", "Meeting / Training", "Cleaning / 5S",
]
present = [d for d in DEFAULTS if frappe.db.exists("PEPL Downtime Category", d)]
check(len(present) == len(DEFAULTS), "2. the 16 starting downtime categories exist (" + str(len(present)) + " found)")
check(bool(frappe.db.exists("PEPL Downtime Category", {"is_breakdown": 1, "stop_type": "Unplanned"})), "2. breakdown categories are Unplanned")
check(frappe.db.get_value("PEPL Downtime Category", "Preventive Maintenance", "stop_type") == "PM / Calibration", "2. Preventive Maintenance is PM / Calibration")

# ---------------- 3. shift ----------------
def shift(name, start, end, brk):
    return frappe.get_doc({"doctype": "PEPL Shift", "shift_name": name, "start_time": start, "end_time": end, "break_minutes": brk}).insert()

day = shift("CHK23 Day", "08:00:00", "16:30:00", 30)
check(day.planned_minutes == 480 and not day.crosses_midnight, "3. day shift 08:00-16:30 with 30 min break = 480 planned minutes (" + str(day.planned_minutes) + ")")
night = shift("CHK23 Night", "22:00:00", "06:00:00", 30)
check(night.planned_minutes == 450 and night.crosses_midnight, "3. night shift 22:00-06:00 = 450 minutes, runs past midnight (" + str(night.planned_minutes) + ")")
refused("3. same start and end refused", lambda: shift("CHK23 Zero", "08:00:00", "08:00:00", 0), "same")
refused("3. break as long as the shift refused", lambda: shift("CHK23 Short", "08:00:00", "09:00:00", 60), "break")
refused("3. negative break refused", lambda: shift("CHK23 Neg", "08:00:00", "16:00:00", -5), "negative")

# ---------------- 4. downtime category ----------------
def category(name, stop_type, breakdown):
    return frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": name, "stop_type": stop_type, "is_breakdown": breakdown}).insert()

bd = category("CHK23 Spindle Failure", "Unplanned", 1)
check("availability" in bd.effect and "MTBF" in bd.effect, "4. a breakdown says it lowers availability and counts for MTBF / MTTR")
pl = category("CHK23 No Load", "Planned", 0)
check("planned production time" in pl.effect and "MTBF" not in pl.effect, "4. a planned stop says it is taken out of planned time")
refused("4. a Planned stop cannot be a breakdown", lambda: category("CHK23 Planned Breakdown", "Planned", 1), "breakdown")

# ---------------- 5. operator PIN ----------------
# The PIN length is whatever this site's System Parameters say (default 4); nothing is changed here.
n = int(digits or 4)
good_pin = "4321098765"[:n]
for wt in ("CHK23 VMC", "CHK23 LATHE"):
    frappe.get_doc({"doctype": "Workstation Type", "workstation_type": wt}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": "CHK23 VMC-01", "workstation_type": "CHK23 VMC"}).insert()


def operator(code, pin, skills=None, **extra):
    doc = frappe.get_doc(dict({"doctype": "PEPL Operator", "employee_code": code, "operator_name": "Check " + code, "pin": pin}, **extra))
    for row in skills or []:
        doc.append("skills", row)
    return doc.insert()

refused("5. PIN with a letter refused", lambda: operator("CHK23-OP-A", "1a" + "2" * (n - 2)), "digits only")
refused("5. PIN one digit too long refused (rule: " + str(n) + " digits)", lambda: operator("CHK23-OP-B", "1" * (n + 1)), str(n) + " digits")
refused("5. PIN one digit too short refused", lambda: operator("CHK23-OP-B2", "1" * (n - 1)), str(n) + " digits")
op = operator("CHK23-OP-C", good_pin)
check(op.pin_set == 1, "5. a " + str(n) + "-digit PIN is accepted and marked PIN Set")
stored = frappe.db.get_value("PEPL Operator", op.name, "pin") or ""
check(good_pin not in stored, "5. the PIN is not stored readable (record shows " + stored + ")")
check(frappe.get_doc("PEPL Operator", op.name).get_password("pin") == good_pin, "5. the PIN is kept encrypted and can be verified")
again = frappe.get_doc("PEPL Operator", op.name)
again.operator_name = "Check renamed"
again.save()
check(again.pin_set == 1 and again.get_password("pin") == good_pin, "5. saving other fields keeps the PIN")
same = operator("CHK23-OP-D", good_pin)
check(same.pin_set == 1, "5. a second operator may have the same PIN (PIN is checked with the code)")
nopin = operator("CHK23-OP-E", None)
rows = frappe.call(PANEL, name=nopin.name)["rows"]
check(any("No PIN" in r["text"] and r["colour"] == "orange" for r in rows), "5. operator without a PIN: panel warns in orange")

user = frappe.get_doc({"doctype": "User", "email": "chk23.login@example.com", "first_name": "Chk23", "send_welcome_email": 0}).insert()
operator("CHK23-OP-G", good_pin, user=user.name)
refused("5. one ERPNext login cannot belong to two operators", lambda: operator("CHK23-OP-H", good_pin, user=user.name), "already linked")

# ---------------- 6. machine skills ----------------
L3 = "3 - Runs independently"
refused(
    "6. the same machine group twice refused",
    lambda: operator("CHK23-OP-I", good_pin, [{"workstation_type": "CHK23 VMC", "level": L3}, {"workstation_type": "CHK23 VMC", "level": "1 - Trainee"}]),
    "twice",
)
refused(
    "6. Valid Until before Certified On refused",
    lambda: operator("CHK23-OP-J", good_pin, [{"workstation_type": "CHK23 VMC", "level": L3, "certified_on": frappe.utils.today(), "valid_until": frappe.utils.add_days(frappe.utils.today(), -1)}]),
    "valid until",
)
skilled = operator(
    "CHK23-OP-K",
    good_pin,
    [
        {"workstation_type": "CHK23 VMC", "level": L3},
        {"workstation_type": "CHK23 LATHE", "level": "2 - Runs under supervision", "valid_until": frappe.utils.add_days(frappe.utils.today(), -3)},
    ],
)
rows = frappe.call(PANEL, name=skilled.name)["rows"]
texts = " | ".join(r["text"] for r in rows)
print("INFO  panel: " + texts)
check(any("CHK23 VMC" in r["text"] and r["colour"] == "green" for r in rows), "6. panel shows VMC at level 3 in green")
check(any("CHK23 LATHE" in r["text"] and "expired" in r["text"] and r["colour"] == "red" for r in rows), "6. panel shows the expired lathe skill in red")
check(any("PIN set" in r["text"] for r in rows), "6. panel shows PIN set")

# ---------------- 7. who may do what (read live from this site's permissions) ----------------
def rights(profile):
    out = frappe.call("frappe.desk.query_report.run", report_name="PEPL Role Access Matrix", filters={"area": "Production", "role_profile": profile})
    return {r["doctype"]: r for r in (out.get("result") or []) if isinstance(r, dict) and r.get("doctype")}

foreman = rights("PEPL Foreman")
manager = rights("PEPL Production Manager")
check({"PEPL Shift", "PEPL Operator", "PEPL Downtime Category"} <= set(manager), "7. the three masters are in the Role Access Matrix (Production)")
fo, mo = foreman.get("PEPL Operator", {}), manager.get("PEPL Operator", {})
check(fo.get("read") == "Yes" and not fo.get("create"), "7. Foreman can view operators but not create them")
check(mo.get("create") == "Yes" and mo.get("write") == "Yes", "7. Production Manager creates and edits operators")
check(not mo.get("delete") and not fo.get("delete"), "7. neither can delete an operator (System Manager only)")
fs, ms = foreman.get("PEPL Shift", {}), manager.get("PEPL Shift", {})
check(ms.get("write") == "Yes" and fs.get("read") == "Yes" and not fs.get("write"), "7. Shifts: manager edits, foreman views")

# ---------------- 8. attribution ----------------
versions = frappe.get_all("Version", filters={"ref_doctype": "PEPL Operator", "docname": op.name}, fields=["owner"])
check(len(versions) >= 1 and versions[0].owner == frappe.session.user, "8. the rename of the operator is recorded with the user's name")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
