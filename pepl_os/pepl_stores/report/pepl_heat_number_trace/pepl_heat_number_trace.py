# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-15 - Heat Number Trace: everything that happened to one heat number."""

from frappe import _

from pepl_os.pepl_stores.trace import heat_trace


def execute(filters=None):
	columns = [
		{"fieldname": "stage", "label": _("Stage"), "fieldtype": "Data", "width": 110},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "voucher_type", "label": _("Document Type"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "voucher_no",
			"label": _("Document"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 160,
		},
		{"fieldname": "purpose", "label": _("Purpose"), "fieldtype": "Data", "width": 170},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 150},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 80},
		{
			"fieldname": "warehouse",
			"label": _("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 150,
		},
		{"fieldname": "batch_no", "label": _("Batch"), "fieldtype": "Link", "options": "Batch", "width": 120},
		{"fieldname": "party", "label": _("Supplier / Customer"), "fieldtype": "Data", "width": 160},
		{
			"fieldname": "work_order",
			"label": _("Work Order"),
			"fieldtype": "Link",
			"options": "Work Order",
			"width": 140,
		},
	]
	heat = (filters or {}).get("heat_number")
	return columns, heat_trace(heat) if heat else []
