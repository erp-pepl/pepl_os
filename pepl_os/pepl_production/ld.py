"""C3a-X11 - The contractual Liquidated Damages (LD) terms of a Sales Order, and what late delivery costs.

Each Sales Order carries its LD clause: whether LD applies, the rate (% of the value delivered late) per week or
per day of delay "or part thereof", the cap (% of the value), grace days, whether LD is charged on the value of
the late items or on the whole order, and the clause reference. Railways and Defence orders usually carry the
standard clause, so a new order of a sector listed in System Parameters → Production → "LD: Sectors with LD by
Default" starts with the default rate, period and cap; anything else starts without LD. The terms are fixed once
the order is submitted (amend the order to change them).

LD for a line, as on a date:
- Delivered late: each Delivery Note quantity posted after the line's delivery date + grace days.
- Still pending and late: the undelivered quantity once the delivery date + grace days has passed.
"Value of Late Items" (the usual clause): each late part costs its value x rate x periods late (weeks or days, a
part of a period counted as a whole one), capped per line at the cap % of the value delivered late.
"Whole Order Value": the order value x rate x the most periods any part is late, capped at the cap % of the order. The LD-exposure report (B5) and the panels build on get_ld_exposure.
"""

import math

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, today

from pepl_os.common import params

APPLICABLE = "custom_ld_applicable"
RATE = "custom_ld_rate_percent"
PERIOD = "custom_ld_period"
CAP = "custom_ld_max_percent"
GRACE = "custom_ld_grace_days"
BASIS = "custom_ld_basis"
CLAUSE = "custom_ld_clause"
WEEK, DAY = "Week", "Day"
LATE_ITEMS, WHOLE_ORDER = "Value of Late Items", "Whole Order Value"

DEFAULT_SECTORS_FIELD = "custom_ld_default_sectors"
DEFAULT_RATE_FIELD = "custom_ld_default_rate_percent"
DEFAULT_PERIOD_FIELD = "custom_ld_default_period"
DEFAULT_CAP_FIELD = "custom_ld_default_max_percent"


def default_sectors():
	text = params.get(DEFAULT_SECTORS_FIELD, "Railways\nDefence") or ""
	return {line.strip() for line in text.replace(",", "\n").splitlines() if line.strip()}


def apply_defaults(doc):
	"""A new order of an LD sector starts with the standard clause (only when nothing was entered)."""
	if not doc.is_new() or doc.get(APPLICABLE) or flt(doc.get(RATE)):
		return False
	if (doc.get("custom_sector") or "").strip() not in default_sectors():
		return False
	doc.set(APPLICABLE, 1)
	doc.set(RATE, flt(params.get(DEFAULT_RATE_FIELD, 0.5)))
	doc.set(PERIOD, params.get(DEFAULT_PERIOD_FIELD, WEEK) or WEEK)
	doc.set(CAP, flt(params.get(DEFAULT_CAP_FIELD, 10)))
	doc.set(BASIS, doc.get(BASIS) or LATE_ITEMS)
	return True


def validate_sales_order(doc, method=None):
	"""doc_events: Sales Order validate. Defaults for LD sectors; a complete, sensible clause when LD applies."""
	apply_defaults(doc)
	if not cint(doc.get(APPLICABLE)):
		return
	errors = []
	if not 0 < flt(doc.get(RATE)) <= 100:
		errors.append(_("LD Rate % must be more than 0 and at most 100."))
	if not 0 < flt(doc.get(CAP)) <= 100:
		errors.append(_("LD Cap % must be more than 0 and at most 100."))
	if doc.get(PERIOD) not in (WEEK, DAY):
		errors.append(_("LD per Week or per Day is required."))
	if cint(doc.get(GRACE)) < 0:
		errors.append(_("LD Grace Days cannot be negative."))
	if not doc.get(BASIS):
		doc.set(BASIS, LATE_ITEMS)
	if errors:
		frappe.throw("<br>".join(errors), title=_("Liquidated Damages"))


