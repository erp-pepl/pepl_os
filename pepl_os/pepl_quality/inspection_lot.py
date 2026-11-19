"""C3b-B1 - Inspection-lot management: lot request -> proof schedule -> bulk lot offer -> the agency's IC.

For orders inspected by an outside agency (RITES, RDSO, DGQA / AHQ, the consignee), every lot of a Sales Order line is
one PEPL Inspection Lot. Its status follows what has been recorded (never typed):
  Draft -> Lot Requested (lot number asked for) -> Proof Scheduled -> Proof Passed / Proof Failed (when a proof /
  prototype inspection is required) -> Offered (bulk lot offered) -> Inspected (IC with accepted quantity) or
  Rejected (nothing accepted); Cancelled (with a reason).
Rules:
  * the item must be on the order; the lots of an order line together cannot exceed its ordered quantity;
  * a step needs the one before it: proof results need a proof date; the offer needs the proof Passed (when
    required), at most the lot size, and - for an item inspected before delivery - PEPL's own final inspection
    submitted and Accepted; the IC needs the offer: accepted + rejected = offered, and an IC number and date when
    anything was accepted;
  * once Inspected or Rejected, the quantities and the IC are locked;
  * the letters (lot request, proof schedule request, bulk lot offer) are the PEPL Generated Documents of the order's
    document tracker; the lot links to them.
A rejected quantity raises an NCR (QA-NCR-LOT, source Dispatch) for the lot; it never stops the lot.
The dispatch gate (C3b-Q5) counts the IC: a Delivery Note line of an order that needs agency inspection may only
ship what the ICs of its order line accepted, less what was already delivered.
"""

import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate

from pepl_os.pepl_production.job_order_panel import qty_text
from pepl_os.pepl_quality import dispatch, ncr

LOT = "PEPL Inspection Lot"
QI = "Quality Inspection"
TENDER = "PEPL Tender"
RULE = "QA-NCR-LOT"
DRAFT, REQUESTED, PROOF_SCHEDULED, PROOF_PASSED, PROOF_FAILED = (
	"Draft",
	"Lot Requested",
	"Proof Scheduled",
	"Proof Passed",
	"Proof Failed",
)
OFFERED, INSPECTED, REJECTED, CANCELLED = "Offered", "Inspected", "Rejected", "Cancelled"
DONE = (INSPECTED, REJECTED)
LOCKED = (
	"sales_order",
	"item",
	"lot_qty",
	"offered_qty",
	"accepted_qty",
	"rejected_qty",
	"ic_number",
	"ic_date",
)


def status_of(doc):
	if doc.get("cancelled"):
		return CANCELLED
	if doc.get("inspected_on"):
		return INSPECTED if flt(doc.accepted_qty) > 0 else REJECTED
	if doc.get("offered_on"):
		return OFFERED
	if doc.get("proof_required") and doc.get("proof_result") == "Passed":
		return PROOF_PASSED
	if doc.get("proof_required") and doc.get("proof_result") == "Failed":
		return PROOF_FAILED
	if doc.get("proof_required") and doc.get("proof_scheduled_on"):
		return PROOF_SCHEDULED
	if doc.get("requested_on"):
		return REQUESTED
	return DRAFT


def order_line_qty(sales_order, item):
	return flt(
		frappe.db.sql(
			"""select sum(stock_qty) from `tabSales Order Item` where parent = %s and item_code = %s""",
			(sales_order, item),
		)[0][0]
	)


def tender_of(sales_order):
	name = frappe.db.get_value("Sales Order", sales_order, "custom_tender_reference") if sales_order else None
	return name if name and frappe.db.exists(TENDER, name) else None


def tender_needs_inspection(sales_order):
	tender = tender_of(sales_order)
	return bool(tender) and frappe.db.get_value(TENDER, tender, "inspection_status") == "Yes"


def lots_of(sales_order, item, exclude=None):
	filters = {"sales_order": sales_order, "item": item, "cancelled": 0}
	if exclude:
		filters["name"] = ["!=", exclude]
	return frappe.get_all(
		LOT,
		filters=filters,
		fields=["name", "status", "lot_qty", "offered_qty", "accepted_qty", "rejected_qty", "ic_number"],
		order_by="creation asc",
	)


