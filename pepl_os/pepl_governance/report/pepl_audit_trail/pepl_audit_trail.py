# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""PEPL Audit Trail: who changed, printed, exported, deleted, viewed or overrode what."""

from frappe import _

from pepl_os.pepl_governance.audit_trail import ROW_LIMIT_PER_SOURCE, get_events


def execute(filters=None):
	rows, truncated = get_events(filters or {})
	message = None
	if truncated:
		message = _(
			"Showing the latest {0} rows for: {1}. Narrow the dates or add a user to see everything."
		).format(ROW_LIMIT_PER_SOURCE, ", ".join(truncated))
	return get_columns(), rows, message


def get_columns():
	return [
		{"fieldname": "time", "label": _("Time"), "fieldtype": "Datetime", "width": 170},
		{"fieldname": "user", "label": _("User"), "fieldtype": "Link", "options": "User", "width": 200},
		{"fieldname": "event_type", "label": _("Event"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "reference_doctype",
			"label": _("Record Type"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 150,
		},
		{
			"fieldname": "reference_name",
			"label": _("Record"),
			"fieldtype": "Dynamic Link",
			"options": "reference_doctype",
			"width": 170,
		},
		{"fieldname": "detail", "label": _("What Happened"), "fieldtype": "Data", "width": 480},
	]
