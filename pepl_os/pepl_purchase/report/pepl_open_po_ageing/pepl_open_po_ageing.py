# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-13 - Open PO value per supplier by age (since PO date) and by days overdue (since promised date)."""

from frappe import _

from pepl_os.pepl_purchase.chase import open_po_ageing


def _money(fieldname, label):
	return {"fieldname": fieldname, "label": label, "fieldtype": "Currency", "width": 110}


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
		{"fieldname": "open_orders", "label": _("Open POs"), "fieldtype": "Int", "width": 80},
		_money("open_value", _("Open Value")),
		_money("age_0_30", _("Age 0-30")),
		_money("age_31_60", _("Age 31-60")),
		_money("age_61_90", _("Age 61-90")),
		_money("age_90_plus", _("Age 90+")),
		_money("not_overdue", _("Not Overdue")),
		_money("overdue_1_30", _("Overdue 1-30")),
		_money("overdue_31_60", _("Overdue 31-60")),
		_money("overdue_61_90", _("Overdue 61-90")),
		_money("overdue_90_plus", _("Overdue 90+")),
	]
	return columns, open_po_ageing(filters)