def validate_lot(doc):
	"""PEPL Inspection Lot validate."""
	before = None if doc.is_new() else doc.get_doc_before_save()
	if before and before.status in DONE and not doc.cancelled:
		changed = [f for f in LOCKED if cstr(before.get(f)) != cstr(doc.get(f))]
		if changed or not doc.get("inspected_on"):
			frappe.throw(
				_("An inspected lot is locked (quantities and IC). Cancel it with a reason if it is wrong.")
			)
	if before and before.cancelled and not doc.cancelled:
		frappe.throw(_("A cancelled lot stays cancelled. Make a new one."))
	if doc.sales_order and doc.item:
		ordered = order_line_qty(doc.sales_order, doc.item)
		if not ordered:
			frappe.throw(_("{0} is not on Sales Order {1}.").format(doc.item, doc.sales_order))
		doc.so_qty = ordered
		if not doc.cancelled:
			others = sum(flt(r.lot_qty) for r in lots_of(doc.sales_order, doc.item, exclude=doc.name))
			if flt(doc.lot_qty) <= 0:
				frappe.throw(_("Enter the lot size."))
			if others + flt(doc.lot_qty) > ordered + 1e-9:
				frappe.throw(
					_("Lots of {0} on {1} would come to {2}, more than the {3} ordered.").format(
						doc.item, doc.sales_order, qty_text(others + flt(doc.lot_qty)), qty_text(ordered)
					)
				)
	if doc.sales_order and not doc.inspection_agency:
		tender = tender_of(doc.sales_order)
		if tender:
			values = frappe.db.get_value(
				TENDER, tender, ["inspection_authority", "inspection_type"], as_dict=True
			)
			doc.inspection_agency = values.inspection_authority
			doc.inspection_type = doc.inspection_type or values.inspection_type
	_check_steps(doc)
	if doc.cancelled and len((doc.cancel_reason or "").strip()) < 10:
		frappe.throw(_("Give the reason for cancelling the lot (at least 10 characters)."))
	doc.status = status_of(doc)


def _check_steps(doc):
	if doc.get("proof_result") and not doc.get("proof_scheduled_on"):
		frappe.throw(_("Enter the date the proof inspection was scheduled before its result."))
	if not doc.get("offered_on"):
		if doc.get("inspected_on"):
			frappe.throw(_("The agency inspects an offered lot: enter the offer first."))
		return
	if doc.get("proof_required") and doc.get("proof_result") != "Passed":
		frappe.throw(_("The bulk lot can be offered once the proof inspection has Passed."))
	if flt(doc.offered_qty) <= 0 or flt(doc.offered_qty) > flt(doc.lot_qty) + 1e-9:
		frappe.throw(
			_("Quantity Offered must be more than 0 and at most the lot size ({0}).").format(
				qty_text(doc.lot_qty)
			)
		)
	if doc.get("requested_on") and getdate(doc.offered_on) < getdate(doc.requested_on):
		frappe.throw(_("The lot cannot be offered before its lot number was requested."))
	if dispatch.needs_final_inspection(doc.item):
		qi = doc.get("internal_inspection")
		values = qi and frappe.db.get_value(QI, qi, ["docstatus", "status", "item_code"], as_dict=True)
		if not values or values.docstatus != 1 or values.status != "Accepted" or values.item_code != doc.item:
			frappe.throw(
				_(
					"{0} is inspected before delivery: name PEPL's own final inspection of the lot (submitted and "
					"Accepted) before offering it to the agency."
				).format(doc.item)
			)
	if not doc.get("inspected_on"):
		return
	if getdate(doc.inspected_on) < getdate(doc.offered_on):
		frappe.throw(_("The lot cannot be inspected before it was offered."))
	if abs(flt(doc.accepted_qty) + flt(doc.rejected_qty) - flt(doc.offered_qty)) > 1e-9:
		frappe.throw(
			_("Accepted + Rejected must equal the quantity offered ({0}).").format(qty_text(doc.offered_qty))
		)
	if flt(doc.accepted_qty) > 0 and not ((doc.ic_number or "").strip() and doc.ic_date):
		frappe.throw(_("Enter the IC / Inspection Note number and date for the accepted quantity."))


