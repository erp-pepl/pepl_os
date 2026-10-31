# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-B5 - LD Exposure: late days x contractual LD rate on every open Sales Order, today and in the look-ahead
days. See pepl_production/ld_exposure.py and ld.py for every rule."""

import frappe
from frappe import _

from pepl_os.pepl_production import ld_exposure


def _money(fieldname, label, width=120):
	return {"fieldname": fieldname, "label": label, "fieldtype": "Currency", "width": width}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	orders, lines = ld_exposure.order_rows(filters)
	days = ld_exposure.look_ahead_days()
	message = frappe.utils.escape_html(ld_exposure.summary(orders))
	ahead_label = _("LD in {0} Days").format(days)
	if filters.get("show") == "Lines":
		columns = [
			{
				"fieldname": "sales_order",
				"label": _("Sales Order"),
				"fieldtype": "Link",
				"options": "Sales Order",
				"width": 140,
			},
			{"fieldname": "customer_name", "label": _("Customer"), "fieldtype": "Data", "width": 160},
			{
				"fieldname": "item_code",
				"label": _("Item"),
				"fieldtype": "Link",
				"options": "Item",
				"width": 140,
			},
			{"fieldname": "due", "label": _("Due"), "fieldtype": "Date", "width": 100},
			{"fieldname": "qty", "label": _("Ordered"), "fieldtype": "Float", "width": 85},
			{"fieldname": "delivered", "label": _("Delivered"), "fieldtype": "Float", "width": 85},
			{"fieldname": "pending", "label": _("Pending"), "fieldtype": "Float", "width": 85},
			{"fieldname": "late_qty", "label": _("Late Qty"), "fieldtype": "Float", "width": 85},
			{"fieldname": "days_late", "label": _("Days Late"), "fieldtype": "Int", "width": 85},
			_money("ld_now", _("LD so far")),
			_money("ld_ahead", ahead_label),
			_money("uncapped", _("Before Cap")),
		]
		return columns, lines, message
	columns = [
		{
			"fieldname": "sales_order",
			"label": _("Sales Order"),
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 140,
		},
		{"fieldname": "customer_name", "label": _("Customer"), "fieldtype": "Data", "width": 170},
		{"fieldname": "sector", "label": _("Sector"), "fieldtype": "Data", "width": 90},
		_money("order_value", _("Order Value")),
		{"fieldname": "terms", "label": _("LD Terms"), "fieldtype": "Data", "width": 200},
		{"fieldname": "basis", "label": _("Charged On"), "fieldtype": "Data", "width": 130},
		{"fieldname": "days_late", "label": _("Days Late"), "fieldtype": "Int", "width": 85},
		{"fieldname": "late_lines", "label": _("Late Lines"), "fieldtype": "Int", "width": 85},
		{"fieldname": "pending_qty", "label": _("Pending Qty"), "fieldtype": "Float", "width": 95},
		_money("ld_now", _("LD so far")),
		_money("ld_ahead", ahead_label),
		_money("ld_added", _("Added in {0} Days").format(days)),
		_money("cap_amount", _("LD Cap")),
		{"fieldname": "cap_used", "label": _("Cap Used %"), "fieldtype": "Percent", "width": 95},
		{"fieldname": "clause", "label": _("Clause"), "fieldtype": "Data", "width": 160},
	]
	return columns, orders, message
