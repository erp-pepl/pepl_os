"""C3b-P2 - The NCR panel: where the NCR stands, what it costs, who still signs, its CAPA and what it holds back.

One panel ("NCR") at the top of the PEPL NCR form, in this order:
  "Major NCR, Under Review · In-Process · raised 08-11-2026 (10 days ago) by the system (QA-NCR-RATE)"
  "What: 12 Nos of PIN-10 · batch H-221 · Burr: burr on the chamfer"
  "From: Job Order MFG-WO-0001 · machine MILL-01 · rejection 8% on 07-11-2026 (8 of 100 pieces)"
  "Disposition: Scrap · cost not entered yet (about 120.00 at the item's valuation rate)"      orange
  "Signed: Quality Manager by qm@... on 09-11-2026" / "Still to sign: Manufacturing Manager"    green / orange
  "CAPA CAPA-2026-00003: Open · target 10-12-2026 · five-why: 2 of 5 whys answered; ..."       orange (red overdue)
  "Dispatch: PIN-10 (batch H-221) needs a reason at dispatch until this NCR is closed (gate: Soft Block)"
  "To close: choose the disposition · still to sign: Manufacturing Manager"  /  "Ready to close: ..."  /
  "Closed on 12-11-2026 by qm@..."  /  "Cancelled: raised against the wrong item"
The "Sign off" button stays (shown to a user who holds a role still to sign).
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, fmt_money, formatdate, getdate, today

from pepl_os.pepl_production.job_order_panel import qty_text
from pepl_os.pepl_quality import capa, dispatch, ncr

COSTED = ("Rework", "Scrap", "Return to Supplier", "Regrade")


def _currency():
	company = frappe.defaults.get_global_default("company")
	return (company and frappe.get_cached_value("Company", company, "default_currency")) or None


def money(value):
	return fmt_money(flt(value), currency=_currency())


def age_text(raised_on, as_of=None):
	if not raised_on:
		return _("raise date not set")
	days = date_diff(as_of or today(), raised_on)
	if days <= 0:
		return _("raised today")
	return _("raised {0} ({1} day(s) ago)").format(formatdate(raised_on), days)


def is_open(doc):
	return doc.status in (ncr.OPEN, ncr.UNDER_REVIEW)


def header_row(doc):
	text = _("{0} NCR, {1} · {2} · {3}").format(
		_(doc.severity), _(doc.status), _(doc.source or _("no source")), age_text(doc.raised_on)
	)
	if cint(doc.raised_by_system):
		text += _(" by the system ({0})").format(doc.raise_rule or "")
	if doc.status == ncr.CLOSED:
		colour = "green"
	elif doc.status == ncr.CANCELLED:
		colour = "gray"
	else:
		colour = "red" if doc.severity == ncr.CRITICAL else "orange"
	return {"text": text, "colour": colour}


def what_row(doc):
	uom = frappe.db.get_value("Item", doc.item, "stock_uom") if doc.item else ""
	if flt(doc.qty_affected) > 0:
		qty = f"{qty_text(doc.qty_affected)} {uom or ''}".strip() + " " + _("of") + " "
		colour = "gray"
	else:
		qty = _("quantity not entered") + " · "
		colour = "orange"
	text = _("What: {0}{1}").format(qty, doc.item or _("no item"))
	if doc.batch_no:
		text += " · " + _("batch {0}").format(doc.batch_no)
	defect = ": ".join(
		p for p in ((doc.defect_type or "").strip(), (doc.defect_description or "").strip()) if p
	)
	if defect:
		text += " · " + defect[:160]
	return {"text": text, "colour": colour}


def from_row(doc):
	parts = []
	if doc.quality_inspection:
		parts.append(_("QC Inspection {0}").format(doc.quality_inspection))
	if doc.purchase_receipt:
		parts.append(_("receipt {0}").format(doc.purchase_receipt))
	if doc.supplier:
		parts.append(_("supplier {0}").format(doc.supplier))
	if doc.delivery_note:
		parts.append(_("Delivery Note {0}").format(doc.delivery_note))
	if doc.against_delivery_note:
		parts.append(_("returned against {0}").format(doc.against_delivery_note))
	if doc.customer:
		parts.append(_("customer {0}").format(doc.customer))
	if doc.sales_order:
		parts.append(_("Sales Order {0}").format(doc.sales_order))
	if doc.work_order:
		parts.append(_("Job Order {0}").format(doc.work_order))
	if doc.workstation:
		parts.append(_("machine {0}").format(doc.workstation))
	if flt(doc.pieces_made):
		parts.append(
			_("rejection {0}% on {1} ({2} of {3} pieces)").format(
				qty_text(round(flt(doc.rejection_rate), 2)),
				formatdate(doc.rate_date) if doc.rate_date else "-",
				qty_text(doc.pieces_rejected),
				qty_text(doc.pieces_made),
			)
		)
	if not parts:
		return {"text": _("From: not linked to any document"), "colour": "gray"}
	return {"text": _("From: {0}").format(" · ".join(parts)), "colour": "gray"}


def suggested_cost(doc):
	"""Quantity affected x the item's valuation rate (a hint for the cost, never written to the NCR)."""
	if not doc.item or flt(doc.qty_affected) <= 0:
		return 0
	return flt(doc.qty_affected) * flt(frappe.db.get_value("Item", doc.item, "valuation_rate"))


