"""C3a-X9 - Customer-supplied material (CSM) consumed by what is delivered, and the Delivery Note material gate.

When PEPL delivers parts made from the customer's own material, the material they used must leave the CSM
stores against that Sales Order. The Delivery Note works it out and books it:

- Needed: for each Sales Order line delivered, the CSM per piece from its BOM (the line's Job Order BOM, else
  the item's default BOM; multi-level BOMs are flattened) x the quantity delivered on all submitted Delivery
  Notes of the order, this one included.
- Already consumed: CSM issued to production against the order (C2-16 issues and earlier deliveries).
- To consume now = needed - already consumed. Available = the order's CSM still in the CSM stores.

On submit, the Delivery Note posts one Material Issue per Sales Order for what is to be consumed now (zero
value; heat lots first in, first out, so the heat number follows the material), linked to the Delivery Note.
Cancelling the Delivery Note cancels it. A difference within "CSM Reconciliation Tolerance (kg)" (in the
material's stock unit) is ignored.

The material gate (pepl_sales "Delivery Note Material Gate Mode") stops a delivery that would consume more
customer material than the order holds: Off - nothing; Warn at Validate, Block at Submit - a warning on save
and no submit; Hard Block - the Delivery Note cannot even be saved. If posting the issue fails, the delivery
still goes and the Stores notification owner gets a ToDo (PRD-CSM-NOT-CONSUMED).
"""

import frappe
from erpnext.stock.get_item_details import get_default_bom
from frappe import _
from frappe.utils import flt

from pepl_os.common import alerts, params
from pepl_os.pepl_stores import csm, stock_tree
from pepl_os.pepl_stores.heat import HEAT_FIELD

GATE_FIELD = "dn_material_gate_mode"  # owned by pepl_sales
TOLERANCE_FIELD = "csm_reconciliation_tolerance_kg"  # owned by pepl_sales
OFF, WARN, HARD = "Off", "Warn at Validate, Block at Submit", "Hard Block"
DN_FIELD = "custom_delivery_note"
SUMMARY_FIELD = "custom_csm_consumption"
FAILED_RULE = "PRD-CSM-NOT-CONSUMED"
OWNER_FIELD = "custom_stores_notification_owner"


def gate_mode():
	value = params.get(GATE_FIELD, WARN)
	return value if value in (OFF, WARN, HARD) else WARN


def tolerance():
	return max(flt(params.get(TOLERANCE_FIELD, 0.5)), 0)


def csm_per_piece(bom_no):
	"""{csm item: stock qty per finished piece} of a BOM (exploded to the leaf materials)."""
	if not bom_no:
		return {}
	rows = frappe.get_all(
		"BOM Explosion Item",
		filters={"parent": bom_no, "parenttype": "BOM"},
		fields=["item_code", "qty_consumed_per_unit", "stock_qty"],
	)
	if not rows:  # an unsaved explosion: fall back to the first level
		quantity = flt(frappe.db.get_value("BOM", bom_no, "quantity")) or 1
		rows = [
			frappe._dict(item_code=r.item_code, qty_consumed_per_unit=flt(r.stock_qty) / quantity)
			for r in frappe.get_all(
				"BOM Item", filters={"parent": bom_no, "parenttype": "BOM"}, fields=["item_code", "stock_qty"]
			)
		]
	per_piece = {}
	for r in rows:
		if stock_tree._is_csm_item(r.item_code):
			per_piece[r.item_code] = per_piece.get(r.item_code, 0) + flt(r.qty_consumed_per_unit)
	return per_piece


def line_bom(item_code, so_detail):
	"""The BOM a Sales Order line was made with: its Job Order's, else the item's default."""
	if so_detail:
		bom = frappe.db.get_value(
			"Work Order",
			{"sales_order_item": so_detail, "docstatus": ["<", 2], "production_item": item_code},
			"bom_no",
			order_by="docstatus desc, creation desc",
		)
		if bom:
			return bom
	return get_default_bom(item_code)


def _needed(rows):
	"""{item: qty} of CSM needed by these Delivery Note rows (stock_qty of the finished part)."""
	need = {}
	for row in rows:
		for item, per in csm_per_piece(line_bom(row.item_code, row.so_detail)).items():
			need[item] = need.get(item, 0) + per * flt(row.stock_qty or row.qty)
	return need


