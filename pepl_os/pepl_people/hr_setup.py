"""C4-H0 - Frappe HR (HRMS) set up for PEPL.

PEPL approved Frappe HR in writing (26 Nov 2026). Payroll stays out: its screens are installed with the app but not
configured. What this module sets up on a site (run by docs/checks/setup_c4_h0_hr.py, Commit ticked):

1. HR Settings: a leave approver is required, nobody approves his own leave, no birthday / anniversary / holiday mails.
2. PEPL's Holiday List: every Sunday (weekly off) plus PEPL's holidays, the default list of every company that has none.
3. Leave Types: "Earned Leave" (PEPL's only leave: holidays inside a leave count - sandwich -, never below zero,
   carried forward) and HRMS's "Leave Without Pay" (sandwich too). The 1-per-20-days accrual comes in H3.
4. Leave Periods: one per calendar year (PEPL's leave year is January - December) for every company.
5. Shift Types: one per active PEPL Shift (same name, same times), with PEPL's attendance rules from System Parameters
   -> People (late after 15 minutes, half day below 4.5 hours, absent below 4 hours). Auto attendance stays OFF:
   attendance is recorded in Attendo for now (PEPL, 26 Nov 2026).
6. Role Profiles PEPL HR Manager (Abhijay) and PEPL HR Assistant (Biswanath) added to the logins given.

Everything is safe to run again: existing records are completed, never deleted.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate

from pepl_os.common import params

EARNED_LEAVE = "Earned Leave"
LEAVE_WITHOUT_PAY = "Leave Without Pay"
HR_MANAGER_PROFILE = "PEPL HR Manager"
HR_ASSISTANT_PROFILE = "PEPL HR Assistant"

# HR Settings PEPL decided (25 / 26 Nov 2026). Field names checked against frappe/hrms version-16.
HR_SETTINGS = {
	"leave_approver_mandatory_in_leave_application": 1,
	"prevent_self_leave_approval": 1,
	"send_birthday_reminders": 0,
	"send_work_anniversary_reminders": 0,
	"send_holiday_reminders": 0,
}

EARNED_LEAVE_FLAGS = {
	"include_holiday": 1,  # sandwich: Sundays / holidays inside a leave count as leave
	"allow_negative": 0,  # never below the balance (HR takes the rest as Leave Without Pay)
	"is_carry_forward": 1,  # cap: PEPL tells later (empty = no cap)
	"is_earned_leave": 0,  # HRMS's own earned-leave job allocates a fixed number; PEPL's 1-per-20 job does it (H3)
	"is_lwp": 0,
	"allow_encashment": 0,  # payroll is out of scope
}
LWP_FLAGS = {"include_holiday": 1, "is_lwp": 1}

# System Parameters -> People: PEPL's attendance rules (26 Nov 2026)
GRACE_FIELD = "custom_late_entry_grace_minutes"
HALF_DAY_FIELD = "custom_half_day_below_hours"
ABSENT_FIELD = "custom_absent_below_hours"
DEFAULT_GRACE = 15
DEFAULT_HALF_DAY = 4.5
DEFAULT_ABSENT = 4


# ---------------- settings ----------------
def attendance_rules():
	return {
		"late_entry_grace_period": max(0, cint(params.get(GRACE_FIELD, DEFAULT_GRACE))),
		"working_hours_threshold_for_half_day": flt(params.get(HALF_DAY_FIELD, DEFAULT_HALF_DAY)),
		"working_hours_threshold_for_absent": flt(params.get(ABSENT_FIELD, DEFAULT_ABSENT)),
	}


def validate_params(doc):
	"""Errors for System Parameters -> People."""
	errors = []
	grace = doc.get(GRACE_FIELD)
	if grace not in (None, "") and not 0 <= cint(grace) <= 120:
		errors.append(_("Late Entry Grace (Minutes) must be between 0 and 120."))
	half = doc.get(HALF_DAY_FIELD)
	absent = doc.get(ABSENT_FIELD)
	half = DEFAULT_HALF_DAY if half in (None, "") else flt(half)
	absent = DEFAULT_ABSENT if absent in (None, "") else flt(absent)
	if not 0 <= absent <= 24 or not 0 <= half <= 24:
		errors.append(_("Half Day and Absent hours must be between 0 and 24."))
	elif absent > half:
		errors.append(
			_("Absent Below (Hours) {0} cannot be more than Half Day Below (Hours) {1}.").format(absent, half)
		)
	return errors


# ---------------- 1. HR Settings ----------------
def apply_hr_settings():
	"""Returns the fields changed."""
	doc = frappe.get_doc("HR Settings")
	changed = [f for f, v in HR_SETTINGS.items() if doc.meta.has_field(f) and cint(doc.get(f)) != v]
	if changed:
		for f in changed:
			doc.set(f, HR_SETTINGS[f])
		doc.flags.ignore_permissions = True
		doc.save()
	return changed


# ---------------- 2. Holiday List ----------------
def sundays(from_date, to_date):
	"""Every Sunday from from_date to to_date (inclusive)."""
	start = getdate(from_date)
	first = add_days(start, (6 - start.weekday()) % 7)
	return [getdate(add_days(first, 7 * i)) for i in range(date_diff(to_date, first) // 7 + 1)]


def ensure_holiday_list(name, from_date, to_date, holidays):
	"""PEPL's Holiday List: every Sunday + `holidays` ([date, description], ...). Adds what is missing, never deletes.

	Returns {"created": bool, "added": [dates added]}.
	"""
	from_date = getdate(from_date)
	to_date = getdate(to_date)
	created = not frappe.db.exists("Holiday List", name)
	if created:
		doc = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": from_date,
				"to_date": to_date,
				"weekly_off": "Sunday",
			}
		)
	else:
		doc = frappe.get_doc("Holiday List", name)
		if getdate(doc.to_date) < to_date:
			doc.to_date = to_date
		if getdate(doc.from_date) > from_date:
			doc.from_date = from_date
	have = {getdate(r.holiday_date) for r in doc.holidays}
	added = []
	for day in sundays(from_date, to_date):
		if day not in have:
			doc.append("holidays", {"holiday_date": day, "description": _("Sunday"), "weekly_off": 1})
			have.add(day)
			added.append(day)
	for row in holidays or []:
		day = getdate(row[0])
		if not from_date <= day <= to_date:
			frappe.throw(
				_("Holiday {0} ({1}) is outside {2} to {3}.").format(day, row[1], from_date, to_date)
			)
		if day not in have:
			doc.append("holidays", {"holiday_date": day, "description": row[1], "weekly_off": 0})
			have.add(day)
			added.append(day)
	if created or added:
		doc.holidays.sort(key=lambda r: getdate(r.holiday_date))
		for i, r in enumerate(doc.holidays, start=1):
			r.idx = i
		doc.flags.ignore_permissions = True
		doc.save()
	return {"created": created, "added": added}


def set_company_holiday_lists(name):
	"""The list becomes the default of every company that has none. Returns {company: "set" | "kept <other>"}."""
	result = {}
	for co in frappe.get_all("Company", fields=["name", "default_holiday_list"]):
		if not co.default_holiday_list:
			frappe.db.set_value("Company", co.name, "default_holiday_list", name)
			result[co.name] = "set"
		elif co.default_holiday_list != name:
			result[co.name] = "kept " + co.default_holiday_list
	return result


# ---------------- 3. Leave Types ----------------
def ensure_leave_types():
	"""Earned Leave created / completed and Leave Without Pay given PEPL's flags. Returns what changed."""
	changed = {}
	for leave_type, flags in ((EARNED_LEAVE, EARNED_LEAVE_FLAGS), (LEAVE_WITHOUT_PAY, LWP_FLAGS)):
		if frappe.db.exists("Leave Type", leave_type):
			doc = frappe.get_doc("Leave Type", leave_type)
			diff = [f for f, v in flags.items() if cint(doc.get(f)) != v]
			if not diff:
				continue
			for f in diff:
				doc.set(f, flags[f])
		else:
			doc = frappe.get_doc({"doctype": "Leave Type", "leave_type_name": leave_type, **flags})
			diff = ["created"]
		doc.flags.ignore_permissions = True
		doc.save()
		changed[leave_type] = diff
	return changed


