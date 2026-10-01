# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-13 - Daily chase list: every Overdue, Due Today and Due Soon PO line, by supplier."""

from frappe import _

from pepl_os.pepl_purchase.chase import chase_list


def execute(filters=None):
	columns = [
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 170,
		},
		{"fieldname": "vendor_criticality", "label": _("Criticality"), "fieldtype": "Data", "width": 90},
		{"fieldname": "chase", "label": _("Chase"), "fieldtype": "Data", "width": 80},
		{"fieldname": "phone", "label": _("Phone"), "fieldtype": "Data", "width": 110},
		{"fieldname": "email", "label": _("E-mail"), "fieldtype": "Data", "width": 170},
		{
			"fieldname": "purchase_order",
			"label": _("Purchase Order"),
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 150,
		},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 150},
		{"fieldname": "pending_qty", "label": _("Pending Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "promised_date", "label": _("Promised"), "fieldtype": "Date", "width": 95},
		{"fieldname": "revised_date", "label": _("Vendor Revised"), "fieldtype": "Date", "width": 105},
		{"fieldname": "days_overdue", "label": _("Days Overdue"), "fieldtype": "Int", "width": 95},
		{"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "last_chased_on", "label": _("Last Chased"), "fieldtype": "Datetime", "width": 140},
		{
			"fieldname": "tracker",
			"label": _("Tracker"),
			"fieldtype": "Link",
			"options": "PEPL Purchase Tracker",
			"width": 140,
		},
	]
	rows = chase_list(filters)
	seen = set()
	for r in rows:
		r["chase"] = r.supplier if r.supplier not in seen else ""  # one Chase button per supplier
		seen.add(r.supplier)
	return columns, rows
