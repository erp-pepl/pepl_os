"""The standard PEPL flag pattern: one open ToDo per rule per record.

Thin wrappers around the Cycle 1 engine in pepl_sales.operational_notifications,
so every cycle raises and closes alerts the same way.

Rule codes use the Cycle 1 style: upper case with hyphens, prefixed by module,
e.g. "PUR-CHASE", "SUP-DOC-EXPIRY", "STO-REORDER", "QA-CAL-DUE".
"""

from pepl_sales.operational_notifications import (
	close_resolved_rule_todos,
	get_notification_owner,
	upsert_operational_todo,
)

from pepl_os.common import params


def alerts_enabled():
	"""Honour the Cycle 1 master switch for operational ToDos."""
	return params.is_enabled("enable_operational_todos", 0)


def raise_todo(
	rule_code,
	reference_doctype,
	reference_name,
	description,
	owner_field=None,
	allocated_to=None,
	priority="Medium",
	due_date=None,
):
	"""Create or update the one open ToDo for this rule and record.

	Pass either `allocated_to` (a User) or `owner_field` (a System Parameter
	holding a User, e.g. "custom_purchase_notification_owner"). The owner
	falls back to Notification Fallback Owner, exactly as in Cycle 1.
	"""
	if not alerts_enabled():
		return {"action": "disabled", "name": None}

	if not allocated_to:
		allocated_to = get_notification_owner(owner_field or "notification_fallback_owner")

	return upsert_operational_todo(
		rule_code=rule_code,
		reference_type=reference_doctype,
		reference_name=reference_name,
		allocated_to=allocated_to,
		description=description,
		priority=priority,
		due_date=due_date,
	)


def close_resolved(rule_code, reference_doctype, active_reference_names):
	"""Close open ToDos of this rule whose record is no longer an exception."""
	return close_resolved_rule_todos(
		rule_code=rule_code,
		reference_type=reference_doctype,
		active_reference_names=active_reference_names,
	)
