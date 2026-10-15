"""C3a-X2 - Shop-floor masters: shifts, downtime categories and operators.

These are the masters every production record in Cycle 3a points at: the Shift Production Entry (X1)
records a shift, an operator and stops by downtime category; the OEE job (X3) takes planned time from
the shift and losses from the categories; MTBF / MTTR (X4) count the breakdown categories; the skill
check (X7) reads the operator's level on the machine's group.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, to_timedelta, today

from pepl_os.common import params

SHIFT = "PEPL Shift"
DOWNTIME = "PEPL Downtime Category"
OPERATOR = "PEPL Operator"

PIN_DIGITS_FIELD = "custom_operator_pin_digits"
PIN_DIGITS_RANGE = (4, 6)

# Skill levels, lowest first. The number at the front is the level used by the skill check (X7).
LEVELS = (
	"1 - Trainee",
	"2 - Runs under supervision",
	"3 - Runs independently",
	"4 - Sets up and trains others",
)

UNPLANNED, PLANNED, PM = "Unplanned", "Planned", "PM / Calibration"

# Starting list, created once on install; PEPL's Production HOD confirms it in Phase 3 (Configure).
# (name, stop type, counts as a breakdown for MTBF / MTTR)
SEED_DOWNTIME_CATEGORIES = (
	("Breakdown - Mechanical", UNPLANNED, 1),
	("Breakdown - Electrical", UNPLANNED, 1),
	("Breakdown - Hydraulic / Pneumatic", UNPLANNED, 1),
	("Setup / Changeover", UNPLANNED, 0),
	("Tool Change", UNPLANNED, 0),
	("Waiting for Material", UNPLANNED, 0),
	("Waiting for Operator", UNPLANNED, 0),
	("Waiting for Drawing / Instruction", UNPLANNED, 0),
	("Waiting for Inspection", UNPLANNED, 0),
	("Quality Problem / Rework", UNPLANNED, 0),
	("Power Failure", UNPLANNED, 0),
	("Preventive Maintenance", PM, 0),
	("Calibration", PM, 0),
	("No Plan / No Load", PLANNED, 0),
	("Meeting / Training", PLANNED, 0),
	("Cleaning / 5S", PLANNED, 0),
)
SEEDED_FLAG = "pepl_downtime_categories_seeded"


# Install / migrate -----------------------------------------------------------------------------------


def ensure_production_masters():
	"""The default downtime categories, once. Afterwards PEPL may rename, disable or remove them."""
	if cint(frappe.db.get_default(SEEDED_FLAG)):
		return []
	made = []
	for name, stop_type, is_breakdown in SEED_DOWNTIME_CATEGORIES:
		if frappe.db.exists(DOWNTIME, name):
			continue
		frappe.get_doc(
			{
				"doctype": DOWNTIME,
				"category_name": name,
				"stop_type": stop_type,
				"is_breakdown": is_breakdown,
				"is_active": 1,
			}
		).insert(ignore_permissions=True)
		made.append(name)
	frappe.db.set_default(SEEDED_FLAG, 1)
	return made


# Shift -----------------------------------------------------------------------------------------------


def shift_minutes(start_time, end_time):
	"""Minutes from start to end; a shift that ends at or before its start runs past midnight."""
	start = to_timedelta(start_time).total_seconds() // 60
	end = to_timedelta(end_time).total_seconds() // 60
	return int((end - start) % (24 * 60))


def validate_shift(doc):
	length = shift_minutes(doc.start_time, doc.end_time)
	if not length:
		frappe.throw(_("Start time and end time are the same. A shift must have a length."))
	breaks = cint(doc.break_minutes)
	if breaks < 0:
		frappe.throw(_("Break minutes cannot be negative."))
	if breaks >= length:
		frappe.throw(
			_("Break ({0} minutes) must be shorter than the shift ({1} minutes).").format(breaks, length)
		)
	doc.planned_minutes = length - breaks
	doc.crosses_midnight = 1 if to_timedelta(doc.end_time) <= to_timedelta(doc.start_time) else 0


# Downtime category -----------------------------------------------------------------------------------


def downtime_effect(stop_type, is_breakdown):
	"""Plain words shown on the category: what this stop does to OEE and MTBF / MTTR."""
	if stop_type == PLANNED:
		return _("Planned stop: this time is taken out of planned production time, so it does not lower OEE.")
	if stop_type == PM:
		return _(
			"Preventive maintenance / calibration: taken out of planned production time when System Parameters "
			"say 'OEE: Exclude PM/Calibration from Planned Time'; otherwise it lowers availability."
		)
	text = _("Unplanned stop: counts against machine availability (OEE).")
	if cint(is_breakdown):
		text += " " + _("Breakdown: each stop counts as one failure for MTBF and its repair time for MTTR.")
	return text


def validate_downtime_category(doc):
	if cint(doc.is_breakdown) and doc.stop_type != UNPLANNED:
		frappe.throw(_("Only an Unplanned stop can be a breakdown (it counts towards MTBF / MTTR)."))
	doc.effect = downtime_effect(doc.stop_type, doc.is_breakdown)


# Operator --------------------------------------------------------------------------------------------


def pin_digits():
	low, high = PIN_DIGITS_RANGE
	digits = params.get_int(PIN_DIGITS_FIELD, low)
	return digits if low <= digits <= high else low


def _is_masked(value):
	return bool(value) and set(value) == {"*"}


def level_rank(level):
	"""1 to 4 for a level, 0 for none."""
	return LEVELS.index(level) + 1 if level in LEVELS else 0


def validate_operator(doc):
	pin = doc.get("pin")
	if pin and not _is_masked(pin):
		digits = pin_digits()
		if not pin.isdigit():
			frappe.throw(_("The PIN must be digits only."))
		if len(pin) != digits:
			frappe.throw(_("The PIN must be exactly {0} digits (System Parameters).").format(digits))
		doc.pin_changed_on = today()
	doc.pin_set = 1 if pin else 0

	if doc.user:
		other = frappe.db.get_value(OPERATOR, {"user": doc.user, "name": ["!=", doc.name or ""]}, "name")
		if other:
			frappe.throw(_("Login {0} is already linked to operator {1}.").format(doc.user, other))

	seen = set()
	for row in doc.get("skills") or []:
		if row.workstation_type in seen:
			frappe.throw(_("Machine group {0} is listed twice in the skills.").format(row.workstation_type))
		seen.add(row.workstation_type)
		if row.certified_on and row.valid_until and getdate(row.valid_until) < getdate(row.certified_on):
			frappe.throw(
				_("Row {0}: Valid Until cannot be before Certified On ({1}).").format(
					row.idx, row.workstation_type
				)
			)


def _skill_is_current(row, as_of=None):
	return not row.valid_until or getdate(row.valid_until) >= getdate(as_of or today())


def operator_level(operator, workstation, as_of=None):
	"""The operator's current level on the machine's group (Workstation Type), or None."""
	group = frappe.db.get_value("Workstation", workstation, "workstation_type")
	if not group or not frappe.db.exists(OPERATOR, operator):
		return None
	rows = frappe.get_all(
		"PEPL Operator Skill",
		filters={"parent": operator, "parenttype": OPERATOR, "workstation_type": group},
		fields=["level", "valid_until"],
	)
	for row in rows:
		if _skill_is_current(row, as_of):
			return row.level
	return None


def verify_operator_pin(operator, pin):
	"""True when the operator is active and the PIN matches. Used by the kiosk (code + PIN).

	Not whitelisted: the kiosk calls it behind its own rate limit.
	"""
	if not pin or not operator or not frappe.db.exists(OPERATOR, operator):
		return False
	if frappe.db.get_value(OPERATOR, operator, "status") != "Active":
		return False
	from frappe.utils.password import get_decrypted_password

	stored = get_decrypted_password(OPERATOR, operator, "pin", raise_exception=False)
	return bool(stored) and str(stored) == str(pin)


@frappe.whitelist()
def get_operator_panel(name):
	"""Rows for the operator form panel: PIN, status and machine groups with level and validity."""
	frappe.has_permission(OPERATOR, "read", name, throw=True)
	doc = frappe.get_doc(OPERATOR, name)
	rows = []
	if doc.status != "Active":
		rows.append({"text": _("Inactive: cannot enter shift production"), "colour": "gray"})
	if doc.pin_set:
		rows.append({"text": _("PIN set (changed {0})").format(doc.pin_changed_on or "-"), "colour": "green"})
	else:
		rows.append(
			{"text": _("No PIN yet: this operator cannot use the shop-floor kiosk"), "colour": "orange"}
		)

	if not doc.skills:
		rows.append({"text": _("No machine groups yet: add the skills below"), "colour": "orange"})
	for row in doc.skills:
		label = f"{row.workstation_type}: {row.level}"
		if not _skill_is_current(row):
			rows.append({"text": _("{0} - expired on {1}").format(label, row.valid_until), "colour": "red"})
		elif level_rank(row.level) >= 3:
			rows.append({"text": label, "colour": "green"})
		else:
			rows.append({"text": label, "colour": "orange"})
	return {"rows": rows}