# ---------------- 4. Leave Periods ----------------
def ensure_leave_periods(years):
	"""One active Leave Period per calendar year for every company. Returns the periods created."""
	created = []
	for company in frappe.get_all("Company", pluck="name"):
		for year in years:
			start = getdate(f"{cint(year)}-01-01")
			end = getdate(f"{cint(year)}-12-31")
			if frappe.db.exists("Leave Period", {"company": company, "from_date": start, "to_date": end}):
				continue
			frappe.get_doc(
				{
					"doctype": "Leave Period",
					"company": company,
					"from_date": start,
					"to_date": end,
					"is_active": 1,
				}
			).insert(ignore_permissions=True)
			created.append(f"{company} {year}")
	return created


# ---------------- 5. Shift Types ----------------
def pepl_shift_names():
	return frappe.get_all("PEPL Shift", filters={"is_active": 1}, pluck="name", order_by="name")


def ensure_shift_types(holiday_list=None):
	"""One Shift Type per active PEPL Shift, same name and times, PEPL's rules. Returns {shift: created | updated}."""
	rules = attendance_rules()
	result = {}
	for name in pepl_shift_names():
		shift = frappe.db.get_value("PEPL Shift", name, ["start_time", "end_time"], as_dict=True)
		values = {
			"start_time": shift.start_time,
			"end_time": shift.end_time,
			"determine_check_in_and_check_out": "Alternating entries as IN and OUT during the same shift",
			"working_hours_calculation_based_on": "First Check-in and Last Check-out",
			"enable_late_entry_marking": 1,
			**rules,
		}
		if holiday_list:
			values["holiday_list"] = holiday_list
		if frappe.db.exists("Shift Type", name):
			doc = frappe.get_doc("Shift Type", name)
			if all(str(doc.get(f) or "") == str(v or "") for f, v in values.items()):
				continue
			doc.update(values)
			doc.flags.ignore_permissions = True
			doc.save()
			result[name] = "updated"
		else:
			# Shift Type is named by prompt: the name goes in __newname
			doc = frappe.get_doc(
				{"doctype": "Shift Type", "__newname": name, "enable_auto_attendance": 0, **values}
			)
			doc.insert(ignore_permissions=True)
			result[name] = "created"
	return result


