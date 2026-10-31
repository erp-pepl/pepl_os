"""C3a-B5 - LD-exposure report: what late delivery costs on every open Sales Order, today and if nothing more is
delivered in the next days.

Built on the order's own LD clause and ld.exposure (C3a-X11): late days (after the line's delivery date and the
grace days) x the contractual rate (per week or per day, a part counted as a whole), capped as the clause says.
- Open orders: submitted, not fully delivered, not Completed / Closed.
- LD so far: as on the chosen date (delivered-late quantities and quantities still pending and late).
- LD in N days: the same if nothing more is delivered by then (N = "LD: Look-Ahead Days", System Parameters).
  "Starts within N days" = no LD yet, but a pending line becomes late in that time.
- Red: LD already running. Orange: LD starts within the look-ahead. Green: on time. Grey: no LD clause (shown
  only when "Only orders with LD terms" is unticked).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from pepl_os.common import params
from pepl_os.pepl_production import ld
from pepl_os.pepl_production.job_order_panel import qty_text

LOOK_AHEAD_FIELD = "custom_ld_look_ahead_days"
DEFAULT_LOOK_AHEAD = 7
CLOSED = ("Completed", "Closed", "Cancelled", "Draft")


def look_ahead_days():
	value = params.get(LOOK_AHEAD_FIELD, DEFAULT_LOOK_AHEAD)
	return cint(value) if value not in (None, "") and cint(value) >= 0 else DEFAULT_LOOK_AHEAD


def _orders(filters):
	conditions = {"docstatus": 1, "status": ["not in", CLOSED], "per_delivered": ["<", 100]}
	for key in ("company", "customer"):
		if filters.get(key):
			conditions[key] = filters[key]
	if filters.get("sales_order"):
		conditions["name"] = filters["sales_order"]
	if filters.get("sector") and frappe.db.has_column("Sales Order", "custom_sector"):
		conditions["custom_sector"] = filters["sector"]
	if cint(filters.get("only_ld", 1)):
		conditions[ld.APPLICABLE] = 1
	fields = ["name", "customer", "customer_name", "base_net_total", "delivery_date", ld.APPLICABLE]
	if frappe.db.has_column("Sales Order", "custom_sector"):
		fields.append("custom_sector")
	return frappe.get_all("Sales Order", filters=conditions, fields=fields, order_by="delivery_date, name")


def state(now_total, ahead_total):
	if now_total > 0:
		return "red"
	if ahead_total > 0:
		return "orange"
	return "green"


def order_rows(filters=None):
	"""(order rows, line rows) as on the date, with the look-ahead."""
	filters = frappe._dict(filters or {})
	as_on = getdate(filters.get("as_on") or today())
	days = look_ahead_days()
	ahead_on = add_days(as_on, days)
	orders, lines = [], []
	for so in _orders(filters):
		doc = frappe.get_doc("Sales Order", so.name)
		now = ld.exposure(doc, as_on)
		later = ld.exposure(doc, ahead_on)
		terms = now["terms"]
		applies = bool(terms["applicable"] and terms["rate"])
		ahead_by_line = {line.so_detail: line for line in later["lines"]}
		late_lines = [line for line in now["lines"] if line.late_qty]
		colour = state(now["total"], later["total"]) if applies else "gray"
		cap_used = round(100.0 * now["total"] / now["cap_amount"], 1) if now["cap_amount"] else 0
		orders.append(
			{
				"sales_order": so.name,
				"customer": so.customer,
				"customer_name": so.customer_name,
				"sector": so.get("custom_sector") or "",
				"order_value": flt(so.base_net_total),
				"terms": _("{0}% per {1}, cap {2}%{3}").format(
					qty_text(terms["rate"]),
					_(terms["period"]).lower(),
					qty_text(terms["cap"]),
					(", " + _("{0} grace days").format(terms["grace"])) if terms["grace"] else "",
				)
				if applies
				else _("no LD clause"),
				"basis": terms["basis"] if applies else "",
				"clause": terms["clause"],
				"days_late": max((line.days_late for line in now["lines"]), default=0),
				"late_lines": len(late_lines),
				"pending_qty": sum(flt(line.pending) for line in now["lines"]),
				"ld_now": now["total"],
				"ld_ahead": later["total"],
				"ld_added": round(later["total"] - now["total"], 2),
				"cap_amount": now["cap_amount"],
				"cap_used": cap_used,
				"colour": colour,
			}
		)
		for line in now["lines"]:
			ahead = ahead_by_line.get(line.so_detail)
			if not (
				line.late_qty
				or (ahead and ahead.late_qty)
				or (line.pending and getdate(line.due) <= ahead_on)
			):
				continue
			lines.append(
				{
					"sales_order": so.name,
					"customer_name": so.customer_name,
					"item_code": line.item_code,
					"due": line.due,
					"qty": line.qty,
					"delivered": line.delivered,
					"pending": line.pending,
					"late_qty": line.late_qty,
					"days_late": line.days_late,
					"ld_now": line.amount,
					"ld_ahead": ahead.amount if ahead else line.amount,
					"uncapped": line.uncapped,
					"colour": "red"
					if line.amount > 0
					else ("orange" if ahead and ahead.amount > 0 else "green"),
				}
			)
	orders.sort(key=lambda r: (-r["ld_now"], -r["ld_ahead"], -r["days_late"], r["sales_order"]))
	lines.sort(key=lambda r: (-r["ld_now"], -r["ld_ahead"], r["sales_order"]))
	return orders, lines


def summary(orders):
	days = look_ahead_days()
	running = [o for o in orders if o["ld_now"] > 0]
	starting = [o for o in orders if o["colour"] == "orange"]
	now_total = sum(o["ld_now"] for o in orders)
	ahead_total = sum(o["ld_ahead"] for o in orders)
	return _(
		"LD so far {0} on {1} order(s); if nothing more is delivered, {2} in {3} days ({4} more order(s) start LD)."
	).format(
		frappe.utils.fmt_money(now_total, currency=frappe.db.get_default("currency")),
		len(running),
		frappe.utils.fmt_money(ahead_total, currency=frappe.db.get_default("currency")),
		days,
		len(starting),
	)