def plan(doc):
	"""Per Sales Order: [{item, needed, consumed, to_consume, available, short}] for this Delivery Note."""
	result = {}
	orders = sorted({r.against_sales_order for r in doc.get("items") or [] if r.get("against_sales_order")})
	for order in orders:
		mine = [r for r in doc.items if r.get("against_sales_order") == order]
		this_dn = _needed(mine)
		if not this_dn:
			continue
		earlier = frappe.db.sql(
			"""select i.item_code, i.so_detail, i.qty, i.stock_qty from `tabDelivery Note Item` i
			join `tabDelivery Note` d on d.name = i.parent
			where d.docstatus = 1 and d.is_return = 0 and i.against_sales_order = %s and d.name != %s""",
			(order, doc.name or ""),
			as_dict=True,
		)
		before = _needed(earlier)
		balance = {r.item_code: r for r in csm.csm_balance({"sales_order": order})}
		lines = []
		for item in sorted(this_dn):
			needed = this_dn[item] + before.get(item, 0)
			row = balance.get(item)
			consumed = flt(row.issued) if row else 0
			available = max(flt(row.balance), 0) if row else 0
			to_consume = max(needed - consumed, 0)
			lines.append(
				frappe._dict(
					item_code=item,
					needed=round(needed, 6),
					consumed=round(consumed, 6),
					to_consume=round(to_consume, 6),
					available=round(available, 6),
					short=round(max(to_consume - available, 0), 6),
				)
			)
		result[order] = lines
	return result


def _short_message(shortages):
	parts = [
		_("{0}: needs {1} more of {2} (to consume {3}, the order holds {4})").format(
			order, flt(line.short, 3), line.item_code, flt(line.to_consume, 3), flt(line.available, 3)
		)
		for order, line in shortages
	]
	return _("The customer's material on hand does not cover this delivery. {0}.").format("; ".join(parts))


def shortages(doc):
	limit = tolerance()
	return [(order, line) for order, lines in plan(doc).items() for line in lines if line.short > limit]


# Delivery Note hooks -----------------------------------------------------------------------------------


def validate_delivery_note(doc, method=None):
	"""doc_events: Delivery Note validate. The material gate (warning or hard block) and the summary."""
	if doc.get("is_return"):
		return
	short = shortages(doc)
	mode = gate_mode()
	summary = []
	for order, lines in plan(doc).items():
		for line in lines:
			summary.append(
				_("{0}: {1} {2} to consume").format(order, flt(line.to_consume, 3), line.item_code)
			)
	if doc.meta.get_field(SUMMARY_FIELD) and doc.docstatus == 0:
		doc.set(SUMMARY_FIELD, "\n".join(summary))
	if not short or mode == OFF:
		return
	message = _short_message(short)
	if mode == HARD:
		frappe.throw(
			message + " " + _("Delivery Note Material Gate Mode is Hard Block."), title=_("CSM short")
		)
	if doc.docstatus == 0:
		frappe.msgprint(
			message + " " + _("It cannot be submitted until the material is received."),
			title=_("CSM short"),
			indicator="orange",
		)


def before_submit_delivery_note(doc, method=None):
	"""doc_events: Delivery Note before_submit. Block at submit (both Warn and Hard modes)."""
	if doc.get("is_return") or gate_mode() == OFF:
		return
	short = shortages(doc)
	if short:
		frappe.throw(_short_message(short), title=_("CSM short"))


def _lots(order, item_code, warehouses):
	"""The order's CSM lots of an item still in the CSM stores: [{warehouse, batch, heat, qty}], oldest first."""
	rows = frappe.db.sql(
		f"""select d.s_warehouse, d.t_warehouse, d.batch_no, d.{HEAT_FIELD} as heat, d.transfer_qty as qty
		from `tabStock Entry Detail` d join `tabStock Entry` se on se.name = d.parent
		where se.docstatus = 1 and se.custom_sales_order = %s and d.item_code = %s
		order by se.posting_date, se.posting_time, se.creation, d.idx""",
		(order, item_code),
		as_dict=True,
	)
	lots, order_seen = {}, []
	for r in rows:
		for warehouse, sign in ((r.t_warehouse, 1), (r.s_warehouse, -1)):
			if warehouse in warehouses:
				key = (warehouse, r.batch_no or "", r.heat or "")
				if key not in lots:
					lots[key] = 0.0
					order_seen.append(key)
				lots[key] += sign * flt(r.qty)
	return [
		frappe._dict(warehouse=k[0], batch=k[1], heat=k[2], qty=lots[k]) for k in order_seen if lots[k] > 1e-9
	]