def on_update_lot(doc):
	"""A rejected quantity raises an NCR for the lot (once); cancelling the lot takes back an unsigned one."""
	frappe.db.savepoint("pepl_lot_ncr")
	try:
		if doc.status in DONE and flt(doc.rejected_qty) > 0 and not doc.ncr:
			name = ncr.raise_ncr(
				RULE,
				{"inspection_lot": doc.name},
				{
					"source": ncr.DISPATCH,
					"item": doc.item,
					"qty_affected": flt(doc.rejected_qty),
					"sales_order": doc.sales_order,
					"customer": doc.customer,
					"defect_type": _("Rejected by {0}").format(doc.inspection_agency or _("the agency")),
					"defect_description": _(
						"{0} of {1} offered in lot {2} rejected at inspection on {3}. {4}"
					).format(
						qty_text(doc.rejected_qty),
						qty_text(doc.offered_qty),
						doc.lot_no or doc.name,
						frappe.utils.formatdate(doc.inspected_on),
						(doc.remarks or "").strip(),
					)[:1000],
				},
			)
			doc.db_set("ncr", name, update_modified=False)
		elif doc.status == CANCELLED and doc.ncr:
			ncr.cancel_auto(
				RULE, {"inspection_lot": doc.name}, _("Inspection lot {0} cancelled").format(doc.name)
			)
	except Exception:
		frappe.db.rollback(save_point="pepl_lot_ncr")
		frappe.log_error(title=f"PEPL: NCR for inspection lot {doc.name} not raised")
	return None


# The dispatch gate (C3b-Q5) -------------------------------------------------------------------------------------


def needs_agency_inspection(sales_order, item):
	"""An order line is inspected by an agency when its tender says so or it has an inspection lot."""
	if not sales_order:
		return False
	return bool(lots_of(sales_order, item)) or tender_needs_inspection(sales_order)


def ic_accepted(sales_order, item):
	return sum(flt(r.accepted_qty) for r in lots_of(sales_order, item) if r.status == INSPECTED)


def delivered_before(sales_order, item, delivery_note):
	"""Stock quantity of the order line on submitted Delivery Notes (not returns), this one left out."""
	return flt(
		frappe.db.sql(
			"""select sum(i.stock_qty) from `tabDelivery Note Item` i join `tabDelivery Note` d on d.name = i.parent
			where d.docstatus = 1 and d.is_return = 0 and d.name != %s and i.against_sales_order = %s
				and i.item_code = %s""",
			(delivery_note or "", sales_order, item),
		)[0][0]
	)


def ic_gaps(doc):
	"""[(row, what is wrong)] for Delivery Note lines shipping more than the agency's ICs accepted."""
	gaps = []
	asked = {}
	for row in doc.items:
		so = row.get("against_sales_order")
		if not so or not needs_agency_inspection(so, row.item_code):
			continue
		key = (so, row.item_code)
		asked[key] = asked.get(key, 0) + flt(row.get("stock_qty") or row.qty)
		cleared = ic_accepted(so, row.item_code)
		shipped = delivered_before(so, row.item_code, doc.name)
		if shipped + asked[key] > cleared + 1e-9:
			if not cleared:
				what = _("needs the agency's inspection ({0}): no IC yet").format(
					frappe.db.get_value(LOT, {"sales_order": so, "item": row.item_code}, "inspection_agency")
					or _("tender: inspection required")
				)
			else:
				what = _(
					"ICs of {0} accepted {1}, {2} already delivered; this delivery would make {3}"
				).format(so, qty_text(cleared), qty_text(shipped), qty_text(shipped + asked[key]))
			gaps.append((row, what))
	return gaps


# Panel -------------------------------------------------------------------------------------------------------------


