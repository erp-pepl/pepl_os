# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-B2 - Estimate vs Actual Cost: the CST estimate a piece against what each Job Order (or each item) really
cost a piece - material, machining, job work & other, overhead. See pepl_production/costing.py for every rule."""

from frappe import _

from pepl_os.pepl_production import costing


def _money(fieldname, label, width=110):
	return {"fieldname": fieldname, "label": label, "fieldtype": "Currency", "width": width}


def execute(filters=None):
	filters = filters or {}
	by_item = filters.get("group_by") == "Item"
	columns = []
	if not by_item:
		columns.append(
			{
				"fieldname": "job_order",
				"label": _("Job Order"),
				"fieldtype": "Link",
				"options": "Work Order",
				"width": 150,
			}
		)
	columns += [
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 150},
	]
	if by_item:
		columns.append({"fieldname": "job_orders", "label": _("Job Orders"), "fieldtype": "Int", "width": 90})
	else:
		columns += [
			{
				"fieldname": "sales_order",
				"label": _("Sales Order"),
				"fieldtype": "Link",
				"options": "Sales Order",
				"width": 140,
			},
			{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		]
	columns += [
		{"fieldname": "pieces", "label": _("Pieces"), "fieldtype": "Float", "width": 80},
		{"fieldname": "cst", "label": _("CST"), "fieldtype": "Data", "width": 110},
		_money("est_total", _("Estimate a Piece")),
		_money("act_total", _("Actual a Piece")),
		_money("variance", _("Variance a Piece")),
		{"fieldname": "variance_percent", "label": _("Variance %"), "fieldtype": "Percent", "width": 95},
		_money("est_material", _("Material Est.")),
		_money("act_material", _("Material Act.")),
		_money("est_machining", _("Machining Est.")),
		_money("act_machining", _("Machining Act.")),
		_money("est_other", _("Job Work & Other Est."), 130),
		_money("act_other", _("Job Work & Other Act."), 130),
		_money("est_overhead", _("Overhead Est.")),
		_money("act_overhead", _("Overhead Act.")),
		_money("estimate_total", _("Estimate x Pieces"), 130),
		_money("actual_total", _("Actual Cost"), 120),
	]
	if not by_item:
		columns.append({"fieldname": "basis", "label": _("Estimate From"), "fieldtype": "Data", "width": 160})
	columns.append({"fieldname": "notes", "label": _("Notes"), "fieldtype": "Data", "width": 320})
	data = costing.rows(filters)
	return columns, data, costing.summary_message(data)
