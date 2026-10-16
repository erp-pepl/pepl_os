# PEPL OS v0.25.0 - Check 25: C3a-X7 operator skill check on the Shift Production Entry -
# levels, expiry by shift date, minimum level, Advisory / Soft Block / Hard Block, reason in the Override Log.
# Runs on 0.25.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes this check makes to try each mode, is undone at the end.
VERSION = "0.25.0"
SPR = "PEPL Shift Production Entry"
L1 = "1 - Trainee"
L2 = "2 - Runs under supervision"
L3 = "3 - Runs independently"
L4 = "4 - Sets up and trains others"
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
        check(words.lower() in text.lower(), label + " -> " + text[:220])
        return text


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.get_meta(SPR).get_field("skill_status")) and bool(frappe.get_meta(SPR).get_field("skill_level")), "1. the shift entry records the operator's skill and the check result")
check(bool(frappe.get_meta("PEPL System Parameters").get_field("custom_skill_min_level")), "1. System Parameters has Production > Minimum Skill Level to Run a Machine")
site_mode = frappe.db.get_single_value("PEPL System Parameters", "skill_check_mode")
site_min = frappe.db.get_single_value("PEPL System Parameters", "custom_skill_min_level")
print("INFO  this site: Operator Skill Check Mode = " + str(site_mode) + ", minimum level = " + str(site_min))
check(site_min in (L1, L2, L3, L4), "1. the minimum level on this site is one of the four levels")


def set_rules(mode, minimum=L3, reasons=1):
    params = frappe.get_doc("PEPL System Parameters")
    params.skill_check_mode = mode
    params.custom_skill_min_level = minimum
    params.custom_enforce_override_reason = reasons
    params.save()


