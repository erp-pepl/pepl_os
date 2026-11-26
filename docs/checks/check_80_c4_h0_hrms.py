# PEPL OS v0.80.0 - Check 80: Cycle 4 H0 - Frappe HR in place (runs on 0.80.0 or later).
# Run AFTER setup_c4_h0_hr.py (Commit ticked). System Console, Type = Python, as Administrator.
# Leave "Commit" UNTICKED: this Check only reads, and ends with a rollback.
VERSION = "0.80.0"
HOLIDAY_LIST = "PEPL Holidays 2026-2027"
YEARS = [2026, 2027]
HOLIDAYS_2026 = 10
HR = "pepl_os.pepl_people.hr_setup"
HR_DOCTYPES = ["Employee", "Holiday List", "Shift Type", "Shift Assignment", "Employee Checkin", "Attendance",
               "Attendance Request", "Leave Type", "Leave Period", "Leave Allocation", "Leave Application"]
CANCEL_HR = ["Attendance", "Attendance Request", "Shift Assignment", "Leave Allocation", "Leave Application"]
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


def perm_rows(doctype):
    # the effective rules: Custom DocPerm once a DocType's rights were changed, else its standard DocPerm
    table = "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": doctype}) else "DocPerm"
    return frappe.get_all(table, filters={"parent": doctype}, fields=["role", "permlevel", "read", "write", "cancel", "delete"])


def same_rules(st, rules):
    for f in rules:
        if float(st.get(f) or 0) != float(rules[f] or 0):
            return False
    return True


apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}

# ---------------- 1. versions ----------------
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os " + str(apps.get("pepl_os")) + " (needs " + VERSION + ")")
check(version_parts(apps.get("frappe")) >= [16, 60, 0], "1. frappe " + str(apps.get("frappe")) + " (Frappe HR needs 16.60+)")
check(version_parts(apps.get("erpnext")) >= [16, 50, 0], "1. erpnext " + str(apps.get("erpnext")) + " (Frappe HR needs 16.50+)")
check("hrms" in apps, "1. Frappe HR installed (hrms " + str(apps.get("hrms")) + ")")
check("india_compliance" in apps, "1. India Compliance installed (" + str(apps.get("india_compliance")) + ")")
check("hrms" in (frappe.get_hooks("required_apps", app_name="pepl_os") or []), "1. pepl_os requires hrms")

# ---------------- 2. profiles ----------------
for profile, want in [["PEPL HR Manager", ["HR Manager", "HR User", "Leave Approver"]], ["PEPL HR Assistant", ["HR User"]]]:
    have = frappe.get_all("Has Role", filters={"parent": profile, "parenttype": "Role Profile"}, pluck="role")
    check(frappe.db.exists("Role Profile", profile) and all(r in have for r in want), "2. Role Profile " + profile + " has " + ", ".join(want))
assistant = frappe.get_all("Has Role", filters={"parent": "PEPL HR Assistant", "parenttype": "Role Profile"}, pluck="role")
check("HR Manager" not in assistant and "Leave Approver" not in assistant, "2. PEPL HR Assistant cannot approve (no HR Manager / Leave Approver)")
for profile in ["PEPL HR Manager", "PEPL HR Assistant"]:
    holders = frappe.get_all("User Role Profile", filters={"role_profile": profile, "parenttype": "User"}, pluck="parent")
    print("INFO  " + profile + " held by: " + (", ".join(holders) or "nobody yet"))

# ---------------- 3. access on the HR records ----------------
for doctype in HR_DOCTYPES:
    if not frappe.db.exists("DocType", doctype):
        check(False, "3. " + doctype + " exists")
        continue
    deleters = [r.role for r in perm_rows(doctype) if r.delete and r.role != "System Manager"]
    check(not deleters, "3. " + doctype + ": only the System Manager deletes (" + ", ".join(deleters) + ")")
for doctype in ["Employee", "Attendance", "Leave Application"]:
    ceo = [r for r in perm_rows(doctype) if r.role == "PEPL CEO" and not r.permlevel]
    check(bool(ceo) and ceo[0].read and not ceo[0].write, "3. the CEO views " + doctype + " and changes nothing")