def _csm_stores(company):
	scrap = set(frappe.get_all("Warehouse", filters={"warehouse_name": csm.SCRAP_STORE}, pluck="name"))
	return {
		w
		for w in frappe.get_all("Warehouse", filters={"company": company, "is_group": 0}, pluck="name")
		if stock_tree.is_csm_warehouse(w) and w not in scrap
	}


def consume(doc):
	"""Post the CSM Material Issue(s) for this Delivery Note. Returns the Stock Entry names."""
	stores = _csm_stores(doc.company)
	limit = tolerance()
	made = []
	for order, lines in plan(doc).items():
		rows = []
		for line in lines:
			qty = min(line.to_consume, line.available)
			if qty <= limit:
				continue
			for lot in _lots(order, line.item_code, stores):
				if qty <= 1e-9:
					break
				take = min(qty, lot.qty)
				row = {"item_code": line.item_code, "qty": take, "s_warehouse": lot.warehouse}
				if lot.batch:
					row.update(batch_no=lot.batch, use_serial_batch_fields=1)
				if lot.heat:
					row[HEAT_FIELD] = lot.heat
				rows.append(row)
				qty -= take
		if not rows:
			continue
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Issue",
				"purpose": "Material Issue",
				"company": doc.company,
				"posting_date": doc.posting_date,
				"set_posting_time": 1,
				csm.SO_FIELD: order,
				DN_FIELD: doc.name,
				"remarks": _(
					"Customer-supplied material consumed by Delivery Note {0} (Sales Order {1})."
				).format(doc.name, order),
				"items": rows,
			}
		)
		entry.flags.ignore_permissions = True
		entry.insert()
		entry.submit()
		made.append(entry.name)
	return made


def on_submit_delivery_note(doc, method=None):
	"""doc_events: Delivery Note on_submit. Never stops the delivery once the gate has passed."""
	if doc.get("is_return"):
		return
	frappe.db.savepoint("pepl_csm_consumption")
	try:
		made = consume(doc)
	except Exception:
		frappe.db.rollback(save_point="pepl_csm_consumption")
		frappe.log_error(title=f"PEPL: CSM not consumed for {doc.name}")
		alerts.raise_todo(
			FAILED_RULE,
			"Delivery Note",
			doc.name,
			f"Delivery Note {doc.name}: the customer-supplied material it used could not be issued "
			"automatically. Post the Material Issue against the Sales Order and check the Error Log.",
			owner_field=OWNER_FIELD,
			priority="High",
		)
		frappe.msgprint(
			_("The customer's material used by this delivery could not be issued. Stores has been notified."),
			indicator="orange",
			alert=True,
		)
		return
	if made:
		frappe.msgprint(
			_("Customer-supplied material consumed: {0}").format(", ".join(frappe.bold(n) for n in made)),
			indicator="green",
			alert=True,
		)


def on_cancel_delivery_note(doc, method=None):
	"""doc_events: Delivery Note on_cancel. Cancel the CSM issue(s) it posted."""
	for name in frappe.get_all("Stock Entry", filters={DN_FIELD: doc.name, "docstatus": 1}, pluck="name"):
		entry = frappe.get_doc("Stock Entry", name)
		entry.flags.ignore_permissions = True
		entry.cancel()


@frappe.whitelist()
def consumption_preview(delivery_note):
	"""For the Delivery Note form: what it will consume and whether the material is there."""
	doc = frappe.get_doc("Delivery Note", delivery_note)
	doc.check_permission("read")
	return {
		"mode": gate_mode(),
		"tolerance": tolerance(),
		"orders": plan(doc),
		"consumed_by": frappe.get_all(
			"Stock Entry", filters={DN_FIELD: doc.name, "docstatus": 1}, pluck="name"
		),
	}
