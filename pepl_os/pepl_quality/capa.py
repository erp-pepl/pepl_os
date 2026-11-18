"""C3b-Q4 - Corrective and Preventive Action (PEPL CAPA): the triggers from NCRs, the five-why, the actions, closing.

A CAPA goes after the root cause of one or more NCRs of an item:
  * containment (what was done at once), five-why (Why 1 … Why 5) and the root cause;
  * actions: Correction / Corrective Action / Preventive Action, each with who, due date and done on;
  * status Open → In Progress → Closed, or Cancelled (with a reason). Closing needs the five-why complete (the first
    "CAPA: Whys Required" whys and the root cause), at least one Corrective Action and every action done. A Closed or
    Cancelled CAPA cannot be changed; a Quality Manager reopens a Closed one (In Progress).
  * C3b-B3 - effectiveness verification: with "CAPA: Verification After (Days)" above 0, a CAPA whose actions are
    complete is not closed at once. Setting it to Closed (or Awaiting Verification) checks the closing rules, puts it
    "Awaiting Verification" and schedules the effectiveness check on (today + those days); the CAPA owner gets a ToDo
    for that day (QA-CAPA-VERIFY). On or after that day a Quality Manager presses "Verify Effectiveness":
    Effective -> Closed (refused while a Major / Critical NCR was raised on the item since the actions were completed);
    Not Effective -> back to In Progress, counted, to add actions and close again (a new check is scheduled).
    "Not Effective" may be recorded at any time. 0 days = closing closes at once (no check).

Triggers (on every save of an NCR that is not cancelled and has no CAPA yet; never stops the NCR):
  * Critical NCR → a CAPA (trigger "Critical NCR");
  * Major NCR when the item has at least "CAPA: Repeat Major Count" Major or Critical NCRs without a CAPA raised within
    "CAPA: Repeat Window (Days)" → one CAPA for all of them (trigger "Repeat Major");
  * an NCR of an item that already has an open CAPA (not Closed / Cancelled) joins that CAPA instead.
The NCR shows its CAPA; the CAPA lists its NCRs. A CAPA raised by the system gives its owner (default: the Quality
Notification Owner) a ToDo (QA-CAPA-OPEN), closed when the CAPA is closed or cancelled.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, getdate, now_datetime, today

from pepl_os.common import alerts, params

CAPA = "PEPL CAPA"
NCR = "PEPL NCR"
OWNER_FIELD = "custom_quality_notification_owner"
NCR_LINK = "capa"

OPEN, IN_PROGRESS, CLOSED, CANCELLED = "Open", "In Progress", "Closed", "Cancelled"
AWAITING = "Awaiting Verification"
DONE_STATES = (CLOSED, CANCELLED)
EFFECTIVE, NOT_EFFECTIVE = "Effective", "Not Effective"
CRITICAL_TRIGGER, REPEAT_TRIGGER, MANUAL_TRIGGER = "Critical NCR", "Repeat Major", "Manual"
CORRECTION, CORRECTIVE, PREVENTIVE = "Correction", "Corrective Action", "Preventive Action"
OPEN_RULE = "QA-CAPA-OPEN"
VERIFY_RULE = "QA-CAPA-VERIFY"
REOPEN_ROLES = ("Quality Manager", "System Manager")
WHY_FIELDS = ("why_1", "why_2", "why_3", "why_4", "why_5")
LOCKED_FIELDS = ("item", "problem_statement", "containment", *WHY_FIELDS, "root_cause")

WINDOW_FIELD = "custom_capa_repeat_window_days"
COUNT_FIELD = "custom_capa_repeat_count"
WHYS_FIELD = "custom_capa_whys_required"
TARGET_FIELD = "custom_capa_target_days"
VERIFY_FIELD = "custom_capa_verification_days"
VERIFY_DEFAULT = 90
RANGES = {
	WINDOW_FIELD: (1, 730),
	COUNT_FIELD: (2, 10),
	WHYS_FIELD: (1, 5),
	TARGET_FIELD: (1, 365),
	VERIFY_FIELD: (0, 365),
}
LABELS = {
	WINDOW_FIELD: "CAPA: Repeat Window (Days)",
	COUNT_FIELD: "CAPA: Repeat Major Count",
	WHYS_FIELD: "CAPA: Whys Required",
	TARGET_FIELD: "CAPA: Target Days",
	VERIFY_FIELD: "CAPA: Verification After (Days)",
}
DEFAULTS = {WINDOW_FIELD: 90, COUNT_FIELD: 2, WHYS_FIELD: 5, TARGET_FIELD: 30}


# Settings ---------------------------------------------------------------------------------------------------


def setting(field):
	return params.get_int(field, DEFAULTS[field]) or DEFAULTS[field]


def verification_days():
	"""Days from actions complete to the effectiveness check; 0 = no check (closing closes at once)."""
	value = params.get(VERIFY_FIELD, VERIFY_DEFAULT)
	if value in (None, ""):
		return VERIFY_DEFAULT
	return min(max(cint(value), 0), 365)


def validate_params(doc):
	errors = []
	for field, (low, high) in RANGES.items():
		value = doc.get(field)
		if value not in (None, "") and not low <= cint(value) <= high:
			errors.append(_("{0} must be between {1} and {2}.").format(_(LABELS[field]), low, high))
	return errors


# Five-why and completeness -------------------------------------------------------------------------------------------


def five_why_state(doc):
	"""(whys filled of the required ones, whys required, root cause given, complete)."""
	required = setting(WHYS_FIELD)
	filled = sum(1 for field in WHY_FIELDS[:required] if (doc.get(field) or "").strip())
	has_root = bool((doc.get("root_cause") or "").strip())
	return filled, required, has_root, filled == required and has_root


def closing_gaps(doc):
	"""What still stops the CAPA from closing (plain sentences)."""
	gaps = []
	filled, required, has_root, _complete = five_why_state(doc)
	if filled < required:
		gaps.append(_("five-why: {0} of {1} whys answered").format(filled, required))
	if not has_root:
		gaps.append(_("no root cause"))
	actions = doc.get("actions") or []
	if not any(row.action_type == CORRECTIVE for row in actions):
		gaps.append(_("no Corrective Action"))
	open_actions = [row for row in actions if not row.done_on]
	if open_actions:
		gaps.append(_("{0} action(s) not done").format(len(open_actions)))
	return gaps


# PEPL CAPA -----------------------------------------------------------------------------------------------------


def validate_capa(doc):
	before = None if doc.is_new() else doc.get_doc_before_save()
	old_status = before.status if before else None
	if before and old_status in (*DONE_STATES, AWAITING) and doc.status == old_status:
		changed = [f for f in LOCKED_FIELDS if cstr(before.get(f)) != cstr(doc.get(f))]
		if changed or len(doc.get("actions") or []) != len(before.get("actions") or []):
			frappe.throw(
				_(
					"A {0} CAPA cannot be changed. A Quality Manager can reopen a closed CAPA (status In Progress)."
				).format(_(old_status))
			)
	if before and old_status == CLOSED and doc.status != CLOSED:
		if doc.status != IN_PROGRESS or not set(REOPEN_ROLES) & set(frappe.get_roles()):
			frappe.throw(_("Only a Quality Manager can reopen a closed CAPA, by setting it to In Progress."))
		doc.closed_on = None
		doc.closed_by = None
	if before and old_status == CANCELLED and doc.status != CANCELLED:
		frappe.throw(_("A cancelled CAPA stays cancelled. Raise a new one."))
	if old_status == AWAITING and doc.status not in (AWAITING, CANCELLED) and not doc.flags.pepl_verification:
		frappe.throw(
			_(
				"This CAPA is awaiting its effectiveness check: a Quality Manager records the result with "
				"'Verify Effectiveness' (Effective closes it, Not Effective sends it back to In Progress)."
			)
		)
	for row in doc.get("actions") or []:
		if row.done_on and getdate(row.done_on) > getdate(today()):
			frappe.throw(_("Action {0}: Done On cannot be in the future.").format(row.idx))
	if not doc.capa_owner:
		doc.capa_owner = params.get(OWNER_FIELD) or frappe.session.user
	if not doc.target_date:
		doc.target_date = add_days(doc.raised_on or today(), setting(TARGET_FIELD))
	filled, required, _has_root, complete = five_why_state(doc)
	doc.five_why_status = (
		_("Complete")
		if complete
		else _("{0} of {1} whys, root cause {2}").format(
			filled, required, _("given") if _has_root else _("missing")
		)
	)
	if doc.status == OPEN and (filled or any(doc.get("actions") or [])):
		doc.status = IN_PROGRESS
	if doc.status in (CLOSED, AWAITING) and old_status not in (CLOSED, AWAITING):
		gaps = closing_gaps(doc)
		if gaps:
			frappe.throw(_("The CAPA cannot be closed yet: {0}.").format("; ".join(gaps)))
		days = verification_days()
		if days or doc.status == AWAITING:
			doc.status = AWAITING
			doc.actions_completed_on = now_datetime()
			doc.verification_due_on = add_days(today(), days)
			doc.verification_result = None
			frappe.msgprint(
				_(
					"Actions complete. The effectiveness check is due on {0}; the CAPA closes when a Quality "
					"Manager verifies it as effective."
				).format(frappe.utils.formatdate(doc.verification_due_on)),
				alert=True,
			)
		else:
			doc.actions_completed_on = now_datetime()
	if doc.status == CLOSED and old_status != CLOSED:
		doc.closed_on = now_datetime()
		doc.closed_by = frappe.session.user
	if doc.status == CANCELLED and old_status != CANCELLED and len((doc.cancel_reason or "").strip()) < 10:
		frappe.throw(_("Give the reason for cancelling the CAPA (at least 10 characters)."))


def on_update_capa(doc):
	"""Every NCR listed points back at the CAPA; the owner's ToDo follows the status."""
	for row in doc.get("ncrs") or []:
		if row.ncr and frappe.db.get_value(NCR, row.ncr, NCR_LINK) != doc.name:
			frappe.db.set_value(NCR, row.ncr, NCR_LINK, doc.name, update_modified=False)
	if doc.status != AWAITING:
		alerts.close_one(VERIFY_RULE, CAPA, doc.name)
	if doc.status in (*DONE_STATES, AWAITING):
		alerts.close_one(OPEN_RULE, CAPA, doc.name)
	if doc.status == AWAITING:
		alerts.raise_todo(
			VERIFY_RULE,
			CAPA,
			doc.name,
			_("Verify the effectiveness of CAPA {0} on {1} (due {2}): did the problem come back?").format(
				doc.name, doc.item, frappe.utils.formatdate(doc.verification_due_on)
			),
			allocated_to=doc.capa_owner,
			priority="Medium",
			due_date=doc.verification_due_on,
		)
	elif doc.status not in DONE_STATES and cint(doc.raised_by_system):
		alerts.raise_todo(
			OPEN_RULE,
			CAPA,
			doc.name,
			_("CAPA ({0}) on {1}: {2}").format(_(doc.trigger), doc.item, (doc.problem_statement or "")[:200]),
			allocated_to=doc.capa_owner,
			priority="High",
			due_date=doc.target_date,
		)


