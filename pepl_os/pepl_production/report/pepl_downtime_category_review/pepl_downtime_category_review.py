# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-C1 - Downtime Category Review: how often each category is used, unused ones and look-alikes to merge."""

from frappe import _

from pepl_os.pepl_production import config


def execute(filters=None):
	filters = filters or {}
	columns = [
		{
			"fieldname": "category",
			"label": _("Downtime Category"),
			"fieldtype": "Link",
			"options": "PEPL Downtime Category",
			"width": 200,
		},
		{"fieldname": "stop_type", "label": _("Stop Type"), "fieldtype": "Data", "width": 130},
		{"fieldname": "is_breakdown", "label": _("Machine Breakdown"), "fieldtype": "Check", "width": 90},
		{"fieldname": "is_active", "label": _("Active"), "fieldtype": "Check", "width": 70},
		{"fieldname": "recent", "label": _("Used (look-back days)"), "fieldtype": "Int", "width": 120},
		{"fieldname": "total", "label": _("Used in all"), "fieldtype": "Int", "width": 90},
		{"fieldname": "last_used", "label": _("Last Used"), "fieldtype": "Date", "width": 100},
		{"fieldname": "notes", "label": _("To look at"), "fieldtype": "Data", "width": 420},
	]
	return columns, config.review_rows(filters.get("days") or config.REVIEW_DAYS)