def apply_rules_to_shift_types():
	"""A change in System Parameters -> People reaches the Shift Types of the PEPL Shifts at once."""
	rules = attendance_rules()
	changed = []
	for name in pepl_shift_names():
		if not frappe.db.exists("Shift Type", name):
			continue
		doc = frappe.get_doc("Shift Type", name)
		if all(flt(doc.get(f)) == flt(v) for f, v in rules.items()):
			continue
		doc.update(rules)
		doc.flags.ignore_permissions = True
		doc.save()
		changed.append(name)
	return changed


def on_parameters_update(doc, method=None):
	"""doc_events: PEPL System Parameters on_update. Never stops the save."""
	if not frappe.db.exists("DocType", "Shift Type"):
		return
	try:
		apply_rules_to_shift_types()
	except Exception:
		frappe.log_error(title="PEPL: Shift Type rules not updated")


# ---------------- 6. Role Profiles on logins ----------------
def profile_field():
	return (
		frappe.get_all(
			"DocField", filters={"parent": "User", "options": "User Role Profile"}, pluck="fieldname"
		)
		or [None]
	)[0]


def add_profile(user, profile):
	"""Add a Role Profile to a login (keeps its other profiles). Returns 'added', 'had it' or 'no such login'."""
	if not frappe.db.exists("User", user):
		return "no such login"
	field = profile_field()
	doc = frappe.get_doc("User", user)
	if field:
		have = [r.role_profile for r in doc.get(field) or []]
		if profile in have:
			return "had it"
		doc.append(field, {"role_profile": profile})
	else:  # an older Frappe with one profile per login
		if doc.role_profile_name == profile:
			return "had it"
		doc.role_profile_name = profile
	doc.flags.ignore_permissions = True
	doc.save()
	return "added"


