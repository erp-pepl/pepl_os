# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-20 - Cycle Count Variance Log: variances by store, reason and month."""

from frappe import _

from pepl_os.pepl_stores.cycle_count import variance_log


def execute(filters=None):
	columns = [
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 85},
		{
			"fieldname": "warehouse",
			"label": _("Store"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 170,
		},
		{"fieldname": "reason", "label": _("Reason"), "fieldtype": "Data", "width": 150},
		{"fieldname": "line_count", "label": _("Lines"), "fieldtype": "Int", "width": 70},
		{"fieldname": "variance_qty", "label": _("Variance Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "variance_value", "label": _("Variance Value"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "items", "label": _("Items"), "fieldtype": "Data", "width": 260},
	]
	return columns, variance_log(filters)
