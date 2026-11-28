"""C4-H3 - Earned Leave the PEPL way (decisions of 25 / 26 Nov 2026).

* Only Earned Leave and Leave Without Pay are applied for (System Parameters -> People: Leave Types Used at PEPL).
* Earned Leave: 1 day for every 20 days worked, from the first day; a Half Day counts 0.5 day worked. Days worked come
  from submitted Attendance (Present / Work From Home = 1, Half Day = 0.5). Counted only for months that are closed
  (after the Attendance Lock Day, 7th, of the next month), so a correction allowed before the lock is never missed.
  Each Employee's Earned Leave allocation of the calendar year (leave year January - December) is kept equal to:
  opening balance (if its date is in that year) + leave earned in that year. The part of 20 days not yet earned
  carries on to the next month and the next year. A daily job does it (safe to run again); HR can run it now.
* Opening balances: Employee fields "EL Opening Balance" and "EL Opening Balance As On" (PEPL sends them later);
  days worked are counted from the day after that date (or from "Earned Leave Counted From", the go-live date).
* New year: after December is closed (8 January), the new year's allocation is made with the balance carried forward
  (no cap until PEPL sets one on the Leave Type).
* Over the balance: refused (Earned Leave never below zero); HR enters the extra days as Leave Without Pay.
* Sandwich (PEPL): Sundays / holidays inside a leave count as leave (Leave Type "Include holidays"); and also when the
  leave days on both sides are in two separate applications - the later application is stretched over the holidays
  and says so in its reason.
* Approver: every Employee's Leave Approver is the "Default Leave Approver" (Abhijay); the approver's own leave goes
  to "Leave Approver of the HR Head" (Aviral). Only the leave approver (or a System Manager) approves or rejects.
"""

import math

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, get_first_day, get_last_day, getdate, today

from pepl_os.common import params
from pepl_os.pepl_people.hr_setup import EARNED_LEAVE

ATTENDANCE_WORKED = {"Present": 1, "Work From Home": 1, "Half Day": 0.5}

DAYS_PER_LEAVE_FIELD = "custom_el_days_worked_per_leave"
ACCRUAL_FROM_FIELD = "custom_el_counted_from"
LOCK_DAY_FIELD = "custom_attendance_lock_day"
DEFAULT_APPROVER_FIELD = "custom_default_leave_approver"
HEAD_APPROVER_FIELD = "custom_hr_head_leave_approver"
LEAVE_TYPES_FIELD = "custom_leave_types_used"
SANDWICH_FIELD = "custom_sandwich_across_applications"
OPENING_FIELD = "custom_el_opening_balance"
OPENING_DATE_FIELD = "custom_el_opening_as_on"
DEFAULT_DAYS_PER_LEAVE = 20
DEFAULT_LOCK_DAY = 7
DEFAULT_LEAVE_TYPES = "Earned Leave\nLeave Without Pay"


def lines(value):
	return [r.strip() for r in str(value or "").splitlines() if r.strip()]


def days_per_leave():
	return flt(params.get(DAYS_PER_LEAVE_FIELD, DEFAULT_DAYS_PER_LEAVE)) or DEFAULT_DAYS_PER_LEAVE


def lock_day():
	return min(28, max(1, cint(params.get(LOCK_DAY_FIELD, DEFAULT_LOCK_DAY)) or DEFAULT_LOCK_DAY))


def leave_types_used():
	return lines(params.get(LEAVE_TYPES_FIELD, DEFAULT_LEAVE_TYPES)) or lines(DEFAULT_LEAVE_TYPES)


def last_closed_day(on=None):
	"""Last day of the latest month whose attendance is closed: after the lock day, last month; before, the one before."""
	on = getdate(on or today())
	months_back = 1 if on.day > lock_day() else 2
	return get_last_day(add_months(get_first_day(on), -months_back))


# ---------------- days worked and leave earned ----------------
def days_worked(employee, from_date, to_date):
	if getdate(to_date) < getdate(from_date):
		return 0
	rows = frappe.get_all(
		"Attendance",
		filters={
			"employee": employee,
			"docstatus": 1,
			"attendance_date": ["between", [from_date, to_date]],
			"status": ["in", list(ATTENDANCE_WORKED)],
		},
		fields=["status"],
	)
	return sum(ATTENDANCE_WORKED[r.status] for r in rows)


def earned(employee, from_date, to_date):
	return math.floor(days_worked(employee, from_date, to_date) / days_per_leave() + 1e-9)


def counting_start(emp):
	"""First day whose work earns leave for this Employee, or None (nothing to count yet)."""
	starts = []
	counted_from = params.get(ACCRUAL_FROM_FIELD)
	if counted_from:
		starts.append(getdate(counted_from))
	if emp.get(OPENING_DATE_FIELD):
		starts.append(add_days(getdate(emp.get(OPENING_DATE_FIELD)), 1))
	if not starts:
		return None
	if emp.get("date_of_joining"):
		starts.append(getdate(emp.date_of_joining))
	return max(starts)