def periods_late(days, period):
	"""Weeks (or days) late, a part of a week counted as a whole one."""
	if days <= 0:
		return 0
	return math.ceil(days / 7) if period == WEEK else days


def _line_value(row, qty):
	return flt(row.base_net_rate or row.net_rate or row.rate) * flt(qty)


def exposure(so, as_on=None):
	"""LD for every line of a Sales Order as on a date: {lines: [...], total, cap, terms}."""
	so = frappe.get_doc("Sales Order", so) if isinstance(so, str) else so
	as_on = getdate(as_on or today())
	terms = {
		"applicable": cint(so.get(APPLICABLE)),
		"rate": flt(so.get(RATE)),
		"period": so.get(PERIOD) or WEEK,
		"cap": flt(so.get(CAP)),
		"grace": cint(so.get(GRACE)),
		"basis": so.get(BASIS) or LATE_ITEMS,
		"clause": so.get(CLAUSE) or "",
	}
	result = {"terms": terms, "lines": [], "total": 0.0, "cap_amount": 0.0, "as_on": as_on}
	if not terms["applicable"] or not terms["rate"]:
		return result
	rate = terms["rate"] / 100.0
	deliveries = frappe.db.sql(
		"""select i.so_detail, d.posting_date, sum(i.stock_qty / ifnull(nullif(i.conversion_factor, 0), 1)) as qty
		from `tabDelivery Note Item` i join `tabDelivery Note` d on d.name = i.parent
		where d.docstatus = 1 and d.is_return = 0 and i.against_sales_order = %s
		group by i.so_detail, d.posting_date""",
		so.name,
		as_dict=True,
	)
	order_value = flt(so.base_net_total or so.net_total)
	cap = terms["cap"] / 100.0
	worst = 0  # most periods late of any late part (Whole Order Value)
	total = 0.0
	for row in so.items:
		due = getdate(row.delivery_date or so.delivery_date)
		delivered = amount = late_qty = 0.0
		for d in (x for x in deliveries if x.so_detail == row.name):
			delivered += flt(d.qty)
			periods = periods_late(date_diff(d.posting_date, due) - terms["grace"], terms["period"])
			if periods:
				late_qty += flt(d.qty)
				amount += _line_value(row, d.qty) * rate * periods
				worst = max(worst, periods)
		pending = max(flt(row.qty) - delivered, 0)
		late_now = date_diff(as_on, due) - terms["grace"]
		periods = periods_late(late_now, terms["period"]) if pending > 0 else 0
		if periods:
			late_qty += pending
			amount += _line_value(row, pending) * rate * periods
			worst = max(worst, periods)
		line_cap = _line_value(row, late_qty) * cap
		capped = min(amount, line_cap)
		result["lines"].append(
			frappe._dict(
				item_code=row.item_code,
				so_detail=row.name,
				due=due,
				qty=flt(row.qty),
				delivered=delivered,
				pending=pending,
				late_qty=late_qty,
				days_late=max(late_now, 0) if pending > 0 else 0,
				amount=round(capped, 2),
				uncapped=round(amount, 2),
			)
		)
		total += capped
	if terms["basis"] == WHOLE_ORDER:
		total = min(order_value * rate * worst, order_value * cap)
		result["cap_amount"] = round(order_value * cap, 2)
	else:
		result["cap_amount"] = round(sum(_line_value(r, r.qty) for r in so.items) * cap, 2)
	result["total"] = round(total, 2)
	result["late_lines"] = sum(1 for line in result["lines"] if line.late_qty)
	return result


@frappe.whitelist()
def get_ld_exposure(sales_order, as_on=None):
	"""For the Sales Order form and the LD-exposure report."""
	frappe.has_permission("Sales Order", "read", doc=sales_order, throw=True)
	return exposure(sales_order, as_on)
