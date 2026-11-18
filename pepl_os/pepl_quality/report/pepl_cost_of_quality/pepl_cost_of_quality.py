# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3b-B2 - Cost of Quality: rejection, scrap recovered, NCR rework, other NCR cost and customer returns, in rupees,
by month or by item."""

import frappe
from frappe import _

from pepl_os.pepl_quality import coq


def _money(fieldname, label, width=130):
	return {"fieldname": fieldname, "label": label, "fieldtype": "Currency", "width": width}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	by_item = filters.get("group_by") == "Item"
	columns = [
		{
			"fieldname": "key",
			"label": _("Item") if by_item else _("Month"),
			"fieldtype": "Link" if by_item else "Data",
			"options": "Item" if by_item else None,
			"width": 160,
		},
		{"fieldname": "rejected_pieces", "label": _("Rejected Pieces"), "fieldtype": "Float", "width": 110},
		_money("rejection", _("Rejection")),
		_money("scrap_recovered", _("Scrap Recovered")),
		_money("ncr_rework", _("NCR Rework")),
		_money("ncr_other", _("NCR Other (internal)")),
		_money("customer", _("Customer (external)")),
		_money("total", _("Cost of Quality"), 140),
		{"fieldname": "ncrs", "label": _("NCRs"), "fieldtype": "Int", "width": 70},
		{"fieldname": "notes", "label": _("Not priced"), "fieldtype": "Data", "width": 320},
	]
	data = coq.rows(filters)
	total = round(sum(r.total for r in data), 2)
	summary = [
		{
			"label": _("Cost of Quality"),
			"value": total,
			"datatype": "Currency",
			"indicator": "Red" if total else "Green",
		},
		{
			"label": _("Rejection (net of scrap)"),
			"value": round(sum(r.rejection - r.scrap_recovered for r in data), 2),
			"datatype": "Currency",
			"indicator": "Orange",
		},
		{
			"label": _("Customer (external)"),
			"value": round(sum(r.customer for r in data), 2),
			"datatype": "Currency",
			"indicator": "Red" if any(r.customer for r in data) else "Green",
		},
	]
	chart = None
	if data and not by_item:
		chart = {
			"data": {
				"labels": [r.key for r in data],
				"datasets": [{"name": _("Cost of Quality"), "values": [r.total for r in data]}],
			},
			"type": "bar",
			"fieldtype": "Currency",
		}
	return columns, data, None, chart, summary
