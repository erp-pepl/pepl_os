# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-16 - CSM Balance by Order: the customer's material held against each Sales Order."""

from frappe import _

from pepl_os.pepl_stores.csm import csm_balance


def execute(filters=None):
	columns = [
		{
			"fieldname": "sales_order",
			"label": _("Sales Order"),
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 150,
		},
		{
			"fieldname": "customer",
			"label": _("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": 150,
		},
		{
			"fieldname": "item_code",
			"label": _("CSM Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 60},
		{"fieldname": "received", "label": _("Received"), "fieldtype": "Float", "width": 95},
		{"fieldname": "issued", "label": _("Issued"), "fieldtype": "Float", "width": 90},
		{"fieldname": "scrapped", "label": _("Scrapped"), "fieldtype": "Float", "width": 90},
		{"fieldname": "returned", "label": _("Returned"), "fieldtype": "Float", "width": 90},
		{"fieldname": "balance", "label": _("Balance"), "fieldtype": "Float", "width": 90},
		{"fieldname": "scrap_on_hand", "label": _("Scrap on Hand"), "fieldtype": "Float", "width": 105},
		{"fieldname": "balance_value", "label": _("Value"), "fieldtype": "Currency", "width": 90},
		{"fieldname": "scrap_disposition", "label": _("Scrap Option"), "fieldtype": "Data", "width": 130},
	]
	return columns, csm_balance(filters)
