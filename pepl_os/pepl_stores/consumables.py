"""C2-21 - Consumables issued by day, week and month, and as a % of sales.

Outflows of Consumables-class items from the stock ledger: Material Issue, Manufacture /
Material Consumption for Manufacture, and transfers into a WIP store. Store-to-store
moves are not consumption, so nothing is counted twice. (Shift Production Entry in
Cycle 3a posts its consumables as Stock Entries, so they appear here too.)

Week = Monday to Sunday, shown by its Monday. % of sales = consumables value of the
month / that month's net total of submitted Sales Invoices (credit notes reduce it).
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from pepl_os.pepl_stores import stock_tree

DAY, WEEK, MONTH = "Day", "Week", "Month"
BY_ITEM, BY_GROUP, BY_MACHINE = "Item", "Item Group", "Machine Group"
MACHINE_FIELD = "custom_machine_group"
CONSUMING = ("Material Issue", "Manufacture", "Material Consumption for Manufacture")
TRANSFERS = ("Material Transfer", "Material Transfer for Manufacture")
NOT_GIVEN = "(not given)"


def period_of(day, period):
	day = getdate(day)
	if period == MONTH:
		return day.strftime("%Y-%m")
	if period == WEEK:
		return str(add_days(day, -day.weekday()))
	return str(day)


def outflows(company=None, from_date=None, to_date=None):
	"""Each consumption line: date, item, item group, machine group, qty, value."""
	to_date = getdate(to_date or today())
	from_date = getdate(from_date or add_days(to_date, -29))
	conditions = [
		"sle.is_cancelled = 0",
		"sle.actual_qty < 0",
		"sle.voucher_type = 'Stock Entry'",
		"i.custom_stock_class = %(cls)s",
		"sle.posting_date between %(from)s and %(to)s",
	]
	values = {"cls": stock_tree.CONSUMABLES, "from": from_date, "to": to_date}
	if company:
		conditions.append("sle.company = %(company)s")
		values["company"] = company
	machine = (
		f"sed.{MACHINE_FIELD}" if frappe.get_meta("Stock Entry Detail").has_field(MACHINE_FIELD) else "null"
	)
	rows = frappe.db.sql(
		f"""select sle.posting_date, sle.item_code, i.item_name, i.item_group, {machine} as machine_group,
			-sle.actual_qty as qty, -sle.stock_value_difference as value, se.purpose, sed.t_warehouse
		from `tabStock Ledger Entry` sle
		join `tabItem` i on i.name = sle.item_code
		join `tabStock Entry` se on se.name = sle.voucher_no
		left join `tabStock Entry Detail` sed on sed.name = sle.voucher_detail_no
		where {" and ".join(conditions)}""",
		values,
		as_dict=True,
	)
	from pepl_os.pepl_stores.reorder import _wip_stores

	wip = None
	out = []
	for r in rows:
		if r.purpose in TRANSFERS:
			if wip is None:
				wip = _wip_stores()
			if r.t_warehouse not in wip:
				continue
		elif r.purpose not in CONSUMING:
			continue
		out.append(r)
	return out


def net_sales_by_month(company=None, from_date=None, to_date=None):
	conditions = ["docstatus = 1", "posting_date between %(from)s and %(to)s"]
	values = {"from": getdate(from_date), "to": getdate(to_date)}
	if company:
		conditions.append("company = %(company)s")
		values["company"] = company
	rows = frappe.db.sql(
		f"""select date_format(posting_date, '%%Y-%%m') as month, sum(base_net_total) as net
		from `tabSales Invoice` where {" and ".join(conditions)} group by month""",
		values,
		as_dict=True,
	)
	return {r.month: flt(r.net) for r in rows}


def consumables_issued(filters=None):
	"""(rows, chart_rows): rows per period and group; chart_rows per period with value and % of sales."""
	filters = frappe._dict(filters or {})
	period = filters.get("period") or DAY
	group_by = filters.get("group_by") or BY_ITEM
	to_date = getdate(filters.get("to_date") or today())
	from_date = getdate(filters.get("from_date") or add_days(to_date, -29))
	lines = outflows(filters.get("company"), from_date, to_date)
	grouped, per_period = {}, {}
	for r in lines:
		key = period_of(r.posting_date, period)
		if group_by == BY_GROUP:
			group, label = r.item_group, r.item_group
		elif group_by == BY_MACHINE:
			group = label = r.machine_group or NOT_GIVEN
		else:
			group, label = r.item_code, r.item_name
		row = grouped.setdefault(
			(key, group), frappe._dict(period=key, group=group, label=label, qty=0.0, value=0.0, lines=0)
		)
		row.qty += flt(r.qty)
		row.value += flt(r.value)
		row.lines += 1
		per_period[key] = per_period.get(key, 0.0) + flt(r.value)
	sales = net_sales_by_month(filters.get("company"), from_date, to_date)
	months = {}
	for r in lines:
		m = getdate(r.posting_date).strftime("%Y-%m")
		months[m] = months.get(m, 0.0) + flt(r.value)
	month_rows = [
		frappe._dict(
			month=m,
			value=v,
			net_sales=sales.get(m, 0.0),
			percent_of_sales=(v / sales[m] * 100) if sales.get(m) else None,
		)
		for m, v in sorted(months.items())
	]
	rows = [grouped[k] for k in sorted(grouped)]
	return rows, sorted(per_period.items()), month_rows
