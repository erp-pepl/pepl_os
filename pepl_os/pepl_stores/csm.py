"""C2-16 - Customer-Supplied Material (CSM) against its Sales Order.

* Receipt: a Material Request of type "Customer Provided" -> Stock Entry (Material Receipt)
  into CSM Stores. ERPNext values customer-provided items at zero, so PEPL's stock value
  does not change. The C2-15 heat number fields and gate apply (CSM items are heat-tracked).
* Every Stock Entry with a CSM line names its Sales Order (custom_sales_order): receipts,
  issues to production, moves to CSM Scrap and returns to the customer. A hard rule.
* Returns to the customer use the Stock Entry Type "CSM Return to Customer" (a Material
  Issue), so the balance report can tell them apart from issues to production.
* The Sales Order carries a scrap option (Hold / Return to Customer / PEPL May Sell,
  default Hold). It appears once the order has CSM movements; C2-18 acts on it.
* Report PEPL CSM Balance by Order: received, issued, scrapped, returned and balance
  per Sales Order and CSM item.
"""

import frappe
from frappe import _
from frappe.utils import flt

from pepl_os.pepl_stores import stock_tree

SO_FIELD = "custom_sales_order"
HAS_CSM_FIELD = "custom_has_csm"
DISPOSITION_FIELD = "custom_csm_scrap_disposition"
HOLD, RETURN_TO_CUSTOMER, PEPL_MAY_SELL = "Hold", "Return to Customer", "PEPL May Sell"
DISPOSITIONS = (HOLD, RETURN_TO_CUSTOMER, PEPL_MAY_SELL)
RETURN_TYPE = "CSM Return to Customer"
SCRAP_STORE = "CSM Scrap"


def csm_rows(doc):
	return [row for row in doc.get("items") or [] if row.item_code and stock_tree._is_csm_item(row.item_code)]


# Setup ------------------------------------------------------------------------------------


def ensure_return_type():
	"""Install / migrate: the Stock Entry Type used to give CSM back to the customer."""
	if frappe.db.exists("Stock Entry Type", RETURN_TYPE):
		return False
	frappe.get_doc({"doctype": "Stock Entry Type", "name": RETURN_TYPE, "purpose": "Material Issue"}).insert(
		ignore_permissions=True
	)
	return True


# Stock Entry --------------------------------------------------------------------------------


def before_validate_stock_entry(doc, method=None):
	"""doc_events: Stock Entry before_validate. From a Customer Provided Material Request the
	Sales Order comes with it (the request's "Drafted from Sales Order")."""
	if doc.get(SO_FIELD):
		return
	requests = {row.material_request for row in doc.get("items") or [] if row.get("material_request")}
	orders = {frappe.db.get_value("Material Request", mr, SO_FIELD) for mr in requests} - {None, ""}
	if len(orders) == 1:
		doc.set(SO_FIELD, orders.pop())


def validate_stock_entry(doc, method=None):
	"""doc_events: Stock Entry validate. A CSM line moves only against its (submitted) Sales Order."""
	rows = csm_rows(doc)
	if doc.stock_entry_type == RETURN_TYPE:
		csm_idx = {row.idx for row in rows}
		others = [row for row in doc.get("items") or [] if row.item_code and row.idx not in csm_idx]
		if others:
			frappe.throw(
				_("{0} is only for customer-supplied material. Row {1}: {2} is PEPL material.").format(
					frappe.bold(RETURN_TYPE), others[0].idx, frappe.bold(others[0].item_code)
				),
				title=_("Customer-supplied material"),
			)
	if not rows:
		return
	order = doc.get(SO_FIELD)
	if not order:
		frappe.throw(
			_(
				"Customer-supplied material moves only against its Sales Order. "
				"Fill in <b>Sales Order</b> (CSM lines: {0})."
			).format(", ".join(f"{row.idx} {row.item_code}" for row in rows)),
			title=_("Sales Order required"),
		)
	values = frappe.db.get_value("Sales Order", order, ["docstatus", "company"], as_dict=True)
	if not values or values.docstatus != 1:
		frappe.throw(
			_("Sales Order {0} must be submitted before customer material is moved against it.").format(
				frappe.bold(order)
			),
			title=_("Sales Order required"),
		)
	if values.company != doc.company:
		frappe.throw(
			_("Sales Order {0} belongs to {1}, not {2}.").format(
				frappe.bold(order), values.company, doc.company
			),
			title=_("Sales Order required"),
		)


def on_stock_entry_change(doc, method=None):
	"""doc_events: Stock Entry on_submit / on_cancel. Show the scrap option on the order."""
	if doc.get(SO_FIELD):
		sync_order_flag(doc.get(SO_FIELD))


