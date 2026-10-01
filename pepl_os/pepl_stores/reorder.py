"""C2-19 - Reorder engine for raw material and consumables.

suggest_reorder(item, warehouse, as_of):
  * daily consumption = outflows from the store over the Reorder Usage Period / its days.
    Counted: Material Issue, Manufacture / Material Consumption for Manufacture, and
    transfers into a WIP store. Store-to-store moves are not consumption.
  * lead time = median days from PO date to receipt for this item, else the Item's
    Lead Time in days.
  * level = daily x (lead time + Reorder Safety Days); qty = daily x 30, rounded up to
    the Item's minimum order qty. Items with under 30 days of history are flagged.

PEPL Reorder Review (Stores HOD, monthly): "Compute suggestions" fills the rows; on
submit the accepted rows are written into each Item's standard Reorder table.

Every morning rule STO-REORDER raises one ToDo per item whose projected qty is below its
reorder level (closed when it recovers). The Item shows a "Create Material Request"
button. ERPNext's own automatic Material Request stays off until the HOD asks for it.
"""

import math
import statistics

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, get_first_day, getdate, today

from pepl_os.common import params
from pepl_os.common.alerts import close_resolved, raise_todo
from pepl_os.common.jobs import tracked_job
from pepl_os.pepl_stores import stock_tree

REVIEW = "PEPL Reorder Review"
REVIEW_ITEM = "PEPL Reorder Review Item"
RULE = "STO-REORDER"
REVIEW_RULE = "STO-REORDER-REVIEW"
STORES_OWNER = "custom_stores_notification_owner"
MIN_HISTORY_DAYS = 30
ORDER_COVER_DAYS = 30
CONSUMING = ("Material Issue", "Manufacture", "Material Consumption for Manufacture")
TRANSFERS = ("Material Transfer", "Material Transfer for Manufacture")
REORDER_CLASSES = (stock_tree.RAW_MATERIAL, stock_tree.CONSUMABLES)


AUTO_MR_FIELD = "auto_indent"
AUTO_MR_FLAG = "pepl_auto_indent_switched_off"


def switch_off_auto_mr_once():
	"""Install / migrate: ERPNext's setup wizard turns on "Raise Material Request when stock reaches
	re-order level". PEPL reviews reorder levels first (Reorder Review) and alerts Stores instead, so it is
	switched off - once. If the Stores HOD later asks for it and it is ticked again, it stays on."""
	if cint(frappe.db.get_default(AUTO_MR_FLAG)):
		return False
	changed = bool(cint(frappe.db.get_single_value("Stock Settings", AUTO_MR_FIELD)))
	if changed:
		frappe.db.set_single_value("Stock Settings", AUTO_MR_FIELD, 0)
		frappe.clear_cache(doctype="Stock Settings")
	frappe.db.set_default(AUTO_MR_FLAG, 1)
	return changed


def lookback_days():
	return params.get_int("custom_reorder_lookback_days", 90) or 90


def safety_days():
	return params.get_int("custom_reorder_safety_days", 0)


def _wip_stores():
	names = set()
	for g in frappe.get_all(
		"Warehouse", filters={"warehouse_name": stock_tree.WIP_GROUP, "is_group": 1}, fields=["lft", "rgt"]
	):
		names.update(
			frappe.get_all("Warehouse", filters={"lft": [">", g.lft], "rgt": ["<", g.rgt]}, pluck="name")
		)
	return names


def consumption(item_code, warehouse, as_of=None, days=None):
	"""Total consumed from this store in the `days` up to and including `as_of`."""
	as_of = getdate(as_of or today())
	days = days or lookback_days()
	start = add_days(as_of, -(days - 1))
	rows = frappe.db.sql(
		"""select -sle.actual_qty as qty, se.purpose, sed.t_warehouse
		from `tabStock Ledger Entry` sle
		join `tabStock Entry` se on se.name = sle.voucher_no
		left join `tabStock Entry Detail` sed on sed.name = sle.voucher_detail_no
		where sle.voucher_type = 'Stock Entry' and sle.is_cancelled = 0 and sle.actual_qty < 0
			and sle.item_code = %s and sle.warehouse = %s and sle.posting_date between %s and %s""",
		(item_code, warehouse, start, as_of),
		as_dict=True,
	)
	wip = None
	total = 0.0
	for r in rows:
		if r.purpose in CONSUMING:
			total += flt(r.qty)
		elif r.purpose in TRANSFERS:
			if wip is None:
				wip = _wip_stores()
			if r.t_warehouse in wip:
				total += flt(r.qty)
	return total


