"""C3a-B3 - HR-lite as a Production feature (no payroll): operator master alignment, skill-matrix upkeep and
shift eligibility.

1. Operator master alignment. A PEPL Operator may point at the person's ERPNext Employee. Then the Employee leads:
   the operator's name, joining date and login come from it, and an Employee who is Left, Inactive or Suspended
   makes the operator Inactive (no kiosk, no shift entry). One Employee = one operator. Saving the Employee
   updates its operator.
2. Skill matrix. The report "PEPL Skill Matrix": every operator against every machine group, with the level,
   expired and soon-expiring skills, how many operators are qualified on each group (cover), and what is missing
   on each operator (PIN, skills, default shift, Employee). Settings: Skill Expiry Warning Days, Minimum Qualified
   Operators per Machine Group.
3. Shift eligibility. An operator's Eligible Shifts (empty = any). A shift entry or kiosk sign-in for another
   shift is warned (Warn: shown on the entry's Shift panel) or refused (Block), per Shift Eligibility Check.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, formatdate, getdate, today

from pepl_os.common import params
from pepl_os.pepl_production import masters

OPERATOR = masters.OPERATOR
SKILL = "PEPL Operator Skill"
SHIFT_ROW = "PEPL Operator Shift"
NOT_WORKING = ("Left", "Inactive", "Suspended")

ELIGIBILITY_FIELD = "custom_shift_eligibility_mode"
WARN, BLOCK = "Warn", "Block"
ELIGIBILITY_MODES = (WARN, BLOCK)
EXPIRY_FIELD = "custom_skill_expiry_warning_days"
DEFAULT_EXPIRY_DAYS = 30
COVER_FIELD = "custom_skill_min_cover"
DEFAULT_COVER = 2


# ---------------- settings ----------------
def eligibility_mode():
	value = params.get(ELIGIBILITY_FIELD, WARN)
	return value if value in ELIGIBILITY_MODES else WARN


def expiry_days():
	return max(0, cint(params.get(EXPIRY_FIELD, DEFAULT_EXPIRY_DAYS)))


def min_cover():
	return max(0, cint(params.get(COVER_FIELD, DEFAULT_COVER)))


def validate_params(doc):
	"""Errors for the B3 settings in System Parameters."""
	errors = []
	mode = doc.get(ELIGIBILITY_FIELD)
	if mode not in (None, "") and mode not in ELIGIBILITY_MODES:
		errors.append(_("Shift Eligibility Check must be Warn or Block."))
	for field, label in (
		(EXPIRY_FIELD, _("Skill Expiry Warning Days")),
		(COVER_FIELD, _("Minimum Qualified Operators per Machine Group")),
	):
		value = doc.get(field)
		if value not in (None, "") and cint(value) < 0:
			errors.append(_("{0} cannot be negative.").format(label))
	return errors


# ---------------- 1. operator <-> Employee ----------------
def align_with_employee(doc):
	"""Operator validate: take the Employee's name, joining date, login and working status."""
	if not doc.get("employee"):
		return
	other = frappe.db.get_value(OPERATOR, {"employee": doc.employee, "name": ["!=", doc.name or ""]}, "name")
	if other:
		frappe.throw(_("Employee {0} is already operator {1}.").format(doc.employee, other))
	emp = frappe.db.get_value(
		"Employee", doc.employee, ["employee_name", "date_of_joining", "user_id", "status"], as_dict=True
	)
	if not emp:
		return
	if emp.employee_name:
		doc.operator_name = emp.employee_name
	if emp.date_of_joining:
		doc.joining_date = emp.date_of_joining
	if emp.user_id:
		doc.user = emp.user_id
	if emp.status in NOT_WORKING and doc.status != "Inactive":
		doc.status = "Inactive"
		frappe.msgprint(
			_("Operator set to Inactive: Employee {0} is {1}.").format(doc.employee, _(emp.status)),
			indicator="orange",
			alert=True,
		)


