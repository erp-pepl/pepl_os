"""C2-23 - Procurement Command Centre: the six number cards, the funnel, the tracker-refresh line.

Each card method is whitelisted, takes the card's `filters` and returns
{"value", "fieldtype", "route", "route_options"} so clicking the card opens the report
or list that explains the number.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from pepl_os.common import params

OPEN_LINE = ("Overdue", "Due Today", "Due Soon", "Part Received", "Not Due")
TRACKER_JOB = "pepl_os.pepl_purchase.tracker.refresh_open_purchase_trackers"
BLOCK = "PEPL Tracker Refreshed"


def _card(value, fieldtype, route, route_options=None):
	return {"value": flt(value), "fieldtype": fieldtype, "route": route, "route_options": route_options or {}}


def _open_tracker_lines(extra="", values=None):
	return frappe.db.sql(
		f"""select l.parent, l.po_item, l.pending_qty, l.promised_date, l.revised_date, l.line_status
		from `tabPEPL Purchase Tracker Line` l
		join `tabPEPL Purchase Tracker` t on t.name = l.parent
		where t.status not in ('Completed', 'Cancelled') and l.line_status in %(open)s and l.pending_qty > 0 {extra}""",
		dict(values or {}, open=OPEN_LINE),
		as_dict=True,
	)


@frappe.whitelist()
def overdue_deliveries(filters=None):
	"""Open tracker lines with status Overdue."""
	count = len(_open_tracker_lines("and l.line_status = 'Overdue'"))
	return _card(count, "Int", ["query-report", "PEPL Chase List"])


@frappe.whitelist()
def pos_due_this_week(filters=None):
	"""Purchase Orders with an open line due within the next 7 days (today included)."""
	start, end = getdate(today()), getdate(add_days(today(), 7))
	rows = _open_tracker_lines(
		"and coalesce(l.revised_date, l.promised_date) between %(start)s and %(end)s",
		{"start": start, "end": end},
	)
	trackers = {r.parent for r in rows}
	orders = {frappe.db.get_value("PEPL Purchase Tracker", t, "purchase_order") for t in trackers}
	return _card(len(orders), "Int", ["List", "PEPL Purchase Tracker"], {"status": ["!=", "Completed"]})


@frappe.whitelist()
def msme_payments_due(filters=None):
	"""Rupees still owed on MSME bills (the 45-day clock)."""
	value = frappe.db.sql(
		"""select ifnull(sum(outstanding_amount), 0) from `tabPurchase Invoice`
		where docstatus = 1 and custom_is_msme = 1 and is_return = 0 and outstanding_amount > 0"""
	)[0][0]
	return _card(value, "Currency", ["query-report", "PEPL Vendor Payment Priority"])


@frappe.whitelist()
def open_po_value(filters=None):
	"""Sum of pending qty x rate over open tracker lines."""
	value = frappe.db.sql(
		"""select ifnull(sum(l.pending_qty * poi.base_rate), 0)
		from `tabPEPL Purchase Tracker Line` l
		join `tabPEPL Purchase Tracker` t on t.name = l.parent
		join `tabPurchase Order Item` poi on poi.name = l.po_item
		where t.status not in ('Completed', 'Cancelled') and l.line_status in %(open)s and l.pending_qty > 0""",
		{"open": OPEN_LINE},
	)[0][0]
	return _card(value, "Currency", ["query-report", "PEPL Open PO Ageing"])


@frappe.whitelist()
def supplier_documents_expiring(filters=None):
	"""Supplier approval documents expiring within the alert window (not yet expired)."""
	days = params.get_int("custom_supplier_doc_expiry_alert_days", 30)
	count = frappe.db.sql(
		"""select count(*) from `tabPEPL Supplier Approval Document`
		where parenttype = 'PEPL Supplier Approval' and ifnull(not_applicable, 0) = 0
			and expiry_date between %s and %s""",
		(getdate(today()), getdate(add_days(today(), days))),
	)[0][0]
	return _card(count, "Int", ["List", "PEPL Supplier Approval"])


@frappe.whitelist()
def scrap_stock_value(filters=None):
	"""Stock value in Scrap Yard (customer-material scrap, in CSM Scrap, is not PEPL's)."""
	value = frappe.db.sql(
		"""select ifnull(sum(b.stock_value), 0) from `tabBin` b
		join `tabWarehouse` w on w.name = b.warehouse where w.warehouse_name = 'Scrap Yard'"""
	)[0][0]
	return _card(value, "Currency", ["query-report", "PEPL Scrap Recovery"])


@frappe.whitelist()
def tracker_last_refreshed():
	"""For the line under the cards: when the Purchase Tracker refresh last ran successfully."""
	row = frappe.get_all(
		"PEPL Job Run",
		filters={"method": TRACKER_JOB, "status": "Success"},
		fields=["finished_at"],
		order_by="finished_at desc",
		limit=1,
	)
	at = row[0].finished_at if row else None
	return {
		"at": at,
		"text": frappe.format(at, {"fieldtype": "Datetime"}) if at else _("never"),
		"is_today": bool(at and getdate(at) == getdate(today())),
	}


BLOCK_HTML = '<div class="pepl-tracker-refreshed" style="padding: 6px 2px; font-size: 13px;">…</div>'
BLOCK_SCRIPT = """frappe.call("pepl_os.pepl_purchase.command_centre.tracker_last_refreshed").then((r) => {
	const i = r.message || {};
	const el = root_element.querySelector(".pepl-tracker-refreshed");
	el.innerHTML = `<span class="indicator ${i.is_today ? "green" : "red"}">${__("Purchase Tracker last refreshed: {0}", [i.text || ""])}</span>`;
});"""


def ensure_command_centre_block():
	"""Install / migrate: the "Purchase Tracker last refreshed" line used on both workspaces."""
	values = {"html": BLOCK_HTML, "script": BLOCK_SCRIPT, "style": "", "private": 0}
	if frappe.db.exists("Custom HTML Block", BLOCK):
		doc = frappe.get_doc("Custom HTML Block", BLOCK)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Custom HTML Block", **values})
		doc.insert(ignore_permissions=True, set_name=BLOCK)
	return doc.name


# Procurement Funnel ---------------------------------------------------------------------


def _monthly(sql, values):
	return {r.month: r for r in frappe.db.sql(sql, values, as_dict=True)}


def procurement_funnel(filters=None):
	"""Per month: MRs -> RFQs -> comparisons approved -> POs -> POs fully received (counts and value)."""
	filters = frappe._dict(filters or {})
	to_date = getdate(filters.get("to_date") or today())
	from_date = getdate(filters.get("from_date") or add_days(to_date, -364))
	company = filters.get("company")
	v = {"from": from_date, "to": to_date, "company": company}
	cc = " and company = %(company)s" if company else ""
	mrs = _monthly(
		f"""select date_format(transaction_date, '%%Y-%%m') as month, count(*) as n
		from `tabMaterial Request` where docstatus = 1 and material_request_type = 'Purchase'
		and transaction_date between %(from)s and %(to)s{cc} group by month""",
		v,
	)
	rfqs = _monthly(
		f"""select date_format(transaction_date, '%%Y-%%m') as month, count(*) as n
		from `tabRequest for Quotation` where docstatus = 1 and transaction_date between %(from)s and %(to)s{cc}
		group by month""",
		v,
	)
	qcs = {}
	if frappe.db.exists("DocType", "PEPL Quotation Comparison"):
		qc_company = " and r.company = %(company)s" if company else ""
		qcs = _monthly(
			f"""select date_format(c.modified, '%%Y-%%m') as month, count(distinct c.name) as n,
				ifnull(sum(row.awarded_qty * row.base_rate), 0) as value
			from `tabPEPL Quotation Comparison` c
			join `tabRequest for Quotation` r on r.name = c.request_for_quotation
			left join `tabPEPL Quotation Comparison Row` row on row.parent = c.name
			where c.docstatus = 1 and date(c.modified) between %(from)s and %(to)s{qc_company} group by month""",
			v,
		)
	pos = _monthly(
		f"""select date_format(transaction_date, '%%Y-%%m') as month, count(*) as n,
			ifnull(sum(base_grand_total), 0) as value,
			sum(case when per_received >= 100 then 1 else 0 end) as received_n,
			ifnull(sum(case when per_received >= 100 then base_grand_total else 0 end), 0) as received_value
		from `tabPurchase Order` where docstatus = 1 and transaction_date between %(from)s and %(to)s{cc}
		group by month""",
		v,
	)
	months = sorted(set(mrs) | set(rfqs) | set(qcs) | set(pos))
	rows = []
	for m in months:
		po = pos.get(m) or frappe._dict()
		qc = qcs.get(m) or frappe._dict()
		rows.append(
			frappe._dict(
				month=m,
				material_requests=(mrs.get(m) or frappe._dict()).get("n") or 0,
				rfqs=(rfqs.get(m) or frappe._dict()).get("n") or 0,
				comparisons_approved=qc.get("n") or 0,
				comparisons_value=flt(qc.get("value")),
				purchase_orders=po.get("n") or 0,
				po_value=flt(po.get("value")),
				fully_received=int(po.get("received_n") or 0),
				received_value=flt(po.get("received_value")),
			)
		)
	return rows