def history_days(item_code, warehouse, as_of=None):
	first = frappe.db.sql(
		"""select min(posting_date) from `tabStock Ledger Entry`
		where item_code = %s and warehouse = %s and is_cancelled = 0""",
		(item_code, warehouse),
	)[0][0]
	return date_diff(getdate(as_of or today()), first) + 1 if first else 0


def lead_time(item_code):
	"""(days, basis): median PO date -> receipt days from history, else the Item's lead time."""
	rows = frappe.db.sql(
		"""select datediff(pr.posting_date, po.transaction_date)
		from `tabPurchase Receipt Item` pri
		join `tabPurchase Receipt` pr on pr.name = pri.parent and pr.docstatus = 1 and pr.is_return = 0
		join `tabPurchase Order` po on po.name = pri.purchase_order
		where pri.item_code = %s""",
		item_code,
	)
	days = [cint(r[0]) for r in rows if r[0] is not None and r[0] >= 0]
	if days:
		return math.ceil(statistics.median(days)), _("median of {0} receipt(s)").format(len(days))
	return cint(frappe.get_cached_value("Item", item_code, "lead_time_days")), _("Item lead time")


def _round_up(value, step=None):
	value = round(flt(value), 6)
	if step and flt(step) > 0:
		return math.ceil(value / flt(step)) * flt(step)
	return math.ceil(value)


def suggest_reorder(item_code, warehouse, as_of=None):
	as_of = getdate(as_of or today())
	days = lookback_days()
	used = consumption(item_code, warehouse, as_of, days)
	daily = used / days
	lead, lead_basis = lead_time(item_code)
	safety = safety_days()
	history = history_days(item_code, warehouse, as_of)
	moq = flt(frappe.get_cached_value("Item", item_code, "min_order_qty"))
	level = _round_up(daily * (lead + safety))
	qty = _round_up(daily * ORDER_COVER_DAYS, moq) if daily else 0
	insufficient = history < MIN_HISTORY_DAYS
	basis = _("{0} used in {1} days = {2}/day; lead {3} days ({4}) + safety {5} days").format(
		flt(used, 3), days, flt(daily, 3), lead, lead_basis, safety
	)
	if insufficient:
		basis = _("Insufficient history ({0} days, needs {1}). ").format(history, MIN_HISTORY_DAYS) + basis
	return frappe._dict(
		item_code=item_code,
		warehouse=warehouse,
		daily_consumption=flt(daily, 3),
		lead_time_days=lead,
		suggested_level=level,
		suggested_qty=qty,
		insufficient_history=1 if insufficient else 0,
		history_days=history,
		basis=basis,
	)


def current_reorder(item_code, warehouse):
	return frappe.db.get_value(
		"Item Reorder",
		{"parent": item_code, "parenttype": "Item", "warehouse": warehouse},
		["warehouse_reorder_level", "warehouse_reorder_qty"],
		as_dict=True,
	) or frappe._dict(warehouse_reorder_level=0, warehouse_reorder_qty=0)


def candidates(company):
	"""(item, store) pairs: raw material and consumables items in their class store."""
	pairs = []
	for stock_class in REORDER_CLASSES:
		store = frappe.db.get_value(
			"Warehouse",
			{
				"company": company,
				"warehouse_name": stock_tree.CLASS_DEFAULT_STORE[stock_class],
				"is_group": 0,
			},
			"name",
		)
		if not store:
			continue
		for item in frappe.get_all(
			"Item",
			filters={"custom_stock_class": stock_class, "is_stock_item": 1, "disabled": 0, "has_variants": 0},
			pluck="name",
			order_by="name",
		):
			pairs.append((item, store))
	return pairs