# Triggers from the NCR -----------------------------------------------------------------------------------------------


def open_capa_for(item):
	return frappe.db.get_value(
		CAPA, {"item": item, "status": ["not in", DONE_STATES]}, "name", order_by="creation desc"
	)


def _ncr_row(ncr_doc):
	return {
		"ncr": ncr_doc.name,
		"severity": ncr_doc.severity,
		"raised_on": ncr_doc.raised_on,
		"defect": (ncr_doc.defect_description or "")[:140],
	}


def _attach(capa_name, ncr_docs):
	capa = frappe.get_doc(CAPA, capa_name)
	listed = {row.ncr for row in capa.get("ncrs") or []}
	for ncr_doc in ncr_docs:
		if ncr_doc.name not in listed:
			capa.append("ncrs", _ncr_row(ncr_doc))
	capa.flags.ignore_permissions = True
	capa.flags.ignore_links = True
	capa.save()
	return capa.name


def _raise(trigger, ncr_docs):
	first = ncr_docs[-1]
	names = ", ".join(n.name for n in ncr_docs)
	statement = (
		_("Critical NCR {0} on {1}: {2}").format(
			first.name, first.item, (first.defect_description or "")[:300]
		)
		if trigger == CRITICAL_TRIGGER
		else _("{0} Major / Critical NCRs on {1} within {2} days: {3}.").format(
			len(ncr_docs), first.item, setting(WINDOW_FIELD), names
		)
	)
	capa = frappe.get_doc(
		{
			"doctype": CAPA,
			"trigger": trigger,
			"status": OPEN,
			"item": first.item,
			"raised_on": today(),
			"raised_by_system": 1,
			"problem_statement": statement,
			"capa_owner": params.get(OWNER_FIELD) or None,
			"ncrs": [_ncr_row(n) for n in ncr_docs],
		}
	)
	capa.flags.ignore_permissions = True
	capa.flags.ignore_links = True
	capa.insert()
	return capa.name


