# PEPL OS v0.80.0 - Cycle 4 H0 set-up: Frappe HR for PEPL (PEPL's decisions of 25 / 26 Nov 2026).
# System Console, Type = Python, logged in as Administrator.
# Run it FIRST with Commit UNTICKED (a preview: it prints what it would do and saves nothing), then again with
# Commit TICKED (it saves). Check after the ticked run that the record shows "commit": 1. Safe to run again.
#  1. HR Settings: leave approver required, nobody approves his own leave, no birthday / anniversary / holiday mails.
#  2. Holiday List "PEPL Holidays 2026-2027": every Sunday + PEPL's 2026 holidays (PDF "Holidays - 2026"); the default
#     list of every company that has none. 2027 holidays are added here when PEPL sends them (run again).
#  3. Leave Types: Earned Leave (sandwich, never below zero, carried forward) and Leave Without Pay (sandwich).
#  4. Leave Periods 2026 and 2027 (January - December) for every company.
#  5. Shift Types: one per active PEPL Shift, PEPL's rules from System Parameters -> People (late > 15 min, half day
#     < 4.5 h, absent < 4 h). Auto attendance OFF (attendance stays in Attendo for now).
#  6. Role Profiles: PEPL HR Manager -> Abhijay; PEPL HR Assistant -> Biswanath (hr@). A missing login is reported.
HOLIDAY_LIST = "PEPL Holidays 2026-2027"
FROM_DATE = "2026-01-01"
TO_DATE = "2027-12-31"
HOLIDAYS = [
    ["2026-01-23", "Saraswati Puja"],
    ["2026-01-26", "Republic Day"],
    ["2026-03-03", "Dol Jatra (Holi)"],
    ["2026-05-01", "May Day"],
    ["2026-08-15", "Independence Day"],
    ["2026-09-18", "Viswakarma Puja"],
    ["2026-10-19", "Durga Puja"],
    ["2026-10-20", "Durga Puja"],
    ["2026-10-21", "Durga Puja"],
    ["2026-11-09", "Kali Puja"],
    # 2027: add PEPL's holidays here when they arrive, e.g. ["2027-01-26", "Republic Day"],
]
YEARS = [2026, 2027]
HR_MANAGERS = ["abhijay@parasramkagroup.com"]
HR_ASSISTANTS = ["hr@parasramkagroup.com"]


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
print("Apps: " + ", ".join([k + " " + str(apps[k]) for k in apps]) + " - run by " + frappe.session.user)
problems = []
if frappe.session.user != "Administrator":
    problems.append("log in as Administrator and run again")
if "hrms" not in apps:
    problems.append("Frappe HR (hrms) is not installed on this site")
if version_parts(apps.get("frappe")) < [16, 60, 0]:
    problems.append("Frappe must be 16.60 or newer for Frappe HR (now " + str(apps.get("frappe")) + ")")
if version_parts(apps.get("pepl_os")) < [0, 80, 0]:
    problems.append("pepl_os must be 0.80.0 or newer (now " + str(apps.get("pepl_os")) + ")")
if problems:
    for p in problems:
        print("STOP  " + p)
    print("Nothing was changed.")
else:
    lines = frappe.call(
        "pepl_os.pepl_people.hr_setup.apply_hr_setup",
        holiday_list=HOLIDAY_LIST,
        from_date=FROM_DATE,
        to_date=TO_DATE,
        holidays=HOLIDAYS,
        years=YEARS,
        hr_managers=HR_MANAGERS,
        hr_assistants=HR_ASSISTANTS,
    )
    for line in lines:
        print(line)
    print("")
    print("DONE - saved only if Commit was ticked (the record must show \"commit\": 1). Then run Check 80.")
