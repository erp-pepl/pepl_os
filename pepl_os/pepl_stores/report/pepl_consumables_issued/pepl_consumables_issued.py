# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-21 - Consumables Issued per day / week / month, and as a % of net sales."""

from frappe import _
from frappe.utils import flt

from pepl_os.pepl_stores.consumables import consumables_issued

PERCENT_CHART = "% of Sales"


def execute(filters=None):
	filters = filters or {}
	rows, per_period, months = consumables_issued(filters)
	group_label = filters.get("group_by") or "Item"
	columns = [
		{
			"fieldname": "period",
			"label": _(filters.get("period") or "Day"),
			"fieldtype": "Data",
			"width": 105,
		},
		{"fieldname": "group", "label": _(group_label), "fieldtype": "Data", "width": 170},
		{"fieldname": "label", "label": _("Name"), "fieldtype": "Data", "width": 200},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "lines", "label": _("Issues"), "fieldtype": "Int", "width": 75},
	]
	if filters.get("chart") == PERCENT_CHART:
		chart = {
			"data": {
				"labels": [m.month for m in months],
				"datasets": [
					{
						"name": _("Consumables % of net sales"),
						"values": [flt(m.percent_of_sales, 2) for m in months],
					}
				],
			},
			"type": "bar",
		}
	else:
		chart = {
			"data": {
				"labels": [p for p, _v in per_period],
				"datasets": [{"name": _("Consumables value"), "values": [flt(v, 2) for _p, v in per_period]}],
			},
			"type": "bar",
		}
	summary = []
	for m in months:
		pct = "-" if m.percent_of_sales is None else f"{flt(m.percent_of_sales, 2)}%"
		summary.append(
			{
				"value": pct,
				"label": _("{0}: consumables {1} of net sales {2}").format(
					m.month, flt(m.value, 2), flt(m.net_sales, 2)
				),
				"datatype": "Data",
				"indicator": "Blue",
			}
		)
	return columns, rows, None, chart, summary