def sync_order_flag(sales_order):
	has = frappe.db.sql(
		"""select 1 from `tabStock Entry` se
		join `tabStock Entry Detail` d on d.parent = se.name
		join `tabItem` i on i.name = d.item_code
		where se.docstatus = 1 and se.custom_sales_order = %s and i.is_customer_provided_item = 1
		limit 1""",
		sales_order,
	)
	values = {HAS_CSM_FIELD: 1 if has else 0}
	if not frappe.db.get_value("Sales Order", sales_order, DISPOSITION_FIELD):
		values[DISPOSITION_FIELD] = HOLD
	frappe.db.set_value("Sales Order", sales_order, values, update_modified=False)


# Balance by order --------------------------------------------------------------------------


def _scrap_stores():
	return set(frappe.get_all("Warehouse", filters={"warehouse_name": SCRAP_STORE}, pluck="name"))


def csm_balance(filters=None):
	"""Rows per Sales Order and CSM item, from the stock ledger (cancelled entries excluded).

	received  - into a CSM store (not CSM Scrap) by a receipt
	issued    - out of a CSM store to production (any issue that is not a return or a transfer)
	scrapped  - moved into CSM Scrap
	returned  - given back to the customer (Stock Entry Type "CSM Return to Customer")
	balance   - on hand in the CSM stores against the order; scrap_on_hand - in CSM Scrap
	"""
	filters = frappe._dict(filters or {})
	conditions, values = (
		[
			"sle.is_cancelled = 0",
			"i.is_customer_provided_item = 1",
			"ifnull(se.custom_sales_order, '') != ''",
		],
		{},
	)
	for key, column in (
		("company", "sle.company"),
		("sales_order", "se.custom_sales_order"),
		("customer", "so.customer"),
		("item_code", "sle.item_code"),
	):
		if filters.get(key):
			conditions.append(f"{column} = %({key})s")
			values[key] = filters[key]
	if filters.get("to_date"):
		conditions.append("sle.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	entries = frappe.db.sql(
		f"""select se.custom_sales_order as sales_order, so.customer, sle.item_code, i.item_name,
			i.stock_uom, sle.warehouse, sle.actual_qty, sle.stock_value_difference,
			se.purpose, se.stock_entry_type
		from `tabStock Ledger Entry` sle
		join `tabStock Entry` se on se.name = sle.voucher_no and sle.voucher_type = 'Stock Entry'
		join `tabItem` i on i.name = sle.item_code
		left join `tabSales Order` so on so.name = se.custom_sales_order
		where {" and ".join(conditions)}
		order by se.custom_sales_order, sle.item_code""",
		values,
		as_dict=True,
	)
	scrap = _scrap_stores()
	rows = {}
	for e in entries:
		key = (e.sales_order, e.item_code)
		row = rows.setdefault(
			key,
			frappe._dict(
				sales_order=e.sales_order,
				customer=e.customer,
				item_code=e.item_code,
				item_name=e.item_name,
				uom=e.stock_uom,
				received=0.0,
				issued=0.0,
				scrapped=0.0,
				returned=0.0,
				balance=0.0,
				scrap_on_hand=0.0,
				balance_value=0.0,
			),
		)
		qty = flt(e.actual_qty)
		is_return = e.stock_entry_type == RETURN_TYPE
		if e.warehouse in scrap:
			row.scrap_on_hand += qty
			if qty > 0 and not is_return:
				row.scrapped += qty
			elif qty < 0 and is_return:
				row.returned += -qty
			continue
		row.balance += qty
		row.balance_value += flt(e.stock_value_difference)
		if e.purpose == "Material Transfer":
			continue  # between CSM stores, or into CSM Scrap (counted on the scrap side)
		if qty > 0:
			row.received += qty
		elif is_return:
			row.returned += -qty
		else:
			row.issued += -qty
	disposition = {}
	orders = {r.sales_order for r in rows.values()}
	if orders:
		disposition = dict(
			frappe.get_all(
				"Sales Order",
				filters={"name": ["in", list(orders)]},
				fields=["name", DISPOSITION_FIELD],
				as_list=True,
			)
		)
	result = []
	for row in rows.values():
		row.scrap_disposition = disposition.get(row.sales_order) or HOLD
		result.append(row)
	return result


@frappe.whitelist()
def get_order_balance(sales_order):
	"""For the Sales Order form: its CSM lines with the balance."""
	frappe.has_permission("Sales Order", doc=sales_order, throw=True)
	return csm_balance({"sales_order": sales_order})
