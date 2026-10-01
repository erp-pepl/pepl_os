# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-18 - Scrap Recovery by month and metal."""

from frappe import _

from pepl_os.pepl_stores.scrap import scrap_recovery


def execute(filters=None):
	kg = {"fieldtype": "Float", "width": 105}
	money = {"fieldtype": "Currency", "width": 120}
	columns = [
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 85},
		{
			"fieldname": "metal",
			"label": _("Metal"),
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 140,
		},
		{"fieldname": "kg_generated", "label": _("Kg Generated"), **kg},
		{"fieldname": "kg_sold", "label": _("Kg Sold"), **kg},
		{"fieldname": "avg_realised_rate", "label": _("Realised Rate / Kg"), **money},
		{"fieldname": "avg_master_rate", "label": _("Rate Master / Kg"), **money},
		{"fieldname": "value_realised", "label": _("Value Realised"), **money},
		{"fieldname": "closing_kg", "label": _("Closing Kg"), **kg},
		{"fieldname": "closing_value", "label": _("Closing Value"), **money},
		{"fieldname": "rm_issued_kg", "label": _("RM Issued Kg"), **kg},
		{
			"fieldname": "scrap_percent_of_rm",
			"label": _("Scrap % of RM"),
			"fieldtype": "Percent",
			"width": 105,
		},
	]
	return columns, scrap_recovery(filters)
