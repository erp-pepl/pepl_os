# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-17 - Vendor Payment Priority: MSME 45-day first, then critical vendors overdue, then age."""

from frappe import _

from pepl_os.pepl_purchase.payments import payment_priority


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"fieldname": "rank", "label": _("Rank"), "fieldtype": "Int", "width": 60},
		{
			"fieldname": "purchase_invoice",
			"label": _("Purchase Invoice"),
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 150,
		},
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 160,
		},
		{"fieldname": "bill_no", "label": _("Bill No"), "fieldtype": "Data", "width": 100},
		{"fieldname": "bill_date", "label": _("Bill Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "rule", "label": _("Rule"), "fieldtype": "Data", "width": 120},
		{"fieldname": "pay_by", "label": _("Pay By"), "fieldtype": "Date", "width": 95},
		{"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int", "width": 85},
		{"fieldname": "flag", "label": _("Status"), "fieldtype": "Data", "width": 95},
		{"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "running_total", "label": _("Running Total"), "fieldtype": "Currency", "width": 125},
		{"fieldname": "action", "label": _("Payment"), "fieldtype": "Data", "width": 95},
	]
	rows = payment_priority(filters.get("as_of"), filters.get("company"), filters.get("supplier"))
	for row in rows:
		row.action = row.purchase_invoice
	return columns, rows