# ---------------- masters for this run ----------------
DAY = "CHK25 Day " + RUN
GROUP = "CHK25 CNC " + RUN
NO_LOAD = "CHK25 No Load " + RUN
pin = "1" * int(frappe.db.get_single_value("PEPL System Parameters", "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "Workstation Type", "workstation_type": GROUP}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()


def operator(code, skills):
    frappe.get_doc({"doctype": "PEPL Operator", "employee_code": code, "operator_name": "Check " + code, "pin": pin, "skills": skills}).insert()
    return code


SKILLED = operator("CHK25-L3-" + RUN, [{"workstation_type": GROUP, "level": L3}])
JUNIOR = operator("CHK25-L2-" + RUN, [{"workstation_type": GROUP, "level": L2}])
NOBODY = operator("CHK25-NO-" + RUN, [])
LAPSED = operator("CHK25-EXP-" + RUN, [{"workstation_type": GROUP, "level": L4, "valid_until": frappe.utils.add_days(today, -10)}])

machines = []


def machine(grouped=True):
    name = "CHK25 M" + str(len(machines) + 1) + " " + RUN
    values = {"doctype": "Workstation", "workstation_name": name}
    if grouped:
        values["workstation_type"] = GROUP
    frappe.get_doc(values).insert()
    machines.append(name)
    return name


def entry(op, grouped=True, days_back=1):
    # each entry gets its own machine, so entries never overlap each other
    doc = frappe.get_doc({"doctype": SPR, "posting_date": frappe.utils.add_days(today, -days_back), "shift": DAY, "workstation": machine(grouped), "operator": op, "company": company})
    doc.append("downtime", {"downtime_category": NO_LOAD, "from_time": "08:00", "to_time": "16:00"})
    return doc


# ---------------- 2. what the check finds (Advisory, so nothing is blocked) ----------------
set_rules("Advisory")
e = entry(SKILLED).insert()
check(e.skill_status == "Qualified" and e.skill_level == L3, "2. level 3 operator: Qualified (" + str(e.skill_level) + ")")
e = entry(JUNIOR).insert()
check(e.skill_status == "Not qualified" and e.skill_level == L2, "2. level 2 operator: Not qualified (needs 3)")
e = entry(NOBODY).insert()
check(e.skill_status == "Not qualified" and e.skill_level == "None", "2. operator with no skill on the group: Not qualified")
e = entry(LAPSED).insert()
check(e.skill_status == "Not qualified", "2. skill that expired 10 days ago: Not qualified for yesterday's shift")
e = entry(LAPSED, days_back=12).insert()
check(e.skill_status == "Qualified" and e.skill_level == L4, "2. the same skill still counts for a shift 12 days ago (checked on the shift date)")
e = entry(NOBODY, grouped=False).insert()
check(e.skill_status == "Not checked", "2. machine without a machine group: Not checked")
panel = frappe.call("pepl_os.pepl_production.spr.get_spr_panel", name=entry(JUNIOR).insert().name)["rows"]
print("INFO  panel: " + " | ".join(r["text"] for r in panel))
check(any("not qualified" in r["text"].lower() and r["colour"] == "orange" for r in panel), "2. the panel shows the shortfall in orange with the mode")

# ---------------- 3. Advisory ----------------
e = entry(JUNIOR).insert()
check(frappe.call("pepl_os.pepl_production.skill.skill_gate_check", name=e.name) is None, "3. Advisory: no reason asked before submit")
e.submit()
check(e.docstatus == 1, "3. Advisory: the entry of a level 2 operator is submitted (warning only)")

# ---------------- 4. Soft Block ----------------
set_rules("Soft Block")
e = entry(JUNIOR).insert()
gate = frappe.call("pepl_os.pepl_production.skill.skill_gate_check", name=e.name)
check(bool(gate) and gate.get("rule_code") == "PRD-SKILL", "4. Soft Block: the form asks for a reason before submit (" + str(gate and gate.get("message")) + ")")
refused("4. Soft Block: submit without a reason is refused", lambda: e.submit(), "[PRD-SKILL]")
e.reload()
frappe.call("pepl_os.common.overrides.record_override", rule_code="PRD-SKILL", reference_doctype=SPR, reference_name=e.name, message=gate.get("message"), reason="Supervisor stood with the operator all shift (check " + RUN + ")")
log = frappe.get_all("PEPL Override Log", filters={"rule_code": "PRD-SKILL", "reference_name": e.name}, fields=["user", "reason"])
check(len(log) == 1 and log[0].user == frappe.session.user, "4. the reason is in the Override Log with the user's name")
e.submit()
check(e.docstatus == 1, "4. Soft Block: with the reason logged, the entry is submitted")
e = entry(SKILLED).insert()
e.submit()
check(e.docstatus == 1, "4. Soft Block: a qualified operator's entry submits without any reason")
set_rules("Soft Block", reasons=0)
e = entry(JUNIOR).insert()
e.submit()
check(e.docstatus == 1, "4. Soft Block with 'Enforce Override Reason' off: warning only, submitted")

# ---------------- 5. Hard Block ----------------
set_rules("Hard Block")
refused("5. Hard Block: a level 2 operator's entry is refused", lambda: entry(JUNIOR).insert(), "not qualified")
refused("5. Hard Block: an operator with an expired skill is refused", lambda: entry(LAPSED).insert(), "not qualified")
e = entry(SKILLED).insert()
e.submit()
check(e.docstatus == 1, "5. Hard Block: a qualified operator's entry is saved and submitted")
e = entry(NOBODY, grouped=False).insert()
check(e.skill_status == "Not checked", "5. Hard Block never blocks a machine without a group (Not checked)")

# ---------------- 6. minimum level from System Parameters ----------------
set_rules("Hard Block", minimum=L2)
e = entry(JUNIOR).insert()
check(e.skill_status == "Qualified", "6. with the minimum set to level 2, the level 2 operator is Qualified even in Hard Block")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (System Parameters are back to " + str(site_mode) + " / " + str(site_min) + ").")
