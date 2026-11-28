# PEPL OS v0.83.0 - Check 83: Cycle 4 H3 - Earned Leave, sandwich, leave types, approvers (runs on 0.83.0 or later).
# Run AFTER the set-up rev 2 (setup_c4_h0_hr.py, Commit ticked). System Console, Type = Python, as Administrator.
# Leave "Commit" UNTICKED: the Check makes its own test Employees and leaves (2027 dates), tries the rules and rolls
# everything back at the end. A pop-up during the run is a refusal it provokes on purpose.
VERSION = "0.83.0"
HOLIDAY_LIST = "PEPL Holidays 2026-2027"
LV = "pepl_os.pepl_people.leave"
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


def new_employee(first, values):
    base = {"doctype": "Employee", "first_name": first, "last_name": RUN, "company": company, "gender": "Male",
            "date_of_birth": "1990-01-01", "date_of_joining": "2020-04-01", "status": "Active"}
    for k in values:
        base[k] = values[k]
    return frappe.get_doc(base).insert(ignore_permissions=True)


def allocate(emp, days):
    a = frappe.get_doc({"doctype": "Leave Allocation", "employee": emp.name, "leave_type": "Earned Leave",
                        "from_date": "2027-01-01", "to_date": "2027-12-31", "new_leaves_allocated": days})
    a.insert(ignore_permissions=True)
    a.submit()


def application(emp, from_date, to_date, leave_type):
    return frappe.get_doc({"doctype": "Leave Application", "employee": emp.name, "leave_type": leave_type, "from_date": from_date,
                           "to_date": to_date, "company": company, "status": "Open"}).insert(ignore_permissions=True)


def approve(doc):
    doc.status = "Approved"
    doc.submit()
    return doc


installed = frappe.db.get_value("Installed Application", {"app_name": "pepl_os"}, "app_version")
print("INFO  run " + RUN + " (test records end with it; all rolled back)")

# ---------------- 1. settings ----------------
check(version_parts(installed) >= version_parts(VERSION), "1. pepl_os " + str(installed) + " (needs " + VERSION + ")")
check(str(param("custom_el_days_worked_per_leave")) in ["20", "20.0"], "1. Earned Leave: 1 day per 20 days worked (" + str(param("custom_el_days_worked_per_leave")) + ")")
check(str(param("custom_attendance_lock_day")) == "7", "1. Attendance Lock Day 7 (" + str(param("custom_attendance_lock_day")) + ")")
types = [t.strip() for t in str(param("custom_leave_types_used") or "").splitlines() if t.strip()]
check(sorted(types) == ["Earned Leave", "Leave Without Pay"], "1. leave types used: " + ", ".join(types))
check(str(param("custom_sandwich_across_applications")) in ["1", "True"], "1. sandwich across two applications ON")
check(bool(param("custom_default_leave_approver")), "1. Default Leave Approver: " + str(param("custom_default_leave_approver")))
check(bool(param("custom_hr_head_leave_approver")), "1. Leave Approver of the HR Head: " + str(param("custom_hr_head_leave_approver")))
print("INFO  Earned Leave Counted From: " + str(param("custom_el_counted_from") or "not set yet (PEPL's go-live date)"))
companies = frappe.get_all("Company", pluck="name")
for co in companies:
    hla = frappe.db.exists("Holiday List Assignment", {"assigned_to": co, "holiday_list": HOLIDAY_LIST, "docstatus": 1})
    check(bool(hla), "1. company " + co + ": Holiday List Assignment of " + HOLIDAY_LIST + " (run the set-up rev 2 if not)")
check(frappe.db.exists("Scheduled Job Type", {"method": LV + ".daily_el_accrual"}), "1. the daily Earned Leave job is scheduled")
la_events = (frappe.get_hooks("doc_events") or {}).get("Leave Application") or {}
check(LV + ".before_submit_application" in (la_events.get("before_submit") or []), "1. only the leave approver approves (before_submit rule)")
el = frappe.db.get_value("Leave Type", "Earned Leave", ["include_holiday", "allow_negative"], as_dict=True)
check(bool(el) and el.include_holiday == 1 and el.allow_negative == 0, "1. Earned Leave: holidays inside count, never below zero")

# ---------------- 2. on test Employees (2027 dates) ----------------
company = companies[0]
if not frappe.db.exists("Gender", "Male"):
    frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
emp = new_employee("C83 Leave", {})
check(emp.leave_approver == param("custom_default_leave_approver"), "2. a new Employee gets the Default Leave Approver (" + str(emp.leave_approver) + ")")
allocate(emp, 10)
approve(application(emp, "2027-01-08", "2027-01-09", "Earned Leave"))
monday = application(emp, "2027-01-11", "2027-01-11", "Earned Leave")
check(str(monday.from_date) == "2027-01-10" and monday.total_leave_days == 2, "2. sandwich: Friday-Saturday then Monday -> Monday's leave starts Sunday, 2 days (" + str(monday.from_date) + ", " + str(monday.total_leave_days) + ")")
plain = application(emp, "2027-01-25", "2027-01-25", "Earned Leave")
check(str(plain.from_date) == "2027-01-25" and plain.total_leave_days == 1, "2. no leave on the other side: no sandwich (1 day)")
refused = False
try:
    application(emp, "2027-02-01", "2027-02-01", "Casual Leave")
except Exception:
    refused = True
check(refused, "2. a leave type PEPL does not use (Casual Leave) is refused")
refused = False
try:
    application(emp, "2027-03-01", "2027-03-31", "Earned Leave")
except Exception:
    refused = True
check(refused, "2. Earned Leave beyond the balance is refused")
lwp = application(emp, "2027-03-01", "2027-03-02", "Leave Without Pay")
check(lwp.total_leave_days == 2, "2. HR can enter the extra days as Leave Without Pay")
# a date inside the latest closed month (lock day 7): its year is the year the accrual works on
t = frappe.utils.today()
y = int(t[:4])
m = int(t[5:7]) - (1 if int(t[8:10]) > 7 else 2)
if m <= 0:
    m = m + 12
    y = y - 1
opening = new_employee("C83 Opening", {"custom_el_opening_balance": 3, "custom_el_opening_as_on": str(y) + "-" + str(m).zfill(2) + "-01"})
result = frappe.call(LV + ".run_el_accrual_now", employee=opening.name)
alloc = frappe.db.get_value("Leave Allocation", {"employee": opening.name, "leave_type": "Earned Leave", "docstatus": 1}, "new_leaves_allocated")
check(alloc == 3, "2. opening balance 3 -> Earned Leave allocation of 3 (" + str(alloc) + ")")
print("INFO  accrual result: " + str(result))

frappe.db.rollback()
print("")
print("Check 83: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