def target_for_year(emp, year, closed_to):
	"""New Earned Leave for `year`: opening (if dated in that year) + leave earned in that year up to closed_to."""
	opening = (
		flt(emp.get(OPENING_FIELD))
		if emp.get(OPENING_DATE_FIELD) and getdate(emp.get(OPENING_DATE_FIELD)).year == year
		else 0
	)
	start = counting_start(emp)
	if not start:
		return opening, 0, 0
	year_start = getdate(f"{year}-01-01")
	through = min(getdate(closed_to), getdate(f"{year}-12-31"))
	if through < start:
		return opening, 0, 0
	before = earned(emp.name, start, add_days(year_start, -1)) if start < year_start else 0
	in_year = earned(emp.name, start, through) - before
	worked = days_worked(emp.name, max(start, year_start), through)
	return opening + in_year, in_year, worked


# ---------------- the allocation ----------------
def allocation_of(employee, year):
	return frappe.db.get_value(
		"Leave Allocation",
		{
			"employee": employee,
			"leave_type": EARNED_LEAVE,
			"docstatus": 1,
			"from_date": [">=", f"{year}-01-01"],
			"to_date": ["<=", f"{year}-12-31"],
		},
		["name", "new_leaves_allocated", "total_leaves_allocated"],
		as_dict=True,
	)


def set_allocation(emp, year, target):
	"""Make the year's allocation hold `target` new leaves. Returns 'created', 'updated', 'same' or 'nothing'."""
	existing = allocation_of(emp.name, year)
	if existing:
		if flt(existing.new_leaves_allocated) == flt(target):
			return "same"
		doc = frappe.get_doc("Leave Allocation", existing.name)
		doc.new_leaves_allocated = target
		doc.flags.ignore_permissions = True
		doc.save()
		return "updated"
	had_last_year = bool(allocation_of(emp.name, year - 1))
	if not target and not had_last_year:
		return "nothing"
	from_date = max(getdate(f"{year}-01-01"), getdate(emp.date_of_joining or f"{year}-01-01"))
	doc = frappe.get_doc(
		{
			"doctype": "Leave Allocation",
			"employee": emp.name,
			"leave_type": EARNED_LEAVE,
			"from_date": from_date,
			"to_date": f"{year}-12-31",
			"new_leaves_allocated": target,
			"carry_forward": 1 if had_last_year else 0,
			"description": _("PEPL Earned Leave: 1 day per {0} days worked").format(days_per_leave()),
		}
	)
	doc.flags.ignore_permissions = True
	try:
		doc.insert()
	except frappe.ValidationError:
		if not target:  # nothing carried forward and nothing earned: Frappe HR refuses an empty allocation
			frappe.clear_last_message()
			return "nothing"
		raise
	doc.submit()
	return "created"


def accrue_employee(emp, on=None):
	"""Bring one Employee's Earned Leave up to date. Returns {year: (action, target, earned, days worked)}."""
	closed_to = last_closed_day(on)
	year = closed_to.year
	result = {}
	newer = allocation_of(emp.name, year + 1)
	if not newer:  # a year is final once the next year's allocation (carried forward) exists
		target, in_year, worked = target_for_year(emp, year, closed_to)
		result[year] = (set_allocation(emp, year, target), target, in_year, worked)
	if closed_to.month == 12:  # December closed: open the new year with the balance carried forward
		target, in_year, worked = target_for_year(emp, year + 1, closed_to)
		result[year + 1] = (set_allocation(emp, year + 1, target), target, in_year, worked)
	return result


EMPLOYEE_FIELDS = ["name", "employee_name", "date_of_joining", OPENING_FIELD, OPENING_DATE_FIELD]


def run_el_accrual(on=None):
	"""Daily job: every Active Employee. Never stops on one Employee. Returns {employee: result or error}."""
	results = {}
	if not frappe.db.exists("Leave Type", EARNED_LEAVE):
		return results
	for emp in frappe.get_all("Employee", filters={"status": "Active"}, fields=EMPLOYEE_FIELDS):
		frappe.db.savepoint("pepl_el")
		try:
			results[emp.name] = accrue_employee(emp, on)
		except Exception as e:
			frappe.db.rollback(save_point="pepl_el")
			frappe.clear_last_message()
			results[emp.name] = f"error: {e}"
			frappe.log_error(title=f"PEPL Earned Leave not updated: {emp.name}")
	return results


def daily_el_accrual():
	"""scheduler (daily)."""
	run_el_accrual()


@frappe.whitelist()
def run_el_accrual_now(employee=None):
	"""HR Manager / System Manager: bring Earned Leave up to date now (one Employee or all)."""
	frappe.only_for(("HR Manager", "System Manager"))
	if employee:
		emp = frappe.db.get_value("Employee", employee, EMPLOYEE_FIELDS, as_dict=True)
		return {employee: accrue_employee(emp)}
	return run_el_accrual()


