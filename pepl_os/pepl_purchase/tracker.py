"""C2-12 - Purchase Tracker: every submitted PO tracked line by line against its promised date.

One compute function (compute / recompute_tracker) feeds everything. Four
triggers call it, so the tracker can never silently freeze:
  * Purchase Order on_change: submit creates the tracker; cancel, close,
    re-open and "Update Items" recompute it (ERPNext's close sets the status
    through db_set, which fires on_change).
  * Purchase Receipt on_submit / on_cancel: the trackers of the POs on its lines.
  * The daily job refresh_open_purchase_trackers (@tracked_job): every open tracker,
    so days overdue move on each morning.
  * The "Refresh now" button.

Line status at `as_of` (today unless given):
  Received       pending qty <= 0
  Short-Closed   the PO is Closed with qty still pending
  Overdue        pending and as_of > promised date + late grace days
  Due Today      pending and as_of is on or after the promised date, within the grace days
  Due Soon       pending and due within the Delivery Alert Lead Days
  Part Received  something received, not yet due
  Not Due        otherwise
Days overdue = as_of - promised date. The promised date is copied once from the
PO line's Required By date and never changes; the vendor's revised date is for
chasing only.

Tracker status = the worst open line (Overdue > Due Today > Due Soon >
Part Received > Not Due); Completed when every line is Received or
Short-Closed; Cancelled when the PO is cancelled.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, now_datetime, today

from pepl_os.common import params
from pepl_os.common.jobs import tracked_job

DOCTYPE = "PEPL Purchase Tracker"
QTY_PRECISION = 3

RECEIVED, SHORT_CLOSED = "Received", "Short-Closed"
OVERDUE, DUE_TODAY, DUE_SOON, PART_RECEIVED, NOT_DUE = (
	"Overdue",
	"Due Today",
	"Due Soon",
	"Part Received",
	"Not Due",
)
COMPLETED, CANCELLED = "Completed", "Cancelled"
OPEN_ORDER = (OVERDUE, DUE_TODAY, DUE_SOON, PART_RECEIVED, NOT_DUE)  # worst first
CLOSED_LINE = (RECEIVED, SHORT_CLOSED)
COLOURS = {
	OVERDUE: "red",
	DUE_TODAY: "orange",
	DUE_SOON: "yellow",
	PART_RECEIVED: "blue",
	NOT_DUE: "gray",
	RECEIVED: "green",
	SHORT_CLOSED: "gray",
	COMPLETED: "green",
	CANCELLED: "gray",
}


def grace_days():
	return params.get_int("custom_late_grace_days", 0)


def lead_days():
	return params.get_int("custom_delivery_alert_lead_days", 0)


def line_status(ordered, received, promised, as_of, po_closed=False, grace=0, lead=0):
	"""(status, days_to_due, days_overdue) for one line. Pure: no database."""
	pending = flt(flt(ordered) - flt(received), QTY_PRECISION)
	days_to_due = date_diff(promised, as_of) if promised else 0
	if pending <= 0:
		return RECEIVED, days_to_due, 0
	if po_closed:
		return SHORT_CLOSED, days_to_due, 0
	if promised:
		late_by = date_diff(as_of, promised)
		if late_by > grace:
			return OVERDUE, days_to_due, late_by
		if late_by >= 0:
			return DUE_TODAY, days_to_due, 0
		if days_to_due <= lead:
			return DUE_SOON, days_to_due, 0
	if flt(received) > 0:
		return PART_RECEIVED, days_to_due, 0
	return NOT_DUE, days_to_due, 0


def overall_status(line_statuses, po_cancelled=False):
	if po_cancelled:
		return CANCELLED
	open_ = [s for s in line_statuses if s not in CLOSED_LINE]
	if not open_:
		return COMPLETED
	return next(s for s in OPEN_ORDER if s in open_)


def _sync_lines(doc, po):
	"""Add a line for each PO line not yet tracked; drop lines whose PO line is gone.

	The promised date is set when the line is added and never touched again.
	"""
	po_rows = {r.name: r for r in po.items}
	keep = [line for line in doc.lines if line.po_item in po_rows]
	tracked = {line.po_item for line in keep}
	doc.set("lines", keep)
	for r in po.items:
		if r.name not in tracked:
			doc.append(
				"lines",
				{
					"po_item": r.name,
					"item_code": r.item_code,
					"item_name": r.item_name,
					"uom": r.uom,
					"promised_date": r.schedule_date,
				},
			)
	order = {r.name: r.idx for r in po.items}
	doc.lines.sort(key=lambda line: order.get(line.po_item, 0))
	for i, line in enumerate(doc.lines, start=1):
		line.idx = i
	return po_rows


def compute(doc, as_of=None):
	"""Rewrite every computed field of the tracker from its Purchase Order."""
	as_of = getdate(as_of or today())
	po = frappe.get_doc("Purchase Order", doc.purchase_order)
	if po.docstatus == 0:
		frappe.throw(
			_("Purchase Order {0} is not submitted yet, so there is nothing to track.").format(po.name)
		)
	po_rows = _sync_lines(doc, po)
	closed = po.status == "Closed"
	grace, lead = grace_days(), lead_days()
	for line in doc.lines:
		row = po_rows[line.po_item]
		line.item_code = row.item_code
		line.ordered_qty = flt(row.qty)
		line.received_qty = flt(row.received_qty)
		line.pending_qty = max(0.0, flt(flt(row.qty) - flt(row.received_qty), QTY_PRECISION))
		line.line_status, line.days_to_due, line.days_overdue = line_status(
			row.qty, row.received_qty, line.promised_date, as_of, closed, grace, lead
		)
	doc.status = overall_status([line.line_status for line in doc.lines], po.docstatus == 2)
	open_lines = [line for line in doc.lines if line.line_status not in CLOSED_LINE]
	doc.open_lines = 0 if doc.status == CANCELLED else len(open_lines)
	doc.next_due_date = min(
		(getdate(line.promised_date) for line in open_lines if line.promised_date), default=None
	)
	doc.worst_days_overdue = max((line.days_overdue for line in open_lines), default=0)
	doc.supplier = po.supplier
	doc.supplier_name = po.supplier_name
	doc.company = po.company
	doc.buyer = po.owner
	doc.vendor_criticality = frappe.db.get_value("Supplier", po.supplier, "custom_vendor_criticality")
	doc.delivery_score = frappe.db.get_value("Supplier", po.supplier, "custom_delivery_score")
	doc.last_computed_on = now_datetime()
	return doc


def tracker_of(purchase_order):
	return frappe.db.get_value(DOCTYPE, {"purchase_order": purchase_order}, "name")


def recompute_tracker(name, as_of=None):
	"""services.recompute_tracker: recompute and save one tracker. Returns its status."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.flags.as_of = as_of
	doc.flags.ignore_permissions = True
	doc.save()
	return doc.status