for doctype in CANCEL_HR:
    cancellers = [r.role for r in perm_rows(doctype) if r.cancel and not r.permlevel]
    check("HR Manager" in cancellers and all(r in ["HR Manager", "System Manager"] for r in cancellers), "3. " + doctype + ": only the HR head cancels (" + ", ".join(cancellers) + ")")
emp_flags = frappe.db.get_value("DocType", "Employee", ["track_changes", "track_views"], as_dict=True)
views_set = emp_flags.track_views or frappe.db.exists("Property Setter", {"doc_type": "Employee", "property": "track_views", "value": "1"})
changes_set = emp_flags.track_changes or frappe.db.exists("Property Setter", {"doc_type": "Employee", "property": "track_changes", "value": "1"})
check(bool(changes_set) and bool(views_set), "3. Employee: every change and every opening is recorded")

# ---------------- 4. PEPL's HR set-up (setup_c4_h0_hr.py) ----------------
s = frappe.call(HR + ".hr_setup_status", holiday_list=HOLIDAY_LIST, years=YEARS)
hs = s.get("hr_settings") or {}
check(hs.get("leave_approver_mandatory_in_leave_application") == 1, "4. HR Settings: a leave approver is required")
check(hs.get("prevent_self_leave_approval") == 1, "4. HR Settings: nobody approves his own leave")
check(not hs.get("send_birthday_reminders") and not hs.get("send_work_anniversary_reminders") and not hs.get("send_holiday_reminders"), "4. HR Settings: no birthday / anniversary / holiday mails")
hl = s.get("holiday_list")
check(bool(hl), "4. Holiday List " + HOLIDAY_LIST + " exists (run setup_c4_h0_hr.py with Commit ticked if not)")
if hl:
    check(hl["from_date"] == "2026-01-01" and hl["to_date"] == "2027-12-31", "4. it covers 2026-01-01 to 2027-12-31 (" + hl["from_date"] + " to " + hl["to_date"] + ")")
    check(hl["weekly_off"] == hl["sundays_expected"], "4. every Sunday is a weekly off (" + str(hl["weekly_off"]) + " of " + str(hl["sundays_expected"]) + ")")
    in_2026 = [h for h in hl["holidays"] if h[0].startswith("2026")]
    check(len(in_2026) == HOLIDAYS_2026, "4. PEPL's 10 holidays of 2026 (" + str(len(in_2026)) + ")")
    for h in hl["holidays"]:
        print("INFO    " + h[0] + "  " + h[1])
for company, default in (s.get("companies") or {}).items():
    check(default == HOLIDAY_LIST, "4. company " + company + " uses " + HOLIDAY_LIST + " (" + str(default) + ")")
lt = s.get("leave_types") or {}
el = lt.get("Earned Leave")
check(bool(el) and el.include_holiday == 1 and el.allow_negative == 0 and el.is_carry_forward == 1 and el.is_earned_leave == 0, "4. Earned Leave: sandwich on, never below zero, carried forward, no fixed HRMS accrual")
lwp = lt.get("Leave Without Pay")
check(bool(lwp) and lwp.is_lwp == 1 and lwp.include_holiday == 1, "4. Leave Without Pay: unpaid, sandwich on")
for company, years in (s.get("leave_periods") or {}).items():
    check(len(years) == len(YEARS), "4. company " + company + ": leave periods " + ", ".join([str(y) for y in years]))
rules = s.get("rules") or {}
print("INFO  attendance rules (System Parameters -> People): late after " + str(rules.get("late_entry_grace_period")) + " min, half day below " + str(rules.get("working_hours_threshold_for_half_day")) + " h, absent below " + str(rules.get("working_hours_threshold_for_absent")) + " h")
shifts = s.get("shift_types") or {}
if not shifts:
    print("INFO  no active PEPL Shift on this site - no Shift Type made yet (PEPL's shift times needed)")
for name, st in shifts.items():
    check(bool(st), "4. Shift Type " + name + " exists for PEPL Shift " + name)
    if st:
        check(same_rules(st, rules) and st.enable_auto_attendance == 0 and st.enable_late_entry_marking == 1 and st.holiday_list == HOLIDAY_LIST, "4. Shift Type " + name + ": PEPL's rules, late marking on, auto attendance off, PEPL holidays")

frappe.db.rollback()
print("")
print("Check 80: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
