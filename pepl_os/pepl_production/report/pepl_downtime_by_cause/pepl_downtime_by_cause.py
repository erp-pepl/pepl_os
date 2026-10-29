# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-CC - Downtime by Cause: stopped minutes per downtime category over the last days (behind the Command Centre
card "Top Downtime Cause (7 days)")."""

from frappe import _

from pepl_os.pepl_production import command_centre


def execute(filters=None):
	filters = filters or {}
	columns = [
		{
			"fieldname": "downtime_category",
			"label": _("Downtime Category"),
			"fieldtype": "Link",
			"options": "PEPL Downtime Category",
			"width": 220,
		},
		{"fieldname": "stop_type", "label": _("Stop Type"), "fieldtype": "Data", "width": 130},
		{"fieldname": "is_breakdown", "label": _("Machine Breakdown"), "fieldtype": "Check", "width": 90},
		{"fieldname": "minutes", "label": _("Minutes"), "fieldtype": "Int", "width": 100},
		{"fieldname": "share", "label": _("Share %"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "stops", "label": _("Stops"), "fieldtype": "Int", "width": 80},
		{"fieldname": "machines", "label": _("Machines"), "fieldtype": "Int", "width": 90},
	]
	return columns, command_centre.downtime_by_cause(filters.get("days") or command_centre.DAYS)