def repeat_majors(ncr_doc):
	"""This NCR and the other Major / Critical NCRs of the item without a CAPA, raised within the window."""
	since = add_days(ncr_doc.raised_on or today(), -setting(WINDOW_FIELD))
	names = frappe.get_all(
		NCR,
		filters={
			"item": ncr_doc.item,
			"severity": ["in", ("Major", "Critical")],
			"status": ["!=", "Cancelled"],
			"raised_on": [">=", since],
			NCR_LINK: ["is", "not set"],
			"name": ["!=", ncr_doc.name],
		},
		pluck="name",
		order_by="raised_on asc, creation asc",
	)
	return [frappe.get_doc(NCR, name) for name in names] + [ncr_doc]


def check_ncr(ncr_doc):
	"""Raise a CAPA for this NCR, or attach it to the item's open CAPA. Returns the CAPA name or None."""
	if ncr_doc.status == "Cancelled" or ncr_doc.get(NCR_LINK) or not ncr_doc.item:
		return None
	if ncr_doc.severity not in ("Major", "Critical"):
		return None
	current = open_capa_for(ncr_doc.item)
	if current:
		return _attach(current, [ncr_doc])
	if ncr_doc.severity == "Critical":
		return _raise(CRITICAL_TRIGGER, [ncr_doc])
	group = repeat_majors(ncr_doc)
	if len(group) >= setting(COUNT_FIELD):
		return _raise(REPEAT_TRIGGER, group)
	return None


