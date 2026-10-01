"""C2-14 - Letdown log and vendor delivery score.

PEPL Delivery Letdown rows:
  * Late: a receipt line received after the promised date + Late Delivery Grace
    Days (one row per receipt line). Removed again when that receipt is cancelled.
  * Short: a PO closed with a line short by more than the Short Receipt Tolerance
    (% of ordered). "Late + Short" when that line also had a late receipt.
    Removed again when the PO is re-opened (unless excused).
  * Excuse (Purchase Manager): a mandatory reason, logged to the Override Log;
    an excused letdown does not count against the supplier.

Delivery score (daily, onto Supplier.custom_delivery_score):
    lines received complete by their promised date  /  lines that fell due
over the Vendor Score Period (Days) before `as_of`. A line "fell due" when its
promised date is inside that period. "Complete" allows the Short Receipt
Tolerance; "by its promised date" allows the grace days. Lines with an excused
letdown are left out of both counts.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, now_datetime, today

from pepl_os.common import params
from pepl_os.common.jobs import tracked_job
from pepl_os.common.overrides import log_override
from pepl_os.pepl_purchase import tracker as trk

DOCTYPE = "PEPL Delivery Letdown"
LATE, SHORT, LATE_SHORT = "Late", "Short", "Late + Short"
EXCUSE_RULE = "PUR-LETDOWN-EXCUSE"
EXCUSE_ROLES = ("Purchase Manager", "System Manager")
SCORE_FIELD = "custom_delivery_score"
SCORED_LINES_FIELD = "custom_delivery_scored_lines"


def tolerance_percent():
	return flt(params.get_float("custom_receipt_short_tolerance_percent", 0))


def lookback_days():
	return params.get_int("custom_vendor_score_lookback_days", 365) or 365


def promised_date_of(po_item):
	"""The tracker's promised date (copied once), else the PO line's Required By date."""
	return frappe.db.get_value("PEPL Purchase Tracker Line", {"po_item": po_item}, "promised_date") or (
		frappe.db.get_value("Purchase Order Item", po_item, "schedule_date")
	)


# Late: Purchase Receipt -------------------------------------------------------------


def on_receipt_submit(doc, method=None):
	"""doc_events: Purchase Receipt on_submit. One Late row per receipt line received late."""
	grace = trk.grace_days()
	receipt_date = getdate(doc.posting_date)
	for row in doc.items:
		if not (row.purchase_order and row.purchase_order_item):
			continue
		promised = promised_date_of(row.purchase_order_item)
		if not promised:
			continue
		late_by = date_diff(receipt_date, promised)
		if late_by <= grace:
			continue
		if frappe.db.exists(DOCTYPE, {"pr_item": row.name}):
			continue
		frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"supplier": doc.supplier,
				"supplier_name": doc.supplier_name,
				"purchase_order": row.purchase_order,
				"po_item": row.purchase_order_item,
				"item_code": row.item_code,
				"letdown_type": LATE,
				"promised_date": promised,
				"receipt_date": receipt_date,
				"days_late": late_by,
				"ordered_qty": frappe.db.get_value("Purchase Order Item", row.purchase_order_item, "qty"),
				"qty_short": 0,
				"purchase_receipt": doc.name,
				"pr_item": row.name,
			}
		).insert(ignore_permissions=True)


def on_receipt_cancel(doc, method=None):
	"""doc_events: Purchase Receipt on_cancel. The receipt's Late rows go with it."""
	for name in frappe.get_all(DOCTYPE, filters={"purchase_receipt": doc.name}, pluck="name"):
		frappe.delete_doc(DOCTYPE, name, force=1, ignore_permissions=True)


# Short: PO closed with quantity pending -------------------------------------------------


def _short_beyond_tolerance(line):
	ordered = flt(line.ordered_qty)
	return ordered > 0 and flt(line.pending_qty) > ordered * tolerance_percent() / 100.0