def on_employee_update(doc, method=None):
	"""doc_events: Employee on_update - the linked operator follows."""
	name = frappe.db.get_value(OPERATOR, {"employee": doc.name}, "name")
	if not name:
		return
	op = frappe.get_doc(OPERATOR, name)
	before = (op.operator_name, str(op.joining_date or ""), op.user, op.status)
	align_with_employee(op)
	if (op.operator_name, str(op.joining_date or ""), op.user, op.status) != before:
		op.flags.ignore_permissions = True
		op.save()


def check_eligible_shifts(doc):
	"""Operator validate: no shift twice; the default shift is one of the eligible ones."""
	shifts = [r.shift for r in doc.get("eligible_shifts") or []]
	if len(shifts) != len(set(shifts)):
		frappe.throw(_("A shift is listed twice in Eligible Shifts."))
	if shifts and doc.get("default_shift") and doc.default_shift not in shifts:
		frappe.throw(
			_("Default Shift {0} is not one of the Eligible Shifts ({1}).").format(
				doc.default_shift, ", ".join(shifts)
			)
		)


# ---------------- 3. shift eligibility ----------------
def eligible_shifts(operator):
	if not operator:
		return []
	return frappe.get_all(
		SHIFT_ROW, filters={"parent": operator, "parenttype": OPERATOR}, pluck="shift", order_by="idx"
	)


def is_eligible(operator, shift):
	shifts = eligible_shifts(operator)
	return not shifts or shift in shifts


def not_eligible_text(operator, shift):
	return _("Operator {0} is not set to work the {1} shift (eligible: {2}).").format(
		operator, shift, ", ".join(eligible_shifts(operator))
	)


def check_entry(doc):
	"""Shift entry validate: refused in Block mode; Warn shows on the Shift panel."""
	if not doc.get("operator") or not doc.get("shift") or is_eligible(doc.operator, doc.shift):
		return
	if eligibility_mode() == BLOCK:
		frappe.throw(
			not_eligible_text(doc.operator, doc.shift)
			+ " "
			+ _("Ask the foreman to change the shift or the operator's Eligible Shifts.")
		)


def check_sign_in(operator, shift):
	"""Kiosk sign-in: refused in Block mode."""
	if eligibility_mode() == BLOCK and not is_eligible(operator, shift):
		frappe.throw(_("You are not set to work the {0} shift. Ask the foreman.").format(shift))


def panel_row(doc):
	"""Shift panel row when the operator is outside his eligible shifts, else None."""
	if not doc.get("operator") or not doc.get("shift") or is_eligible(doc.operator, doc.shift):
		return None
	return {"text": not_eligible_text(doc.operator, doc.shift), "colour": "orange"}


# ---------------- 2. skills ----------------
def skill_state(row, as_of=None, warn_days=None):
	"""'expired', 'expiring' (within the warning days) or 'current'. `row` may be a plain dict (CI #49)."""
	as_of = getdate(as_of or today())
	if not row.get("valid_until"):
		return "current"
	left = date_diff(row.get("valid_until"), as_of)
	if left < 0:
		return "expired"
	days = expiry_days() if warn_days is None else warn_days
	return "expiring" if left <= days else "current"


def operator_issues(op, skills, as_of=None):
	"""What is missing or needs action on one operator, in plain words."""
	issues = []
	if op.status != "Active":
		return issues
	if not cint(op.pin_set):
		issues.append(_("no PIN"))
	if not skills:
		issues.append(_("no skills"))
	if not op.default_shift:
		issues.append(_("no default shift"))
	if not op.employee:
		issues.append(_("not linked to an Employee"))
	elif frappe.db.get_value("Employee", op.employee, "status") in NOT_WORKING:
		issues.append(_("Employee is not working"))
	for row in skills:
		state = skill_state(row, as_of)
		if state == "expired":
			issues.append(_("{0} expired {1}").format(row.workstation_type, formatdate(row.valid_until)))
		elif state == "expiring":
			issues.append(_("{0} expires {1}").format(row.workstation_type, formatdate(row.valid_until)))
	return issues