# ---------------- the set-up ----------------
@frappe.whitelist()
def apply_hr_setup(holiday_list, from_date, to_date, holidays, years, hr_managers=None, hr_assistants=None):
	"""Run 1-6. System Manager only. Returns the lines to print. Commit is the caller's (System Console)."""
	frappe.only_for("System Manager")
	holidays = frappe.parse_json(holidays) if isinstance(holidays, str) else holidays
	years = frappe.parse_json(years) if isinstance(years, str) else years
	hr_managers = frappe.parse_json(hr_managers) if isinstance(hr_managers, str) else hr_managers or []
	hr_assistants = (
		frappe.parse_json(hr_assistants) if isinstance(hr_assistants, str) else hr_assistants or []
	)
	if not frappe.db.exists("DocType", "HR Settings"):
		frappe.throw(_("Frappe HR (hrms) is not installed on this site."))
	lines = []
	changed = apply_hr_settings()
	lines.append("1. HR Settings: " + (", ".join(changed) + " set" if changed else "already as PEPL decided"))
	hl = ensure_holiday_list(holiday_list, from_date, to_date, holidays)
	lines.append(
		"2. Holiday List "
		+ holiday_list
		+ (" created" if hl["created"] else " exists")
		+ f", {len(hl['added'])} day(s) added, "
		+ str(len(frappe.get_doc("Holiday List", holiday_list).holidays))
		+ " days in it"
	)
	for company, state in set_company_holiday_lists(holiday_list).items():
		lines.append(f"2. Company {company}: default holiday list {state}")
	lt = ensure_leave_types()
	lines.append(
		"3. Leave Types: " + ("; ".join(f"{k}: {', '.join(v)}" for k, v in lt.items()) or "already right")
	)
	lp = ensure_leave_periods(years)
	lines.append("4. Leave Periods created: " + (", ".join(lp) or "none needed"))
	st = ensure_shift_types(holiday_list)
	if not pepl_shift_names():
		lines.append(
			"5. Shift Types: no active PEPL Shift on this site yet - none made (PEPL's shift times needed)"
		)
	else:
		lines.append("5. Shift Types: " + ("; ".join(f"{k} {v}" for k, v in st.items()) or "already right"))
	for user in hr_managers:
		lines.append(f"6. {user}: {HR_MANAGER_PROFILE} {add_profile(user, HR_MANAGER_PROFILE)}")
	for user in hr_assistants:
		lines.append(f"6. {user}: {HR_ASSISTANT_PROFILE} {add_profile(user, HR_ASSISTANT_PROFILE)}")
	return lines


@frappe.whitelist()
def hr_setup_status(holiday_list, years):
	"""Read-only facts for Check 80 (the System Console cannot read some of these itself)."""
	frappe.only_for("System Manager")
	years = frappe.parse_json(years) if isinstance(years, str) else years
	hr = frappe.get_doc("HR Settings") if frappe.db.exists("DocType", "HR Settings") else None
	status = {
		"hr_settings": {f: cint(hr.get(f)) for f in HR_SETTINGS} if hr else {},
		"holiday_list": None,
		"companies": {
			c.name: c.default_holiday_list
			for c in frappe.get_all("Company", fields=["name", "default_holiday_list"])
		},
		"leave_types": {},
		"leave_periods": {},
		"shift_types": {},
		"rules": attendance_rules(),
	}
	if frappe.db.exists("Holiday List", holiday_list):
		doc = frappe.get_doc("Holiday List", holiday_list)
		status["holiday_list"] = {
			"from_date": str(doc.from_date),
			"to_date": str(doc.to_date),
			"weekly_off": len([r for r in doc.holidays if cint(r.weekly_off)]),
			"holidays": [
				[str(r.holiday_date), r.description] for r in doc.holidays if not cint(r.weekly_off)
			],
			"sundays_expected": len(sundays(doc.from_date, doc.to_date)),
		}
	for lt in (EARNED_LEAVE, LEAVE_WITHOUT_PAY):
		if frappe.db.exists("Leave Type", lt):
			status["leave_types"][lt] = frappe.db.get_value(
				"Leave Type", lt, list(EARNED_LEAVE_FLAGS), as_dict=True
			)
	for company in frappe.get_all("Company", pluck="name"):
		status["leave_periods"][company] = [
			y
			for y in years
			if frappe.db.exists(
				"Leave Period",
				{"company": company, "from_date": f"{cint(y)}-01-01", "to_date": f"{cint(y)}-12-31"},
			)
		]
	for name in pepl_shift_names():
		status["shift_types"][name] = (
			frappe.db.get_value(
				"Shift Type",
				name,
				[
					"start_time",
					"end_time",
					"holiday_list",
					"enable_auto_attendance",
					"enable_late_entry_marking",
					*attendance_rules(),
				],
				as_dict=True,
			)
			if frappe.db.exists("Shift Type", name)
			else None
		)
	return status
