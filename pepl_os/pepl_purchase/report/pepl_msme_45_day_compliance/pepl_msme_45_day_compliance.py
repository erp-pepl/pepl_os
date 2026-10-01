# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-17 - MSME 45-Day Compliance: every MSME bill, when it was due and when it was paid."""

from frappe import _

from pepl_os.pepl_purchase.payments import msme_compliance


def execute(filters=None):
	columns = [
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
		{"fieldname": "basis_date", "label": _("Clock Starts"), "fieldtype": "Date", "width": 100},
		{"fieldname": "due_date", "label": _("Pay By"), "fieldtype": "Date", "width": 95},
		{
			"fieldname": "payment_entry",
			"label": _("Cleared By"),
			"fieldtype": "Link",
			"options": "Payment Entry",
			"width": 140,
		},
		{"fieldname": "cleared_on", "label": _("Paid On"), "fieldtype": "Date", "width": 95},
		{"fieldname": "days_taken", "label": _("Days Taken"), "fieldtype": "Int", "width": 90},
		{"fieldname": "grand_total", "label": _("Bill Amount"), "fieldtype": "Currency", "width": 115},
		{"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 115},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
	]
	return columns, msme_compliance(filters)