# Reorder Review -------------------------------------------------------------------------


@frappe.whitelist()
def compute_suggestions(name):
	doc = frappe.get_doc(REVIEW, name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft review can be recomputed."))
	fill_review(doc)
	doc.save()
	return len(doc.items)


def fill_review(doc):
	doc.set("items", [])
	for item_code, store in candidates(doc.company):
		s = suggest_reorder(item_code, store, doc.review_date)
		now = current_reorder(item_code, store)
		if not s.daily_consumption and not now.warehouse_reorder_level:
			continue  # nothing used and no level set: nothing to review
		doc.append(
			"items",
			{
				"item_code": item_code,
				"warehouse": store,
				"current_level": flt(now.warehouse_reorder_level),
				"current_qty": flt(now.warehouse_reorder_qty),
				"daily_consumption": s.daily_consumption,
				"lead_time_days": s.lead_time_days,
				"suggested_level": s.suggested_level,
				"suggested_qty": s.suggested_qty,
				"insufficient_history": s.insufficient_history,
				"basis": s.basis,
				"accept": 0 if s.insufficient_history else 1,
				"final_level": s.suggested_level,
				"final_qty": s.suggested_qty,
			},
		)


def validate_review(doc):
	if not doc.prepared_by:
		doc.prepared_by = frappe.session.user
	for row in doc.items:
		if flt(row.final_level) < 0 or flt(row.final_qty) < 0:
			frappe.throw(_("Row {0}: level and qty cannot be negative.").format(row.idx))
		if row.accept and flt(row.final_level) > 0 and flt(row.final_qty) <= 0:
			frappe.throw(_("Row {0}: give a reorder qty for the level {1}.").format(row.idx, row.final_level))


def on_submit_review(doc):
	"""Write the accepted rows into each Item's Reorder table (standard ERPNext)."""
	for row in doc.items:
		if not row.accept:
			continue
		item = frappe.get_doc("Item", row.item_code)
		existing = [r for r in item.get("reorder_levels") or [] if r.warehouse == row.warehouse]
		if existing:
			target = existing[0]
		else:
			target = item.append(
				"reorder_levels",
				{
					"warehouse": row.warehouse,
					"warehouse_group": row.warehouse,
					"material_request_type": "Purchase",
				},
			)
		target.warehouse_reorder_level = flt(row.final_level)
		target.warehouse_reorder_qty = flt(row.final_qty)
		item.flags.ignore_permissions = True
		item.save()
	close_resolved(REVIEW_RULE, REVIEW, frappe.get_all(REVIEW, filters={"docstatus": 0}, pluck="name"))


@tracked_job("Monthly reorder review")
def monthly_reorder_review():
	made = []
	start = get_first_day(today())
	for company in frappe.get_all("Company", pluck="name"):
		if frappe.db.exists(
			REVIEW, {"company": company, "review_date": [">=", start], "docstatus": ["<", 2]}
		):
			continue
		doc = frappe.get_doc({"doctype": REVIEW, "company": company, "review_date": today()})
		fill_review(doc)
		doc.insert(ignore_permissions=True)
		made.append(doc.name)
		raise_todo(
			REVIEW_RULE,
			REVIEW,
			doc.name,
			_("Monthly reorder review {0} for {1}: {2} item(s) to check and submit.").format(
				doc.name, company, len(doc.items)
			),
			owner_field=STORES_OWNER,
		)
	return {"records_touched": len(made), "message": ", ".join(made)}


# Low-stock alerts ------------------------------------------------------------------------


def below_level():
	"""{item: [(warehouse, projected, level, qty)]} for reorder rows whose projected qty is below the level."""
	rows = frappe.db.sql(
		"""select r.parent as item_code, r.warehouse, r.warehouse_reorder_level as level,
			r.warehouse_reorder_qty as qty, ifnull(b.projected_qty, 0) as projected
		from `tabItem Reorder` r
		join `tabItem` i on i.name = r.parent and i.disabled = 0 and i.is_stock_item = 1
		left join `tabBin` b on b.item_code = r.parent and b.warehouse = r.warehouse
		where r.parenttype = 'Item' and r.warehouse_reorder_level > 0""",
		as_dict=True,
	)
	out = {}
	for r in rows:
		if flt(r.projected) < flt(r.level):
			out.setdefault(r.item_code, []).append(r)
	return out


def sync_reorder_todos():
	low = below_level()
	for item_code, rows in low.items():
		text = "; ".join(
			_("{0}: projected {1}, reorder level {2}").format(
				r.warehouse, flt(r.projected, 3), flt(r.level, 3)
			)
			for r in rows
		)
		raise_todo(
			RULE,
			"Item",
			item_code,
			_("Low stock {0}: {1}. Open the Item and press Create Material Request.").format(item_code, text),
			owner_field=STORES_OWNER,
			priority="High",
		)
	close_resolved(RULE, "Item", list(low))
	return low


@tracked_job("Low-stock reorder alerts")
def daily_reorder_alerts():
	low = sync_reorder_todos()
	return {"records_touched": len(low), "message": f"{len(low)} item(s) below their reorder level"}


@frappe.whitelist()
def refresh_reorder_alerts():
	"""Do the morning low-stock check now (Stores / System Manager). Not the tracked job: that commits."""
	frappe.only_for(("Stock Manager", "Stock User", "System Manager"))
	return sorted(sync_reorder_todos())


@frappe.whitelist()
def get_item_panel(item_code):
	frappe.has_permission("Item", doc=item_code, throw=True)
	rows = frappe.db.sql(
		"""select r.warehouse, r.warehouse_reorder_level as level, r.warehouse_reorder_qty as qty,
			ifnull(b.projected_qty, 0) as projected, ifnull(b.actual_qty, 0) as actual
		from `tabItem Reorder` r left join `tabBin` b on b.item_code = r.parent and b.warehouse = r.warehouse
		where r.parent = %s and r.parenttype = 'Item'""",
		item_code,
		as_dict=True,
	)
	panel = []
	for r in rows:
		low = flt(r.projected) < flt(r.level)
		panel.append(
			{
				"text": _("{0}: in stock {1}, projected {2}, reorder level {3}, reorder qty {4}").format(
					r.warehouse, flt(r.actual, 3), flt(r.projected, 3), flt(r.level, 3), flt(r.qty, 3)
				),
				"colour": "red" if low else "green",
				"warehouse": r.warehouse,
				"low": 1 if low else 0,
			}
		)
	return panel


@frappe.whitelist()
def make_reorder_mr(item_code, warehouse):
	"""A draft Purchase Material Request for the reorder qty (Item panel button)."""
	frappe.has_permission("Material Request", "create", throw=True)
	row = frappe.db.get_value(
		"Item Reorder",
		{"parent": item_code, "parenttype": "Item", "warehouse": warehouse},
		["warehouse_reorder_level", "warehouse_reorder_qty"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("{0} has no reorder level for {1}.").format(item_code, warehouse))
	projected = flt(
		frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "projected_qty")
	)
	qty = max(flt(row.warehouse_reorder_qty), flt(row.warehouse_reorder_level) - projected)
	lead, _basis = lead_time(item_code)
	required_by = add_days(today(), max(lead, 1))
	uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": frappe.get_cached_value("Warehouse", warehouse, "company"),
			"transaction_date": today(),
			"schedule_date": required_by,
			"items": [
				{
					"item_code": item_code,
					"qty": qty,
					"uom": uom,
					"conversion_factor": 1,
					"warehouse": warehouse,
					"schedule_date": required_by,
				}
			],
		}
	).insert()
	return mr.name


@frappe.whitelist()
def get_suggestion(item_code, warehouse, as_of=None):
	"""The suggestion for one item and store (Stores / System Manager)."""
	frappe.has_permission("Item", doc=item_code, throw=True)
	return suggest_reorder(item_code, warehouse, as_of)