def on_ncr_update(ncr_doc):
	"""Called from the NCR's on_update. Never stops the NCR."""
	frappe.db.savepoint("pepl_capa")
	try:
		name = check_ncr(ncr_doc)
	except Exception:
		frappe.db.rollback(save_point="pepl_capa")
		frappe.log_error(title=f"PEPL: CAPA not raised for {ncr_doc.name}")
		return None
	if name:
		ncr_doc.set(NCR_LINK, name)
	return name


@frappe.whitelist()
def get_capa_state(capa):
	"""For the form: five-why progress and what still stops closing."""
	doc = frappe.get_doc(CAPA, capa)
	doc.check_permission("read")
	filled, required, has_root, complete = five_why_state(doc)
	return {
		"whys_filled": filled,
		"whys_required": required,
		"root_cause": has_root,
		"five_why_complete": complete,
		"closing_gaps": closing_gaps(doc),
	}


# Effectiveness verification (C3b-B3) ---------------------------------------------------------------------------


def ncrs_since_completion(doc):
	"""Major / Critical NCRs (not cancelled) on the CAPA's item entered after its actions were complete."""
	if not doc.get("actions_completed_on") or not doc.item:
		return []
	return frappe.get_all(
		NCR,
		filters={
			"item": doc.item,
			"severity": ["in", ("Major", "Critical")],
			"status": ["!=", "Cancelled"],
			"creation": [">=", doc.actions_completed_on],
		},
		pluck="name",
		order_by="creation asc",
	)


def verification_overdue(doc, as_of=None):
	return (
		doc.status == AWAITING
		and doc.get("verification_due_on")
		and getdate(doc.verification_due_on) < getdate(as_of or today())
	)


@frappe.whitelist()
def verify_capa(capa, result, remarks):
	"""Record the effectiveness check. Effective (on or after the due day) closes the CAPA; Not Effective sends it
	back to In Progress. Quality Manager only."""
	frappe.only_for(REOPEN_ROLES)
	doc = frappe.get_doc(CAPA, capa)
	if doc.status != AWAITING:
		frappe.throw(_("CAPA {0} is {1}, not awaiting verification.").format(doc.name, _(doc.status)))
	if result not in (EFFECTIVE, NOT_EFFECTIVE):
		frappe.throw(_("The result is Effective or Not Effective."))
	remarks = (remarks or "").strip()
	if len(remarks) < 10:
		frappe.throw(
			_("Say what was checked (at least 10 characters), e.g. lots inspected since and their result.")
		)
	if result == EFFECTIVE:
		if getdate(today()) < getdate(doc.verification_due_on):
			frappe.throw(
				_(
					"The effectiveness check is due on {0}; the CAPA can be verified as effective from then."
				).format(frappe.utils.formatdate(doc.verification_due_on))
			)
		since = ncrs_since_completion(doc)
		if since:
			frappe.throw(
				_(
					"Major / Critical NCR(s) {0} were raised on {1} since the actions were completed: the CAPA was "
					"not effective. Record Not Effective and add actions."
				).format(", ".join(since), doc.item)
			)
	line = _("{0}: {1} - {2} ({3})").format(
		frappe.utils.formatdate(today()), _(result), remarks, frappe.session.user
	)
	doc.verification_remarks = ((doc.verification_remarks or "") + "\n" + line).strip()
	doc.verification_result = result
	doc.verified_on = today()
	doc.verified_by = frappe.session.user
	if result == EFFECTIVE:
		doc.status = CLOSED
	else:
		doc.status = IN_PROGRESS
		doc.verification_count = cint(doc.verification_count) + 1
		doc.actions_completed_on = None
		doc.verification_due_on = None
	doc.flags.pepl_verification = True
	doc.flags.ignore_permissions = True
	doc.save()
	return {"status": doc.status, "result": result}
