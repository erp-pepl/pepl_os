# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-B4 - Bottleneck: how long work waits in front of each machine group between Job Order operations, and what
is waiting now. See pepl_production/bottleneck.py for every rule."""

import frappe
from frappe import _

from pepl_os.pepl_production import bottleneck


def _hours(fieldname, label, width=110):
	return {"fieldname": fieldname, "label": label, "fieldtype": "Float", "precision": 2, "width": width}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	ops = bottleneck.operation_rows(filters)
	groups = bottleneck.group_rows(ops)
	message = frappe.utils.escape_html(bottleneck.summary(groups))
	if filters.get("show") == "Operations":
		columns = [
			{
				"fieldname": "job_order",
				"label": _("Job Order"),
				"fieldtype": "Link",
				"options": "Work Order",
				"width": 150,
			},
			{
				"fieldname": "item_code",
				"label": _("Item"),
				"fieldtype": "Link",
				"options": "Item",
				"width": 130,
			},
			{"fieldname": "previous", "label": _("After Operation"), "fieldtype": "Data", "width": 140},
			{"fieldname": "operation", "label": _("Operation"), "fieldtype": "Data", "width": 140},
			{"fieldname": "group", "label": _("Machine Group"), "fieldtype": "Data", "width": 140},
			{
				"fieldname": "previous_finished",
				"label": _("Previous Finished"),
				"fieldtype": "Datetime",
				"width": 150,
			},
			{"fieldname": "started", "label": _("Started"), "fieldtype": "Datetime", "width": 150},
			_hours("hours", _("Wait (h)"), 90),
			{"fieldname": "state_text", "label": _("State"), "fieldtype": "Data", "width": 130},
		]
		words = {"waited": _("Waited"), "overlapped": _("Overlapped"), "waiting": _("Waiting now")}
		for row in ops:
			row["state_text"] = words.get(row["state"], "")
		return columns, ops, message
	columns = [
		{"fieldname": "rank", "label": _("Rank"), "fieldtype": "Int", "width": 60},
		{
			"fieldname": "workstation_type",
			"label": _("Machine Group"),
			"fieldtype": "Link",
			"options": "Workstation Type",
			"width": 170,
		},
		{"fieldname": "waits", "label": _("Waits"), "fieldtype": "Int", "width": 70},
		_hours("average_hours", _("Average Wait (h)"), 120),
		_hours("longest_hours", _("Longest Wait (h)"), 120),
		_hours("total_hours", _("Total Wait (h)")),
		{"fieldname": "overlapped", "label": _("Overlapped"), "fieldtype": "Int", "width": 95},
		{"fieldname": "waiting_now", "label": _("Waiting Now"), "fieldtype": "Int", "width": 100},
		_hours("oldest_waiting_hours", _("Oldest Waiting (h)"), 130),
		_hours("run_hours", _("Run Hours")),
	]
	return columns, groups, message