def disposition_row(doc):
	if not doc.disposition:
		return {"text": _("Disposition: not chosen yet"), "colour": "orange"}
	text = _("Disposition: {0}").format(_(doc.disposition))
	if flt(doc.estimated_cost) > 0:
		return {"text": text + " · " + _("cost {0}").format(money(doc.estimated_cost)), "colour": "gray"}
	if doc.disposition in COSTED:
		hint = suggested_cost(doc)
		text += " · " + _("cost not entered yet")
		if hint:
			text += " " + _("(about {0} at the item's valuation rate)").format(money(hint))
		return {"text": text, "colour": "orange"}
	return {"text": text + " · " + _("no cost"), "colour": "gray"}


def signoff_rows(doc):
	rows = [
		{
			"text": _("Signed: {0} by {1} on {2}").format(
				r.role, r.user, formatdate(getdate(r.signed_on)) if r.signed_on else "-"
			),
			"colour": "green",
		}
		for r in doc.get("sign_offs") or []
	]
	if doc.status != ncr.CANCELLED:
		rows += [
			{"text": _("Still to sign: {0}").format(role), "colour": "orange"}
			for role in ncr.missing_signatures(doc)
		]
	return rows


def capa_row(doc):
	if doc.capa:
		c = frappe.get_doc(capa.CAPA, doc.capa)
		if c.status == capa.CLOSED:
			return {
				"text": _("CAPA {0}: Closed on {1}").format(
					c.name, formatdate(getdate(c.closed_on)) if c.closed_on else "-"
				),
				"colour": "green",
			}
		if c.status == capa.CANCELLED:
			return {"text": _("CAPA {0}: Cancelled").format(c.name), "colour": "gray"}
		text = _("CAPA {0}: {1}").format(c.name, _(c.status))
		late = c.target_date and date_diff(today(), c.target_date) > 0
		if c.target_date:
			text += " · " + _("target {0}").format(formatdate(c.target_date))
			if late:
				text += " " + _("- OVERDUE by {0} day(s)").format(date_diff(today(), c.target_date))
		gaps = capa.closing_gaps(c)
		text += " · " + ("; ".join(gaps) if gaps else _("ready to close"))
		return {"text": text, "colour": "red" if late else "orange"}
	if doc.status == ncr.CANCELLED:
		return None
	if doc.severity == ncr.MINOR:
		return {"text": _("CAPA: not needed for a Minor NCR"), "colour": "gray"}
	if doc.severity == ncr.CRITICAL:
		return {"text": _("CAPA: none linked yet (a Critical NCR raises one)"), "colour": "orange"}
	group = [n for n in capa.repeat_majors(doc) if n.name]
	return {
		"text": _(
			"CAPA: none yet · {0} of {1} Major / Critical NCRs on {2} within {3} days raise one"
		).format(len(group), capa.setting(capa.COUNT_FIELD), doc.item, capa.setting(capa.WINDOW_FIELD)),
		"colour": "gray",
	}


def dispatch_row(doc):
	if not is_open(doc) or not doc.item:
		return None
	what = doc.item + (" " + _("(batch {0})").format(doc.batch_no) if doc.batch_no else "")
	mode = dispatch.gate_mode()
	effect = {
		dispatch.ADVISORY: _("gets a warning at dispatch"),
		dispatch.SOFT_BLOCK: _("needs a reason at dispatch"),
		dispatch.HARD_BLOCK: _("cannot be dispatched"),
	}.get(mode, _("is checked at dispatch"))
	return {
		"text": _("Dispatch: {0} {1} until this NCR is closed (gate: {2})").format(what, effect, _(mode)),
		"colour": "gray" if mode == dispatch.ADVISORY else "orange",
	}


def closing_row(doc):
	if doc.status == ncr.CLOSED:
		when = formatdate(getdate(doc.closed_on)) if doc.closed_on else "-"
		return {"text": _("Closed on {0} by {1}").format(when, doc.closed_by or "-"), "colour": "green"}
	if doc.status == ncr.CANCELLED:
		return {
			"text": _("Cancelled: {0}").format((doc.cancel_reason or "").strip() or "-"),
			"colour": "gray",
		}
	gaps = []
	if not doc.disposition:
		gaps.append(_("choose the disposition"))
	missing = ncr.missing_signatures(doc)
	if missing:
		gaps.append(_("still to sign: {0}").format(", ".join(missing)))
	if gaps:
		return {"text": _("To close: {0}").format(" · ".join(gaps)), "colour": "orange"}
	return {"text": _("Ready to close: set the Status to Closed and save"), "colour": "green"}


def panel_rows(doc):
	rows = [header_row(doc), what_row(doc), from_row(doc)]
	if doc.status != ncr.CANCELLED:
		rows.append(disposition_row(doc))
	rows += signoff_rows(doc)
	rows += [r for r in (capa_row(doc), dispatch_row(doc)) if r]
	rows.append(closing_row(doc))
	return rows


@frappe.whitelist()
def get_ncr_panel(name):
	"""Rows for the "NCR" panel, and whether this user can sign now."""
	doc = frappe.get_doc(ncr.NCR, name)
	doc.check_permission("read")
	mine = set(frappe.get_roles())
	return {
		"rows": panel_rows(doc),
		"can_sign": is_open(doc) and any(r in mine for r in ncr.missing_signatures(doc)),
	}
