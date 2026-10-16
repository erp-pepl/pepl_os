"""C3a-X5 - A submitted Sales Order drafts its Job Orders (ERPNext Work Orders).

For every manufactured line (stock class Finished Goods or WIP / Semi-Finished) with a default BOM, one draft
Job Order for the quantity not yet on a Job Order of that line, linked to the Sales Order line, finishing into
the line's store and through PEPL's WIP store, due on the line's delivery date. Production reviews and submits
it (submitting creates the Job Cards). Bought-out and raw material lines go to the Material Request (C2-07).

A manufactured line without a BOM gets no Job Order; Production is told by ToDo (rule PRD-NO-BOM).
Cancelling the Sales Order deletes the draft Job Orders it created. Nothing here ever stops the Sales Order:
if drafting fails, the Sales Order is submitted and Production is told (rule PRD-JO-DRAFT-FAILED).
Switched on / off in System Parameters (Production → Draft Job Orders from Sales Orders).
"""

import frappe
from erpnext.stock.get_item_details import get_default_bom
from frappe import _
from frappe.utils import flt, now

from pepl_os.common import alerts, params
from pepl_os.pepl_stores import stock_tree

ENABLE_FIELD = "custom_job_order_from_sales_order"
AUTO_FIELD = "custom_auto_from_sales_order"
OWNER_FIELD = "custom_production_notification_owner"
NO_BOM_RULE = "PRD-NO-BOM"
FAILED_RULE = "PRD-JO-DRAFT-FAILED"
MADE_IN_HOUSE = (stock_tree.FINISHED_GOODS, stock_tree.WIP)
SAVEPOINT = "pepl_job_orders"


def enabled():
	return params.is_enabled(ENABLE_FIELD, 1)


def is_manufactured(item_code):
	group = frappe.get_cached_value("Item", item_code, "item_group")
	return stock_tree.stock_class_of(group) in MADE_IN_HOUSE


def qty_on_job_orders(sales_order_item):
	"""Quantity of this Sales Order line already on a draft or submitted Job Order."""
	return flt(
		frappe.db.sql(
			"""select sum(qty) from `tabWork Order`
			where sales_order_item = %s and docstatus < 2 and status != 'Closed'""",
			sales_order_item,
		)[0][0]
	)


def wip_store(company):
	return frappe.db.get_value(
		"Warehouse",
		{"company": company, "warehouse_name": stock_tree.default_store_for(stock_tree.WIP), "is_group": 0},
		"name",
	)


def draft_job_orders(so):
	"""Create the missing draft Job Orders for this submitted Sales Order.

	Returns {"created": [Work Order names], "no_bom": [item codes]}.
	"""
	created, no_bom = [], []
	wip = wip_store(so.company)
	for row in so.items:
		if not is_manufactured(row.item_code):
			continue
		bom = get_default_bom(row.item_code)
		if not bom:
			if row.item_code not in no_bom:
				no_bom.append(row.item_code)
			continue
		pending = flt(row.stock_qty) - qty_on_job_orders(row.name)
		if pending <= 0:
			continue
		work_order = frappe.get_doc(
			{
				"doctype": "Work Order",
				"production_item": row.item_code,
				"bom_no": bom,
				"qty": pending,
				"company": so.company,
				"sales_order": so.name,
				"sales_order_item": row.name,
				"project": so.project,
				"fg_warehouse": row.warehouse,
				"wip_warehouse": wip,
				"description": row.description,
				"planned_start_date": now(),
				"expected_delivery_date": row.delivery_date or so.delivery_date,
				AUTO_FIELD: 1,
			}
		)
		# as ERPNext's own Production Plan does: the BOM's operations, so submitting it makes the Job Cards
		work_order.set_work_order_operations()
		work_order.flags.ignore_permissions = True  # the Sales user who submits the order may not create them
		work_order.flags.ignore_mandatory = True
		work_order.insert()
		created.append(work_order.name)
	return {"created": created, "no_bom": no_bom}


def _flag_missing_boms(so, items):
	if not items:
		return
	alerts.raise_todo(
		NO_BOM_RULE,
		"Sales Order",
		so.name,
		f"Sales Order {so.name}: no default BOM for {', '.join(items)}, so no Job Order was drafted. "
		"Make and submit the BOM, then create the Job Order from the Sales Order.",
		owner_field=OWNER_FIELD,
		priority="High",
	)


def on_sales_order_submit(doc, method=None):
	"""doc_events: Sales Order on_submit (after pepl_sales and the C2-07 Material Request)."""
	if not enabled():
		return
	frappe.db.savepoint(SAVEPOINT)
	try:
		result = draft_job_orders(doc)
	except Exception:
		frappe.db.rollback(save_point=SAVEPOINT)
		frappe.log_error(title=f"PEPL: Job Order draft failed for {doc.name}")
		frappe.msgprint(
			_("The Job Orders for this order could not be drafted. Production has been notified."),
			indicator="orange",
			alert=True,
		)
		alerts.raise_todo(
			FAILED_RULE,
			"Sales Order",
			doc.name,
			f"Job Orders for Sales Order {doc.name} could not be drafted automatically. "
			"Create them from the Sales Order and check the Error Log.",
			owner_field=OWNER_FIELD,
			priority="High",
		)
		return
	_flag_missing_boms(doc, result["no_bom"])
	if result["created"]:
		frappe.msgprint(
			_(
				"Draft Job Order(s) {0} created for the manufactured lines. Production reviews and submits them."
			).format(", ".join(frappe.bold(n) for n in result["created"])),
			indicator="green",
			alert=True,
		)
	if result["no_bom"]:
		frappe.msgprint(
			_("No BOM for {0}: Production has been asked to make it.").format(", ".join(result["no_bom"])),
			indicator="orange",
			alert=True,
		)


def on_sales_order_cancel(doc, method=None):
	"""doc_events: Sales Order on_cancel - delete the draft Job Orders this order created."""
	for name in frappe.get_all(
		"Work Order", filters={"sales_order": doc.name, "docstatus": 0, AUTO_FIELD: 1}, pluck="name"
	):
		frappe.delete_doc("Work Order", name, ignore_permissions=True)