def ensure_tracker(purchase_order, as_of=None):
	"""Create the tracker of a submitted PO, or recompute it. Returns its name."""
	name = tracker_of(purchase_order)
	if name:
		recompute_tracker(name, as_of)
		return name
	doc = frappe.get_doc({"doctype": DOCTYPE, "purchase_order": purchase_order})
	doc.flags.as_of = as_of
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


# Triggers --------------------------------------------------------------------


def on_po_change(doc, method=None):
	"""doc_events: Purchase Order on_change (submit, cancel, close, re-open, Update Items)."""
	if doc.docstatus == 0 or doc.flags.pepl_tracker_busy:
		return
	if doc.docstatus == 2 and not tracker_of(doc.name):
		return
	doc.flags.pepl_tracker_busy = True
	try:
		ensure_tracker(doc.name)
	finally:
		doc.flags.pepl_tracker_busy = False


def on_po_trash(doc, method=None):
	"""doc_events: Purchase Order on_trash. A deleted (cancelled) PO takes its tracker with it."""
	name = tracker_of(doc.name)
	if name:
		frappe.delete_doc(DOCTYPE, name, force=1, ignore_permissions=True)


def on_receipt_change(doc, method=None):
	"""doc_events: Purchase Receipt on_submit / on_cancel."""
	for po in sorted({r.purchase_order for r in doc.items if r.purchase_order}):
		if frappe.db.get_value("Purchase Order", po, "docstatus") == 1 or tracker_of(po):
			ensure_tracker(po)


def open_trackers():
	return frappe.get_all(DOCTYPE, filters={"status": ["not in", [COMPLETED, CANCELLED]]}, pluck="name")


def refresh_all(as_of=None):
	"""Recompute every open tracker. Returns the number recomputed."""
	count = 0
	for name in open_trackers():
		try:
			recompute_tracker(name, as_of)
			count += 1
		except Exception:
			frappe.log_error(title=f"PEPL: Purchase Tracker {name} not recomputed")
	return count


@tracked_job("Purchase Tracker daily recompute")
def refresh_open_purchase_trackers():
	from pepl_os.pepl_purchase.chase import sync_chase_todos  # C2-13; chase imports this module

	count = refresh_all()
	overdue = sync_chase_todos()
	return {
		"records_touched": count,
		"message": f"{count} open purchase tracker(s) recomputed; {overdue} overdue (chase ToDos updated)",
	}


# Buttons and panels ----------------------------------------------------------


@frappe.whitelist()
def refresh_now(name, as_of=None):
	"""Refresh now button. `as_of` (System Manager only) shows the tracker as it will be on that date;
	the next refresh or the daily job puts it back to today."""
	frappe.get_doc(DOCTYPE, name).check_permission("read")
	if as_of:
		frappe.only_for("System Manager")
	return recompute_tracker(name, as_of)


def panel_rows(doc):
	rows = [
		{
			"text": _("Status: {0}").format(_(doc.status))
			+ (_(", {0} day(s) overdue").format(doc.worst_days_overdue) if doc.worst_days_overdue else ""),
			"colour": COLOURS.get(doc.status, "gray"),
		}
	]
	for line in doc.lines:
		text = _("Line {0} {1}: {2} pending, promised {3}").format(
			line.idx, line.item_code, line.pending_qty, frappe.format(line.promised_date, "Date")
		)
		if line.days_overdue:
			text += _(", {0} day(s) overdue").format(line.days_overdue)
		if line.revised_date:
			text += _(", vendor now says {0}").format(frappe.format(line.revised_date, "Date"))
		rows.append(
			{"text": f"{text} ({_(line.line_status)})", "colour": COLOURS.get(line.line_status, "gray")}
		)
	chase = (
		_("Last chased {0} ({1} time(s))").format(
			frappe.format(doc.last_chased_on, "Datetime"), doc.chase_count
		)
		if doc.last_chased_on
		else _("Not chased yet")
	)
	scored = (
		frappe.db.get_value("Supplier", doc.supplier, "custom_delivery_scored_lines") if doc.supplier else 0
	)
	score = (
		_("supplier delivery score {0}% over {1} line(s)").format(round(flt(doc.delivery_score)), scored)
		if scored
		else _("no delivery score yet")
	)
	rows.append({"text": f"{chase}; {score}", "colour": "blue"})
	return rows


@frappe.whitelist()
def get_panel(name=None, purchase_order=None):
	if not name and purchase_order:
		name = tracker_of(purchase_order)
		if not name:
			return None
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	return {"name": doc.name, "rows": panel_rows(doc)}
