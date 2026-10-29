"""C3a-P4 - The customer-supplied material (CSM) panel on the Job Order: is the customer's material there?

For a Job Order (Work Order) whose BOM uses customer-supplied material, per CSM item:
- this Job Order: CSM a piece (BOM, flattened to the leaf materials) x pieces still to make (quantity - made),
  never more than the whole order still needs (material already issued to the shop floor covers it);
- the whole Sales Order: CSM a piece of each line's BOM x the line quantity, less what is already issued or
  consumed against the order (C2-16 issues, C3a-X9 consumption on delivery) = still needed;
- held: the order's CSM still in the CSM stores (C2-16 balance), and how many pieces it is enough for.

Colour: green when the order holds enough for everything still needed on the order; orange when it is enough for
this Job Order but not for the whole order; red when this Job Order itself cannot be finished from what is held
(short by ...). "CSM Reconciliation Tolerance (kg)" (in the material's stock unit) is allowed either way.
A Job Order using CSM without a Sales Order is red: customer material moves only against its Sales Order.
"""

import math

import frappe
from frappe import _
from frappe.utils import flt

from pepl_os.pepl_production import csm_consumption as cc
from pepl_os.pepl_production.job_order_panel import qty_text
from pepl_os.pepl_stores import csm


def _uom(item_code):
	return frappe.get_cached_value("Item", item_code, "stock_uom") or ""


def _qty(value, item_code):
	return f"{qty_text(value)} {_uom(item_code)}".strip()


def order_needs(sales_order):
	"""{csm item: stock qty} the whole Sales Order needs (each line's BOM x the line quantity)."""
	need = {}
	for row in frappe.get_all(
		"Sales Order Item",
		filters={"parent": sales_order, "parenttype": "Sales Order"},
		fields=["name", "item_code", "stock_qty", "qty"],
	):
		for item, per in cc.csm_per_piece(cc.line_bom(row.item_code, row.name)).items():
			need[item] = need.get(item, 0) + per * flt(row.stock_qty or row.qty)
	return need


def lines(wo):
	"""[{item_code, per_piece, remaining, wo_need, order_need, issued, still_needed, held, scrap, enough_for, state,
	short}] for each CSM item of the Job Order's BOM."""
	wo = frappe.get_doc("Work Order", wo) if isinstance(wo, str) else wo
	per_piece = cc.csm_per_piece(wo.bom_no)
	if not per_piece:
		return []
	remaining = max(flt(wo.qty) - flt(wo.produced_qty), 0)
	tolerance = cc.tolerance()
	balance = (
		{r.item_code: r for r in csm.csm_balance({"sales_order": wo.sales_order})} if wo.sales_order else {}
	)
	needs = order_needs(wo.sales_order) if wo.sales_order else {}
	result = []
	for item in sorted(per_piece):
		per = flt(per_piece[item])
		row = balance.get(item)
		held = max(flt(row.balance), 0) if row else 0.0
		issued = flt(row.issued) if row else 0.0
		wo_need = per * remaining
		order_need = needs.get(item, wo_need)
		still_needed = max(order_need - issued, 0)
		# material already issued to the shop floor for the order covers part of this Job Order too
		wo_still = min(wo_need, still_needed)
		if held + tolerance >= still_needed:
			state = "enough"
		elif held + tolerance >= wo_still:
			state = "enough for this Job Order"
		else:
			state = "short"
		result.append(
			frappe._dict(
				item_code=item,
				per_piece=round(per, 6),
				remaining=remaining,
				wo_need=round(wo_need, 6),
				order_need=round(order_need, 6),
				issued=round(issued, 6),
				still_needed=round(still_needed, 6),
				held=round(held, 6),
				scrap=round(max(flt(row.scrap_on_hand), 0), 6) if row else 0.0,
				enough_for=math.floor(held / per + 1e-9) if per else 0,
				state=state,
				wo_still=round(wo_still, 6),
				short=round(max(wo_still - held, 0), 6),
			)
		)
	return result


COLOUR = {"enough": "green", "enough for this Job Order": "orange", "short": "red"}


def panel_rows(wo):
	wo = frappe.get_doc("Work Order", wo) if isinstance(wo, str) else wo
	items = lines(wo)
	if not items:
		return []
	if not wo.sales_order:
		return [
			{
				"text": _(
					"This Job Order uses customer-supplied material ({0}) but has no Sales Order: the customer's "
					"material moves only against its Sales Order."
				).format(", ".join(i.item_code for i in items)),
				"colour": "red",
			}
		]
	worst = (
		"short"
		if any(i.state == "short" for i in items)
		else ("enough for this Job Order" if any(i.state != "enough" for i in items) else "enough")
	)
	headline = {
		"enough": _("Sales Order {0} holds enough of the customer's material for what is still to make"),
		"enough for this Job Order": _(
			"Sales Order {0} holds enough customer material for this Job Order, not for the whole order"
		),
		"short": _("Sales Order {0} does not hold enough customer material to finish this Job Order"),
	}[worst].format(wo.sales_order)
	rows = [{"text": headline, "colour": COLOUR[worst]}]
	for i in items:
		text = _(
			"{0}: {1} a piece x {2} still to make = {3}; the order holds {4} (enough for {5} pieces)"
		).format(
			i.item_code,
			_qty(i.per_piece, i.item_code),
			qty_text(i.remaining),
			_qty(i.wo_need, i.item_code)
			+ (
				" (" + _("{0} after what is already issued").format(_qty(i.wo_still, i.item_code)) + ")"
				if i.wo_still < i.wo_need - 1e-9
				else ""
			),
			_qty(i.held, i.item_code),
			i.enough_for,
		)
		if i.state == "short":
			text += " - " + _("short by {0}").format(_qty(i.short, i.item_code))
		elif i.state == "enough for this Job Order":
			text += " - " + _("the whole order still needs {0}").format(_qty(i.still_needed, i.item_code))
		extra = []
		if i.issued:
			extra.append(_("issued or consumed so far {0}").format(_qty(i.issued, i.item_code)))
		if i.scrap:
			extra.append(_("in CSM Scrap {0}").format(_qty(i.scrap, i.item_code)))
		if extra:
			text += " (" + "; ".join(extra) + ")"
		rows.append({"text": text, "colour": COLOUR[i.state]})
	return rows


@frappe.whitelist()
def get_job_order_csm_panel(work_order):
	"""For the Job Order form: {rows} (empty when the Job Order uses no customer material)."""
	frappe.has_permission("Work Order", "read", doc=work_order, throw=True)
	return {"rows": panel_rows(work_order)}
