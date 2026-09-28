"""A5 - Audit log retention.

Frappe's Log Settings clears some logs automatically (login history in
Activity Log after 90 days by default). This keeps every audit log that
Frappe would clear for at least "Audit Log Retention (Days)". It only ever
raises a retention period, never lowers one, and never adds clearing for a
log Frappe keeps forever (Version, Access Log, View Log, Deleted Document
unless PEPL registers them by hand).
"""

import frappe
from frappe.utils import cint

from pepl_os.common import params

AUDIT_LOGS = ("Activity Log", "Access Log", "Deleted Document", "View Log")


def apply_log_retention():
	days = params.get_int("custom_audit_log_retention_days", 0)
	if days <= 0:
		return {}

	settings = frappe.get_doc("Log Settings")
	defaults = frappe.get_hooks("default_log_clearing_doctypes") or {}
	present = {row.ref_doctype: row for row in settings.logs_to_clear}
	changed = {}

	for doctype in AUDIT_LOGS:
		row = present.get(doctype)
		if row:
			if cint(row.days) < days:
				changed[doctype] = (cint(row.days), days)
				row.days = days
		elif doctype in defaults:
			# Frappe would add it at its default on the next clean-up run.
			settings.append("logs_to_clear", {"ref_doctype": doctype, "days": days})
			changed[doctype] = (None, days)

	if changed:
		settings.save(ignore_permissions=True)
	return changed


def on_parameters_update(doc, method=None):
	"""PEPL System Parameters on_update: apply a changed retention at once."""
	apply_log_retention()
