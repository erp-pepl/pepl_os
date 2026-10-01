# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-23 - Procurement Funnel: MRs -> RFQs -> comparisons approved -> POs -> fully received, per month."""

from frappe import _

from pepl_os.pepl_purchase.command_centre import procurement_funnel


def execute(filters=None):
	n = {"fieldtype": "Int", "width": 105}
	money = {"fieldtype": "Currency", "width": 135}
	columns = [
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 85},
		{"fieldname": "material_requests", "label": _("Material Requests"), **n},
		{"fieldname": "rfqs", "label": _("RFQs"), **n},
		{"fieldname": "comparisons_approved", "label": _("Comparisons Approved"), **n},
		{"fieldname": "comparisons_value", "label": _("Awarded Value"), **money},
		{"fieldname": "purchase_orders", "label": _("Purchase Orders"), **n},
		{"fieldname": "po_value", "label": _("PO Value"), **money},
		{"fieldname": "fully_received", "label": _("Fully Received"), **n},
		{"fieldname": "received_value", "label": _("Received PO Value"), **money},
	]
	rows = procurement_funnel(filters)
	chart = {
		"data": {
			"labels": [r.month for r in rows],
			"datasets": [
				{"name": _("Material Requests"), "values": [r.material_requests for r in rows]},
				{"name": _("RFQs"), "values": [r.rfqs for r in rows]},
				{"name": _("Purchase Orders"), "values": [r.purchase_orders for r in rows]},
				{"name": _("Fully Received"), "values": [r.fully_received for r in rows]},
			],
		},
		"type": "bar",
	}
	return columns, rows, None, chart
