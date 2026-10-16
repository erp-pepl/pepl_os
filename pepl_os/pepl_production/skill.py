"""C3a-X7 - Operator skill check on the Shift Production Entry.

The operator's level on the machine's group (Workstation Type), valid on the shift date, is compared with
the minimum level in System Parameters. What happens when it falls short depends on the Skill Check Mode
(a pepl_sales System Parameter, signed off by PEPL):

- Advisory: the entry is saved and submitted; the shortfall is shown.
- Soft Block: the entry is saved; submitting it needs a reason, which goes to the Override Log
  (rule PRD-SKILL). When "Enforce Override Reason" is off, it only warns.
- Hard Block: the entry is refused.

A machine without a group cannot be checked: the entry says "Not checked" and is never blocked.
"""

import frappe
from frappe import _

from pepl_os.common.overrides import has_recent_override
from pepl_os.pepl_production import masters

SYSTEM_PARAMETERS = "PEPL System Parameters"
MODE_FIELD = "skill_check_mode"  # owned by pepl_sales
MIN_LEVEL_FIELD = "custom_skill_min_level"
ENFORCE_FIELD = "custom_enforce_override_reason"
RULE_CODE = "PRD-SKILL"

ADVISORY, SOFT, HARD = "Advisory", "Soft Block", "Hard Block"
MODES = (ADVISORY, SOFT, HARD)
QUALIFIED, NOT_QUALIFIED, NOT_CHECKED = "Qualified", "Not qualified", "Not checked"
NO_LEVEL = "None"
DEFAULT_MIN_LEVEL = masters.LEVELS[2]


def _single(field):
	# cache=False: a change made in System Parameters applies to the very next entry.
	return frappe.db.get_single_value(SYSTEM_PARAMETERS, field, cache=False)


def mode():
	value = _single(MODE_FIELD)
	return value if value in MODES else SOFT


def min_level():
	value = _single(MIN_LEVEL_FIELD)
	return value if value in masters.LEVELS else DEFAULT_MIN_LEVEL


def reasons_enforced():
	value = _single(ENFORCE_FIELD)
	return True if value in (None, "") else bool(int(value))


def evaluate(doc):
	"""Set skill_level and skill_status on the entry. Returns the status."""
	group = frappe.db.get_value("Workstation", doc.workstation, "workstation_type")
	if not group:
		doc.skill_level, doc.skill_status = "", NOT_CHECKED
		return NOT_CHECKED
	level = masters.operator_level(doc.operator, doc.workstation, as_of=doc.posting_date)
	doc.skill_level = level or NO_LEVEL
	ok = masters.level_rank(level) >= masters.level_rank(min_level())
	doc.skill_status = QUALIFIED if ok else NOT_QUALIFIED
	return doc.skill_status


def shortfall_message(doc):
	group = frappe.db.get_value("Workstation", doc.workstation, "workstation_type")
	has = doc.skill_level if doc.skill_level and doc.skill_level != NO_LEVEL else _("no valid skill")
	return _("Operator {0} is not qualified on machine group {1}: needs level {2}, has {3}.").format(
		doc.operator, group, min_level(), has
	)


def check_on_save(doc):
	"""Called from the entry's validate."""
	if evaluate(doc) != NOT_QUALIFIED:
		return
	current = mode()
	if current == HARD:
		frappe.throw(
			_(
				"{0} Skill Check Mode is Hard Block: choose a qualified operator or update the skill matrix."
			).format(shortfall_message(doc)),
			title=_("Operator not qualified"),
		)
	frappe.msgprint(shortfall_message(doc), indicator="orange", alert=True)


def gate_message(doc):
	"""The message the form shows before submit (Soft Block, no reason logged yet), else None."""
	if doc.skill_status != NOT_QUALIFIED or mode() != SOFT or not reasons_enforced():
		return None
	if doc.name and has_recent_override(RULE_CODE, doc.doctype, doc.name):
		return None
	return shortfall_message(doc)


def check_on_submit(doc):
	"""Called from the entry's before_submit, after the minutes and photo rules."""
	message = gate_message(doc)
	if message:
		frappe.throw(
			f"[{RULE_CODE}] " + message + " " + _("A reason is required to continue."),
			title=_("Reason required"),
		)


@frappe.whitelist()
def skill_gate_check(name):
	"""For the form: {rule_code, message} when a reason must be given before submit, else None."""
	doc = frappe.get_doc("PEPL Shift Production Entry", name)
	doc.check_permission("read")
	message = gate_message(doc)
	return {"rule_code": RULE_CODE, "message": message} if message else None


def panel_row(doc):
	"""One line for the entry panel."""
	if doc.skill_status == QUALIFIED:
		return {
			"text": _("Operator qualified on this machine group ({0})").format(doc.skill_level),
			"colour": "green",
		}
	if doc.skill_status == NOT_QUALIFIED:
		return {"text": shortfall_message(doc) + " " + _("Mode: {0}.").format(mode()), "colour": "orange"}
	return {"text": _("Skill not checked: the machine has no machine group"), "colour": "gray"}
