# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-17 - Outstanding Vendor Bills by supplier and days overdue. Totals equal Accounts Payable."""

from frappe import _

from pepl_os.pepl_purchase.payments import outstanding_vendor_bills


def execute(filters=None):
	money = {"fieldtype": "Currency", "width": 115}
	columns = [
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 170,
		},
		{"fieldname": "supplier_name", "label": _("Supplier Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "bills", "label": _("Bills"), "fieldtype": "Int", "width": 60},
		{"fieldname": "not_due", "label": _("Not Due"), **money},
		{"fieldname": "age_1_30", "label": _("1-30 Days Overdue"), **money},
		{"fieldname": "age_31_60", "label": _("31-60"), **money},
		{"fieldname": "age_61_90", "label": _("61-90"), **money},
		{"fieldname": "age_91_plus", "label": _("Over 90"), **money},
		{"fieldname": "advances", "label": _("Unallocated Advances"), **money},
		{"fieldname": "total", "label": _("Total Outstanding"), "fieldtype": "Currency", "width": 135},
	]
	return columns, outstanding_vendor_bills(filters)
