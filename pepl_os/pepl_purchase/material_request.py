"""C2-07 - A submitted Sales Order drafts its Material Request for bought-out and short raw material.

One draft Material Request (type Purchase) per Sales Order, never two. Lines:
  * Bought-Out Components: the full ordered quantity (bought against this order).
  * Raw Material: only the shortfall in its default store, where
        shortfall = needed - (on hand - reserved + on order + already requested)
    i.e. the part that neither stock nor open orders nor open requests will cover.
  * Everything else (made in-house, consumables, ...) is left out.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from pepl_os.pepl_stores import stock_tree
from pepl_os.pepl_stores.defaults import bin_quantities, default_store

MR_LINK_FIELD = "custom_sales_order"


def _shortfall(item_code, warehouse, needed, same_store_reserved=0):
	"""Quantity not covered by stock, open POs or open requests.

	`same_store_reserved` is this Sales Order's own reservation in that store,
	which ERPNext has already added to reserved_qty when our hook runs.
	"""
	b = bin_quantities(item_code, warehouse)
	available = (
		flt(b.actual_qty)
		- (flt(b.reserved_qty) - flt(same_store_reserved))
		+ flt(b.ordered_qty)
		+ flt(b.indented_qty)
	)
	return max(0.0, flt(needed) - max(0.0, available))


def existing_request(sales_order):
	return frappe.db.get_value(
		"Material Request", {MR_LINK_FIELD: sales_order, "docstatus": ["<", 2]}, "name"
	)


def lines_to_request(so):
	"""[(so_item_row, qty_in_stock_uom, warehouse)] for the lines Purchase must buy."""
	lines = []
	for row in so.items:
		stock_class = stock_tree.stock_class_of(frappe.get_cached_value("Item", row.item_code, "item_group"))
		if stock_class not in (stock_tree.BOUGHT_OUT, stock_tree.RAW_MATERIAL):
			continue
		warehouse = default_store(row.item_code, so.company) or row.warehouse
		needed = flt(row.stock_qty) or flt(row.qty) * flt(row.conversion_factor or 1)
		if stock_class == stock_tree.RAW_MATERIAL:
			own = needed if (so.docstatus == 1 and row.warehouse == warehouse) else 0
			needed = _shortfall(row.item_code, warehouse, needed, same_store_reserved=own)
		if needed > 0:
			lines.append((row, needed, warehouse))
	return lines


def draft_material_request(so):
	"""Create the draft Material Request for this Sales Order. Returns its name, or None."""
	if existing := existing_request(so.name):
		return existing
	lines = lines_to_request(so)
	if not lines:
		return None
	required_by = max(getdate(so.delivery_date or today()), getdate(today()))
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": so.company,
			"transaction_date": today(),
			"schedule_date": required_by,
			MR_LINK_FIELD: so.name,
			"items": [
				{
					"item_code": row.item_code,
					"qty": qty,
					"uom": frappe.get_cached_value("Item", row.item_code, "stock_uom"),
					"conversion_factor": 1,
					"schedule_date": max(getdate(row.delivery_date or required_by), getdate(today())),
					"warehouse": warehouse,
					"sales_order": so.name,
					"sales_order_item": row.name,
				}
				for row, qty, warehouse in lines
			],
		}
	)
	mr.flags.ignore_permissions = True  # the Sales user who submits the order may not create requests
	mr.insert()
	return mr.name


def on_sales_order_submit(doc, method=None):
	"""doc_events: Sales Order on_submit (runs after pepl_sales' own handler)."""
	try:
		name = draft_material_request(doc)
	except Exception:
		# Never block the Sales Order; Purchase is told instead.
		frappe.log_error(title=f"PEPL: Material Request draft failed for {doc.name}")
		frappe.msgprint(
			_("The Material Request for bought-out items could not be drafted. Purchase has been notified."),
			indicator="orange",
			alert=True,
		)
		from pepl_os.common import alerts

		alerts.raise_todo(
			"PUR-MR-DRAFT-FAILED",
			"Sales Order",
			doc.name,
			f"Material Request for Sales Order {doc.name} could not be drafted automatically. "
			"Raise it by hand and check the Error Log.",
			owner_field="custom_purchase_notification_owner",
			priority="High",
		)
		return
	if name:
		frappe.msgprint(
			_("Draft Material Request {0} created for the bought-out and short raw-material lines.").format(
				frappe.bold(name)
			),
			indicator="green",
			alert=True,
		)


# MR helper panel -----------------------------------------------------------


def rm_group_of(item_code):
	group = frappe.get_cached_value("Item", item_code, "item_group")
	return frappe.db.get_value("PEPL RM Group", {"linked_item_group": group}, "name") if group else None


def approved_supplier_count(rm_group):
	if not rm_group:
		return 0
	return len(
		frappe.get_all(
			"Supplier",
			filters={
				"disabled": 0,
				"custom_approval_state": ["in", ["Approved", "Conditionally Approved"]],
				"name": [
					"in",
					frappe.get_all(
						"PEPL Supplier RM Group",
						filters={"parenttype": "Supplier", "rm_group": rm_group},
						pluck="parent",
					)
					or [""],
				],
			},
			pluck="name",
		)
	)


def requested_elsewhere(item_code, material_request):
	rows = frappe.get_all(
		"Material Request Item",
		filters={"item_code": item_code, "parent": ["!=", material_request or ""], "docstatus": ["<", 2]},
		fields=["parent", "stock_qty", "ordered_qty"],
	)
	open_parents = set(
		frappe.get_all(
			"Material Request",
			filters={
				"name": ["in", [r.parent for r in rows] or [""]],
				"docstatus": ["<", 2],
				"status": ["not in", ["Stopped", "Cancelled", "Ordered", "Received"]],
			},
			pluck="name",
		)
	)
	return sum(flt(r.stock_qty) - flt(r.ordered_qty) for r in rows if r.parent in open_parents)


@frappe.whitelist()
def get_mr_panel(material_request):
	"""Per line: on hand, on order, requested in other open requests, approved suppliers."""
	mr = frappe.get_doc("Material Request", material_request)
	mr.check_permission("read")
	lines = []
	for row in mr.items:
		warehouse = row.warehouse or default_store(row.item_code, mr.company)
		b = bin_quantities(row.item_code, warehouse) if warehouse else bin_quantities(row.item_code, "")
		rm_group = rm_group_of(row.item_code)
		lines.append(
			{
				"idx": row.idx,
				"item_code": row.item_code,
				"warehouse": warehouse,
				"on_hand": flt(b.actual_qty),
				"on_order": flt(b.ordered_qty),
				"requested_elsewhere": requested_elsewhere(row.item_code, mr.name),
				"rm_group": rm_group,
				"approved_suppliers": approved_supplier_count(rm_group),
			}
		)
	return lines
