# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-X8 - Job-Work Reconciliation: per job worker and item, sent / received / returned / balance and age."""

from frappe import _
from frappe.utils import flt

from pepl_os.pepl_production import job_work


def execute(filters=None):
	filters = filters or {}
	rows = job_work.reconcile(filters.get("company"), filters.get("supplier"), filters.get("as_on"))
	if filters.get("outstanding_only"):
		rows = [r for r in rows if flt(r.balance) > 0]
	columns = [
		{
			"fieldname": "job_worker",
			"label": _("Job Worker"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 170,
		},
		{
			"fieldname": "warehouse",
			"label": _("Job Worker's Store"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 170,
		},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 160},
		{"fieldname": "sent", "label": _("Sent"), "fieldtype": "Float", "width": 90},
		{"fieldname": "received", "label": _("Received (processed)"), "fieldtype": "Float", "width": 120},
		{"fieldname": "returned", "label": _("Returned (unprocessed)"), "fieldtype": "Float", "width": 120},
		{"fieldname": "adjusted", "label": _("Adjusted"), "fieldtype": "Float", "width": 90},
		{"fieldname": "balance", "label": _("Balance at Job Worker"), "fieldtype": "Float", "width": 120},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Currency", "width": 110},
		{
			"fieldname": "oldest_outside",
			"label": _("Oldest Outside Since"),
			"fieldtype": "Date",
			"width": 110,
		},
		{"fieldname": "days_outside", "label": _("Days Outside"), "fieldtype": "Int", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
	]
	outside = [r for r in rows if flt(r.balance) > 0]
	late = [r for r in outside if r.status != job_work.OUTSIDE]
	summary = [
		{"value": len(outside), "label": _("Lines outside"), "datatype": "Int", "indicator": "Blue"},
		{
			"value": sum(flt(r.value) for r in outside),
			"label": _("Value outside"),
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"value": len(late),
			"label": _("Overdue / GST"),
			"datatype": "Int",
			"indicator": "Red" if late else "Green",
		},
	]
	return columns, rows, None, None, summary