def machine_groups(filters):
	if filters.get("workstation_type"):
		return [filters["workstation_type"]]
	used = set(
		frappe.get_all("Workstation", filters={"workstation_type": ["is", "set"]}, pluck="workstation_type")
	)
	used |= set(frappe.get_all(SKILL, filters={"parenttype": OPERATOR}, pluck="workstation_type"))
	return sorted(g for g in used if g)


def matrix(filters=None):
	"""(groups, operator rows, cover row, thin groups) for the Skill Matrix report."""
	filters = frappe._dict(filters or {})
	as_of = getdate(filters.get("as_of") or today())
	groups = machine_groups(filters)
	keys = {g: "g" + str(i) for i, g in enumerate(groups)}
	conditions = {}
	if filters.get("status"):
		conditions["status"] = filters["status"]
	operators = frappe.get_all(
		OPERATOR,
		filters=conditions,
		fields=["name", "operator_name", "status", "default_shift", "employee", "pin_set"],
		order_by="name",
	)
	skills = {}
	for row in frappe.get_all(
		SKILL,
		filters={"parenttype": OPERATOR},
		fields=["parent", "workstation_type", "level", "valid_until"],
	):
		skills.setdefault(row.parent, []).append(row)
	needed = masters.level_rank(_min_level())
	cover = dict.fromkeys(groups, 0)
	rows = []
	for op in operators:
		mine = skills.get(op.name, [])
		row = {
			"operator": op.name,
			"operator_name": op.operator_name,
			"status": op.status,
			"default_shift": op.default_shift or "",
			"eligible_shifts": ", ".join(eligible_shifts(op.name)) or _("any"),
			"employee": op.employee or "",
		}
		for group in groups:
			key = keys[group]
			skill = next((s for s in mine if s.workstation_type == group), None)
			if not skill:
				row[key], row[key + "_colour"] = "", ""
				continue
			rank = masters.level_rank(skill.level)
			state = skill_state(skill, as_of)
			if state == "expired":
				row[key], row[key + "_colour"] = _("{0} expired").format(rank), "red"
				continue
			text = str(rank)
			if state == "expiring":
				text += " " + _("(to {0})").format(formatdate(skill.valid_until))
			row[key] = text
			row[key + "_colour"] = "orange" if state == "expiring" or rank < needed else "green"
			if rank >= needed and op.status == "Active":
				cover[group] += 1
		row["issues"] = "; ".join(operator_issues(op, mine, as_of))
		rows.append(row)
	want = min_cover()
	cover_row = {
		"operator": "",
		"operator_name": _("Qualified operators (level {0}+)").format(needed),
		"is_cover": 1,
	}
	for group in groups:
		cover_row[keys[group]] = str(cover[group])
		cover_row[keys[group] + "_colour"] = "red" if cover[group] < want else "green"
	thin = [g for g in groups if cover[g] < want]
	return groups, keys, rows, cover_row, thin


def _min_level():
	from pepl_os.pepl_production import skill

	return skill.min_level()


@frappe.whitelist()
def get_operator_hr_panel(name):
	"""Extra rows for the operator form: Employee alignment, eligible shifts, skills expiring soon."""
	frappe.has_permission(OPERATOR, "read", name, throw=True)
	doc = frappe.get_doc(OPERATOR, name)
	rows = []
	if doc.employee:
		status = frappe.db.get_value("Employee", doc.employee, "status")
		rows.append(
			{
				"text": _("Employee {0} ({1})").format(doc.employee, _(status or "")),
				"colour": "red" if status in NOT_WORKING else "green",
			}
		)
	else:
		rows.append({"text": _("Not linked to an Employee"), "colour": "gray"})
	shifts = [r.shift for r in doc.get("eligible_shifts") or []]
	rows.append(
		{
			"text": _("Eligible shifts: {0}").format(", ".join(shifts))
			if shifts
			else _("Eligible shifts: any"),
			"colour": "gray",
		}
	)
	for row in doc.skills:
		if skill_state(row) == "expiring":
			rows.append(
				{
					"text": _("{0} expires on {1} ({2} days)").format(
						row.workstation_type, formatdate(row.valid_until), date_diff(row.valid_until, today())
					),
					"colour": "orange",
				}
			)
	return {"rows": rows}