@frappe.whitelist()
def get_lot_panel(name):
	"""Rows for the "Inspection Lot" panel: the steps, the order line, what comes next."""
	doc = frappe.get_doc(LOT, name)
	doc.check_permission("read")
	unit = doc.stock_uom or ""
	rows = [
		{
			"text": _("Lot {0} of {1}: {2} · {3} ({4} {5} ordered) · agency {6}").format(
				doc.lot_no or doc.name,
				doc.item,
				_(doc.status),
				doc.sales_order,
				qty_text(doc.so_qty),
				unit,
				doc.inspection_agency or _("not set"),
			),
			"colour": {INSPECTED: "green", REJECTED: "red", CANCELLED: "gray", PROOF_FAILED: "red"}.get(
				doc.status, "orange"
			),
		}
	]

	def step(done, text, colour_done="green", colour_todo="gray"):
		rows.append({"text": ("✓ " if done else "· ") + text, "colour": colour_done if done else colour_todo})

	step(
		bool(doc.requested_on),
		_("Lot request: {0} {1}{2}").format(
			qty_text(doc.lot_qty),
			unit,
			_(", lot no. {0}").format(doc.lot_no) if doc.lot_no else "",
		)
		+ (
			_(" · requested {0}").format(frappe.utils.formatdate(doc.requested_on))
			if doc.requested_on
			else ""
		),
	)
	if doc.proof_required:
		text = _("Proof inspection")
		if doc.proof_scheduled_on:
			text += _(" scheduled {0}").format(frappe.utils.formatdate(doc.proof_scheduled_on))
		if doc.proof_result:
			text += " · " + _(doc.proof_result)
		step(
			doc.proof_result == "Passed",
			text,
			colour_todo="red"
			if doc.proof_result == "Failed"
			else "orange"
			if doc.proof_scheduled_on
			else "gray",
		)
	step(
		bool(doc.offered_on),
		_("Bulk lot offer")
		+ (
			_(": {0} {1} on {2}").format(
				qty_text(doc.offered_qty), unit, frappe.utils.formatdate(doc.offered_on)
			)
			if doc.offered_on
			else ""
		),
	)
	if doc.inspected_on:
		step(
			flt(doc.accepted_qty) > 0,
			_("Inspected {0}: accepted {1}, rejected {2}{3}").format(
				frappe.utils.formatdate(doc.inspected_on),
				qty_text(doc.accepted_qty),
				qty_text(doc.rejected_qty),
				_(" · IC {0} of {1}").format(doc.ic_number, frappe.utils.formatdate(doc.ic_date))
				if doc.ic_number
				else "",
			),
			colour_todo="red",
		)
		if doc.ncr:
			rows.append({"text": _("Rejected quantity: NCR {0}").format(doc.ncr), "colour": "red"})
	else:
		step(False, _("Inspection by the agency and IC"))
	lots = lots_of(doc.sales_order, doc.item)
	cleared = sum(flt(r.accepted_qty) for r in lots if r.status == INSPECTED)
	rows.append(
		{
			"text": _(
				"Order line: {0} lot(s) for {1} of {2} ordered · IC accepted {3} · delivered {4}"
			).format(
				len(lots),
				qty_text(sum(flt(r.lot_qty) for r in lots)),
				qty_text(doc.so_qty),
				qty_text(cleared),
				qty_text(delivered_before(doc.sales_order, doc.item, None)),
			),
			"colour": "gray",
		}
	)
	nxt = {
		DRAFT: _("Next: request the lot number (enter Lot Number Requested On)"),
		REQUESTED: _("Next: schedule the proof inspection")
		if doc.proof_required
		else _("Next: offer the bulk lot (Offered On, Quantity Offered)"),
		PROOF_SCHEDULED: _("Next: enter the proof result"),
		PROOF_FAILED: _("Proof failed: correct the item and schedule a new proof (or cancel the lot)"),
		PROOF_PASSED: _("Next: offer the bulk lot"),
		OFFERED: _("Next: enter the agency's inspection: accepted, rejected, IC number and date"),
	}.get(doc.status)
	if nxt:
		rows.append({"text": nxt, "colour": "red" if doc.status == PROOF_FAILED else "orange"})
	if doc.status == CANCELLED:
		rows.append({"text": _("Cancelled: {0}").format(doc.cancel_reason or "-"), "colour": "gray"})
	return rows


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def order_items(doctype, txt, searchfield, start, page_len, filters):
	"""Link search for the lot's Item: only the items of its Sales Order."""
	sales_order = (filters or {}).get("sales_order")
	if not sales_order:
		return []
	return frappe.db.sql(
		"""select distinct item_code, item_name from `tabSales Order Item`
		where parent = %s and (item_code like %s or item_name like %s) order by idx limit %s offset %s""",
		(sales_order, f"%{txt}%", f"%{txt}%", int(page_len), int(start)),
	)