# ---------------- Employee: leave approver ----------------
def default_approver_for(doc):
	default = params.get(DEFAULT_APPROVER_FIELD)
	head = params.get(HEAD_APPROVER_FIELD)
	if default and doc.get("user_id") == default:
		return head
	return default


def set_leave_approver(doc, method=None):
	"""doc_events: Employee validate - the PEPL approver when none is set, never the person himself."""
	if not doc.meta.has_field("leave_approver"):
		return
	wanted = default_approver_for(doc)
	if not doc.get("leave_approver") and wanted:
		doc.leave_approver = wanted
	elif doc.get("leave_approver") and doc.leave_approver == doc.get("user_id"):
		head = params.get(HEAD_APPROVER_FIELD)
		if head:
			doc.leave_approver = head


@frappe.whitelist()
def apply_leave_approvers():
	"""Give every Employee without one the PEPL approver (and the approver himself the HR head's approver)."""
	frappe.only_for(("HR Manager", "System Manager"))
	changed = []
	for name in frappe.get_all("Employee", filters={"status": ["!=", "Left"]}, pluck="name"):
		doc = frappe.get_doc("Employee", name)
		before = doc.get("leave_approver")
		set_leave_approver(doc)
		if doc.get("leave_approver") != before:
			doc.db_set("leave_approver", doc.leave_approver)
			changed.append(f"{name}: {doc.leave_approver}")
	return changed


# ---------------- Leave Application ----------------
def holiday_list_of(employee, on):
	from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

	return get_holiday_list_for_employee(employee, raise_exception=False, as_on=on)


def is_holiday(holiday_list, day):
	return bool(holiday_list) and bool(
		frappe.db.exists("Holiday", {"parent": holiday_list, "holiday_date": getdate(day)})
	)


def approved_leave_on(doc, day):
	"""An approved leave (with holidays counted) of the same Employee on `day`, other than doc."""
	return frappe.db.get_value(
		"Leave Application",
		{
			"employee": doc.employee,
			"docstatus": 1,
			"status": "Approved",
			"name": ["!=", doc.name or ""],
			"from_date": ["<=", getdate(day)],
			"to_date": [">=", getdate(day)],
			"leave_type": ["in", sandwich_leave_types()],
		},
		"name",
	)


def sandwich_leave_types():
	return frappe.get_all("Leave Type", filters={"include_holiday": 1}, pluck="name")


def stretch_for_sandwich(doc):
	"""Before validate: holidays between this leave and another approved leave count as leave (PEPL)."""
	if not params.is_enabled(SANDWICH_FIELD, 1) or cint(doc.get("half_day")):
		return None
	if doc.leave_type not in sandwich_leave_types() or not doc.from_date or not doc.to_date:
		return None
	notes = []
	hl = holiday_list_of(doc.employee, doc.from_date)
	# holidays just before
	day = add_days(getdate(doc.from_date), -1)
	block = []
	while is_holiday(hl, day) and len(block) < 15:
		block.append(day)
		day = add_days(day, -1)
	if block and (other := approved_leave_on(doc, day)):
		doc.from_date = block[-1]
		notes.append(
			_("From {0}: holidays between this leave and {1} count as leave (PEPL sandwich rule).").format(
				frappe.utils.formatdate(doc.from_date), other
			)
		)
	# holidays just after
	day = add_days(getdate(doc.to_date), 1)
	block = []
	while is_holiday(hl, day) and len(block) < 15:
		block.append(day)
		day = add_days(day, 1)
	if block and (other := approved_leave_on(doc, day)):
		doc.to_date = block[-1]
		notes.append(
			_("To {0}: holidays between this leave and {1} count as leave (PEPL sandwich rule).").format(
				frappe.utils.formatdate(doc.to_date), other
			)
		)
	if notes:
		doc.description = "\n".join([*(lines(doc.get("description"))), *notes])
		frappe.msgprint("<br>".join(notes), indicator="orange", alert=True)
	return notes


def before_validate_application(doc, method=None):
	"""doc_events: Leave Application before_validate."""
	stretch_for_sandwich(doc)


def validate_application(doc, method=None):
	"""doc_events: Leave Application validate - only PEPL's leave types."""
	if doc.leave_type not in leave_types_used():
		frappe.throw(
			_("{0} is not used at PEPL. Use one of: {1}.").format(
				doc.leave_type, ", ".join(leave_types_used())
			)
		)


def before_submit_application(doc, method=None):
	"""doc_events: Leave Application before_submit - only the leave approver (or a System Manager) decides."""
	if doc.status not in ("Approved", "Rejected"):
		return
	user = frappe.session.user
	if user == doc.get("leave_approver") or "System Manager" in frappe.get_roles(user):
		return
	frappe.throw(
		_("Only the leave approver {0} can approve or reject this leave.").format(
			doc.get("leave_approver") or "-"
		),
		frappe.PermissionError,
	)