def sync_short_letdowns(doc, method=None):
	"""doc_events: PEPL Purchase Tracker on_update. Keep Short rows in step with closed lines."""
	po = frappe.db.get_value(
		"Purchase Order", doc.purchase_order, ["supplier", "supplier_name"], as_dict=True
	)
	for line in doc.lines:
		existing = frappe.get_all(
			DOCTYPE,
			filters={"po_item": line.po_item, "letdown_type": ["in", [SHORT, LATE_SHORT]]},
			fields=["name", "excused"],
		)
		if line.line_status == trk.SHORT_CLOSED and _short_beyond_tolerance(line):
			if existing:
				continue
			late = frappe.db.exists(DOCTYPE, {"po_item": line.po_item, "letdown_type": LATE})
			promised = getdate(line.promised_date) if line.promised_date else None
			close_date = getdate(today())
			frappe.get_doc(
				{
					"doctype": DOCTYPE,
					"supplier": po.supplier,
					"supplier_name": po.supplier_name,
					"purchase_order": doc.purchase_order,
					"po_item": line.po_item,
					"item_code": line.item_code,
					"letdown_type": LATE_SHORT if late else SHORT,
					"promised_date": promised,
					"receipt_date": close_date,
					"days_late": max(0, date_diff(close_date, promised)) if promised else 0,
					"ordered_qty": line.ordered_qty,
					"qty_short": line.pending_qty,
				}
			).insert(ignore_permissions=True)
		else:
			for row in existing:
				if not row.excused:  # PO re-opened: no longer short-closed
					frappe.delete_doc(DOCTYPE, row.name, force=1, ignore_permissions=True)


# Excuse ------------------------------------------------------------------------------------


@frappe.whitelist()
def excuse_letdown(name, reason):
	"""Excuse button (Purchase Manager): the letdown no longer counts against the supplier."""
	frappe.only_for(EXCUSE_ROLES)
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.excused:
		frappe.throw(_("This letdown is already excused."))
	log_override(
		EXCUSE_RULE,
		DOCTYPE,
		doc.name,
		_("{0} letdown excused for {1}, {2} ({3})").format(
			_(doc.letdown_type), doc.supplier_name or doc.supplier, doc.purchase_order, doc.item_code
		),
		reason,
	)
	doc.db_set(
		{
			"excused": 1,
			"excuse_reason": reason.strip(),
			"excused_by": frappe.session.user,
			"excused_on": now_datetime(),
		}
	)
	update_supplier_score(doc.supplier)
	return doc.name


# Delivery score -------------------------------------------------------------------------


def _excused_lines(supplier):
	return set(frappe.get_all(DOCTYPE, filters={"supplier": supplier, "excused": 1}, pluck="po_item"))


def _received_by(po_item, by_date):
	rows = frappe.db.sql(
		"""
		select sum(pri.received_qty) from `tabPurchase Receipt Item` pri
		join `tabPurchase Receipt` pr on pr.name = pri.parent
		where pr.docstatus = 1 and pri.purchase_order_item = %s and pr.posting_date <= %s
		""",
		(po_item, by_date),
	)
	return flt(rows[0][0]) if rows else 0.0


def delivery_score(supplier, as_of=None):
	"""(score %, lines scored). Score is None when no line fell due in the period."""
	as_of = getdate(as_of or today())
	since = add_days(as_of, -lookback_days())
	grace, tolerance = trk.grace_days(), tolerance_percent()
	lines = frappe.db.sql(
		"""
		select l.po_item, l.ordered_qty, l.promised_date
		from `tabPEPL Purchase Tracker Line` l
		join `tabPEPL Purchase Tracker` t on t.name = l.parent
		where t.supplier = %s and t.status != %s and l.promised_date > %s and l.promised_date <= %s
		""",
		(supplier, trk.CANCELLED, since, as_of),
		as_dict=True,
	)
	excused = _excused_lines(supplier)
	due = on_time = 0
	for line in lines:
		if line.po_item in excused:
			continue
		due += 1
		needed = flt(line.ordered_qty) * (1 - tolerance / 100.0)
		if _received_by(line.po_item, add_days(line.promised_date, grace)) >= needed - 1e-9:
			on_time += 1
	if not due:
		return None, 0
	return round(on_time * 100.0 / due, 1), due


def update_supplier_score(supplier, as_of=None):
	score, lines = delivery_score(supplier, as_of)
	frappe.db.set_value(
		"Supplier", supplier, {SCORE_FIELD: score or 0, SCORED_LINES_FIELD: lines}, update_modified=False
	)
	return score


def suppliers_to_score():
	return frappe.get_all("PEPL Purchase Tracker", distinct=True, pluck="supplier")


def refresh_scores(as_of=None):
	count = 0
	for supplier in suppliers_to_score():
		if not supplier:
			continue
		try:
			update_supplier_score(supplier, as_of)
			count += 1
		except Exception:
			frappe.log_error(title=f"PEPL: delivery score not updated for {supplier}")
	return count


@tracked_job("Vendor delivery scores")
def daily_delivery_scores():
	count = refresh_scores()
	return {"records_touched": count, "message": f"{count} supplier delivery score(s) updated"}


@frappe.whitelist()
def refresh_scores_now(supplier=None):
	"""Update the delivery score(s) now (it also runs every morning)."""
	frappe.only_for(("System Manager", "Purchase Manager"))
	if supplier:
		return update_supplier_score(supplier)
	return refresh_scores()
