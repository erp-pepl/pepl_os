"""C2-18 - Scrap Register by metal: rates, weighments, sales and the recovery report.

* Scrap items, one per metal and form that sells at its own price, sit under
  Scrap > <metal> Scrap (UOM Kg). Customer-material scrap has its own items under
  Customer-Supplied Material > CSM Scrap, because CSM and PEPL stock never share a
  store (C2-04). Both are seeded once; Stores adds more by hand.
* PEPL Scrap Rate: rate per kg from a date. The rate on a date is the latest row
  effective on or before it.
* PEPL Scrap Weighment: gross - tare = net kg (> 0). Submit posts a Material Receipt
  into Scrap Yard at the scrap rate - or, for CSM, into CSM Scrap at zero against its
  Sales Order. Cancel reverses it.
* PEPL Scrap Sale: buyer (Customer group "Scrap Buyers"), vehicle, weighbridge slip
  and lines. Submit posts a Material Issue. A line from CSM Scrap is allowed only when
  its Sales Order's CSM Scrap option is "PEPL May Sell" - a hard rule, no override.
* PEPL Scrap Recovery (report): per month and metal - kg generated, kg sold, realised
  rate against the rate master, value, closing kg and value, scrap % of RM issued.
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, get_first_day, get_last_day, getdate, today
from frappe.utils.nestedset import get_root_of

from pepl_os.pepl_stores import csm, stock_tree

RATE = "PEPL Scrap Rate"
WEIGHMENT = "PEPL Scrap Weighment"
SALE = "PEPL Scrap Sale"
SCRAP_BUYERS = "Scrap Buyers"
CSM_SCRAP_GROUP = "CSM Scrap"
SCRAP_YARD = "Scrap Yard"
PROCESS, REJECTION, SOURCE_CSM = "Process", "Rejection", "CSM"
SEEDED_FLAG = "pepl_scrap_items_seeded"
UOM = "Kg"

# (item code, item name, scrap group, HSN codes to try)
BRASS_HSN = ("74040022", "74040012", "740400", "7404")
SEED_ITEMS = (
	("SCRAP-BRASS-TURNINGS", "Brass Turnings", "Brass Scrap", BRASS_HSN),
	("SCRAP-BRASS-SOLID", "Brass Solid", "Brass Scrap", BRASS_HSN),
	("SCRAP-STEEL-TURNINGS", "Steel Turnings", "Steel Scrap", ("72044100", "720441", "7204")),
	("SCRAP-COPPER", "Copper Scrap", "Copper Scrap", ("74040010", "740400", "7404")),
	("SCRAP-ALUMINIUM", "Aluminium Scrap", "Aluminium Scrap", ("76020010", "760200", "7602")),
)


# Seeding ----------------------------------------------------------------------------


def _hsn(candidates):
	if not frappe.get_meta("Item").has_field("gst_hsn_code"):
		return None
	for code in candidates:
		if frappe.db.exists("GST HSN Code", code):
			return code
	return None


def _ensure_uom():
	if not frappe.db.exists("UOM", UOM):
		frappe.get_doc({"doctype": "UOM", "uom_name": UOM, "must_be_whole_number": 0}).insert(
			ignore_permissions=True
		)


def ensure_scrap_masters():
	"""Install / migrate: the CSM Scrap item group and the Scrap Buyers customer group (always);
	the default scrap items (once - Stores may rename or disable them afterwards)."""
	if frappe.db.exists("Item Group", stock_tree.CSM):
		stock_tree._ensure_item_group(CSM_SCRAP_GROUP, stock_tree.CSM, is_group=0)
	if not frappe.db.exists("Customer Group", SCRAP_BUYERS):
		frappe.get_doc(
			{
				"doctype": "Customer Group",
				"customer_group_name": SCRAP_BUYERS,
				"parent_customer_group": get_root_of("Customer Group"),
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	if cint(frappe.db.get_default(SEEDED_FLAG)):
		return []
	made = seed_scrap_items()
	frappe.db.set_default(SEEDED_FLAG, 1)
	return made


def seed_scrap_items():
	"""PEPL scrap items under Scrap > metal, and a CSM twin of each under CSM Scrap."""
	_ensure_uom()
	made = []
	for code, name, group, hsn in SEED_ITEMS:
		for item_code, item_name, item_group in (
			(code, name, group),
			(f"CSM-{code}", f"CSM {name}", CSM_SCRAP_GROUP),
		):
			if frappe.db.exists("Item", item_code) or not frappe.db.exists("Item Group", item_group):
				continue
			values = {
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_name,
				"item_group": item_group,
				"stock_uom": UOM,
				"is_stock_item": 1,
				"is_purchase_item": 0,
				"is_sales_item": 1,
				"include_item_in_manufacturing": 0,
			}
			code_hsn = _hsn(hsn)
			if code_hsn:
				values["gst_hsn_code"] = code_hsn
			try:
				frappe.get_doc(values).insert(ignore_permissions=True)
				made.append(item_code)
			except frappe.ValidationError:
				# e.g. a GST rule on this site; Stores can create the item by hand.
				frappe.clear_last_message()
				frappe.log_error(title=f"PEPL scrap item {item_code} not seeded")
	return made


# Classification -----------------------------------------------------------------------


def is_scrap_item(item_code):
	group = frappe.get_cached_value("Item", item_code, "item_group")
	return stock_tree.stock_class_of(group) == stock_tree.SCRAP


def is_csm_scrap_item(item_code):
	return frappe.get_cached_value("Item", item_code, "item_group") == CSM_SCRAP_GROUP


def metal_of(item_code):
	"""The scrap metal group: 'Brass Scrap', ... ; CSM scrap reports as 'CSM Scrap'."""
	group = frappe.get_cached_value("Item", item_code, "item_group")
	if group == CSM_SCRAP_GROUP:
		return CSM_SCRAP_GROUP
	lineage = [group]
	parent = frappe.get_cached_value("Item Group", group, "parent_item_group")
	while parent and parent not in lineage:
		if parent == stock_tree.SCRAP:
			return lineage[-1]
		lineage.append(parent)
		parent = frappe.get_cached_value("Item Group", parent, "parent_item_group")
	return group


def scrap_warehouse(company, csm_scrap=False):
	name = CSM_SCRAP_GROUP if csm_scrap else SCRAP_YARD
	warehouse = frappe.db.get_value(
		"Warehouse", {"company": company, "warehouse_name": name, "is_group": 0}, "name"
	)
	if not warehouse:
		frappe.throw(_("Warehouse {0} is missing for {1}.").format(frappe.bold(name), company))
	return warehouse


def is_scrap_warehouse(warehouse):
	return frappe.get_cached_value("Warehouse", warehouse, "warehouse_name") in (SCRAP_YARD, CSM_SCRAP_GROUP)


# Rates --------------------------------------------------------------------------------


def rate_on(item_code, on_date=None):
	"""The scrap rate per kg for this item on this date (latest row effective on or before it)."""
	row = frappe.get_all(
		RATE,
		filters={"scrap_item": item_code, "effective_from": ["<=", getdate(on_date or today())]},
		fields=["rate"],
		order_by="effective_from desc, creation desc",
		limit=1,
	)
	return flt(row[0].rate) if row else None


def validate_rate(doc):
	if not is_scrap_item(doc.scrap_item):
		frappe.throw(
			_("{0} is not a scrap item (Item Group under Scrap).").format(frappe.bold(doc.scrap_item))
		)
	if flt(doc.rate) <= 0:
		frappe.throw(_("The rate per kg must be more than zero."))
	other = frappe.db.get_value(
		RATE,
		{"scrap_item": doc.scrap_item, "effective_from": doc.effective_from, "name": ["!=", doc.name]},
		"name",
	)
	if other:
		frappe.throw(
			_("{0} already has a rate from {1} ({2}). Change that row instead.").format(
				doc.scrap_item, frappe.format(doc.effective_from, {"fieldtype": "Date"}), other
			)
		)


# Weighment -----------------------------------------------------------------------------


def validate_weighment(doc):
	doc.net_kg = flt(doc.gross_kg) - flt(doc.tare_kg)
	if flt(doc.gross_kg) <= 0 or flt(doc.tare_kg) < 0:
		frappe.throw(_("Enter the gross weight, and a tare weight of zero or more."))
	if doc.net_kg <= 0:
		frappe.throw(
			_("Net weight must be more than zero (gross {0} kg - tare {1} kg).").format(
				flt(doc.gross_kg), flt(doc.tare_kg)
			),
			title=_("Net weight"),
		)
	if not doc.weighed_by:
		doc.weighed_by = frappe.session.user
	if doc.source == SOURCE_CSM:
		if not is_csm_scrap_item(doc.scrap_item):
			frappe.throw(_("For CSM scrap choose an item under {0}.").format(frappe.bold(CSM_SCRAP_GROUP)))
		if not doc.sales_order:
			frappe.throw(_("CSM scrap is weighed against its Sales Order. Fill in Sales Order."))
		if frappe.db.get_value("Sales Order", doc.sales_order, "docstatus") != 1:
			frappe.throw(_("Sales Order {0} must be submitted.").format(doc.sales_order))
		doc.rate_applied = 0
		doc.warehouse = scrap_warehouse(doc.company, csm_scrap=True)
	else:
		if not is_scrap_item(doc.scrap_item):
			frappe.throw(
				_("{0} is not a PEPL scrap item (Item Group under Scrap).").format(
					frappe.bold(doc.scrap_item)
				)
			)
		doc.sales_order = None
		rate = rate_on(doc.scrap_item, doc.weighment_date)
		if not rate:
			frappe.throw(
				_("No scrap rate for {0} on {1}. Add one in PEPL Scrap Rate.").format(
					frappe.bold(doc.scrap_item), frappe.format(doc.weighment_date, {"fieldtype": "Date"})
				),
				title=_("Scrap rate missing"),
			)
		doc.rate_applied = rate
		doc.warehouse = scrap_warehouse(doc.company)
	doc.amount = flt(doc.net_kg) * flt(doc.rate_applied)
	if doc.workshop:
		known = stock_tree.workshops()
		if known and doc.workshop not in known:
			frappe.throw(_("Workshop {0} is not in PEPL System Parameters > Workshops.").format(doc.workshop))


def _stock_entry(company, posting_date, purpose, lines, sales_order=None, remarks=None):
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": purpose,
			"purpose": purpose,
			"company": company,
			"set_posting_time": 1,
			"posting_date": posting_date,
			"custom_sales_order": sales_order,
			"remarks": remarks,
			"items": lines,
		}
	)
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	return entry.name


def on_submit_weighment(doc):
	csm_line = doc.source == SOURCE_CSM
	line = {"item_code": doc.scrap_item, "qty": doc.net_kg, "t_warehouse": doc.warehouse}
	if csm_line:
		line["allow_zero_valuation_rate"] = 1
	else:
		line["basic_rate"] = doc.rate_applied
	name = _stock_entry(
		doc.company,
		doc.weighment_date,
		"Material Receipt",
		[line],
		sales_order=doc.sales_order if csm_line else None,
		remarks=_("Scrap weighment {0}").format(doc.name),
	)
	doc.db_set("stock_entry", name)


def _cancel_entries(names):
	for name in names:
		if name and frappe.db.get_value("Stock Entry", name, "docstatus") == 1:
			entry = frappe.get_doc("Stock Entry", name)
			entry.flags.ignore_permissions = True
			entry.cancel()


def on_cancel_weighment(doc):
	_cancel_entries([doc.stock_entry])


# Sale ---------------------------------------------------------------------------------


def validate_sale(doc):
	if frappe.db.get_value("Customer", doc.buyer, "customer_group") != SCRAP_BUYERS:
		frappe.throw(
			_("Buyer {0} must be a Customer in the group {1}.").format(
				frappe.bold(doc.buyer), frappe.bold(SCRAP_BUYERS)
			)
		)
	if not doc.items:
		frappe.throw(_("Add at least one line."))
	total_kg = total_amount = 0.0
	for row in doc.items:
		csm_line = is_csm_scrap_item(row.scrap_item)
		if not (csm_line or is_scrap_item(row.scrap_item)):
			frappe.throw(_("Row {0}: {1} is not a scrap item.").format(row.idx, frappe.bold(row.scrap_item)))
		row.warehouse = row.warehouse or scrap_warehouse(doc.company, csm_scrap=csm_line)
		if not is_scrap_warehouse(row.warehouse):
			frappe.throw(
				_("Row {0}: sell scrap from Scrap Yard or CSM Scrap, not {1}.").format(row.idx, row.warehouse)
			)
		if flt(row.kg) <= 0:
			frappe.throw(_("Row {0}: enter the kg sold.").format(row.idx))
		if flt(row.rate) <= 0:
			frappe.throw(_("Row {0}: enter the rate per kg.").format(row.idx))
		if csm_line:
			check_csm_line(row)
		else:
			row.sales_order = None
		row.amount = flt(row.kg) * flt(row.rate)
		total_kg += flt(row.kg)
		total_amount += row.amount
	doc.total_kg = total_kg
	doc.total_amount = total_amount


def check_csm_line(row):
	"""Hard rule: customer-material scrap is sold only when its order says PEPL May Sell."""
	if not row.sales_order:
		frappe.throw(
			_("Row {0}: {1} is customer-material scrap. Fill in its Sales Order.").format(
				row.idx, frappe.bold(row.scrap_item)
			),
			title=_("Customer-material scrap"),
		)
	option = frappe.db.get_value("Sales Order", row.sales_order, csm.DISPOSITION_FIELD) or csm.HOLD
	if option != csm.PEPL_MAY_SELL:
		frappe.throw(
			_(
				"Row {0}: the scrap of Sales Order {1} is set to {2}. Customer-material scrap can be sold "
				"only when the order's CSM Scrap is {3}."
			).format(
				row.idx, frappe.bold(row.sales_order), frappe.bold(option), frappe.bold(csm.PEPL_MAY_SELL)
			),
			title=_("Customer-material scrap"),
		)


def on_submit_sale(doc):
	"""One Material Issue for the PEPL lines, and one per Sales Order for CSM lines."""
	groups = {}
	for row in doc.items:
		groups.setdefault(row.sales_order or "", []).append(row)
	names = []
	for order, rows in groups.items():
		name = _stock_entry(
			doc.company,
			doc.sale_date,
			"Material Issue",
			[{"item_code": r.scrap_item, "qty": r.kg, "s_warehouse": r.warehouse} for r in rows],
			sales_order=order or None,
			remarks=_("Scrap sale {0} to {1}").format(doc.name, doc.buyer_name or doc.buyer),
		)
		names.append(name)
		for r in rows:
			r.db_set("stock_entry", name)
	doc.db_set("stock_entries", ", ".join(names))


def on_cancel_sale(doc):
	_cancel_entries(sorted({r.stock_entry for r in doc.items if r.stock_entry}))


# Recovery report ------------------------------------------------------------------------


def _month(d):
	return getdate(d).strftime("%Y-%m")


def _rm_metal_map():
	"""Raw-material Item Group -> metal scrap group ('Brass' -> 'Brass Scrap')."""
	mapping = {}
	for g in frappe.get_all("PEPL RM Group", fields=["linked_item_group", "material_base"]):
		if g.linked_item_group and g.material_base:
			mapping[g.linked_item_group] = f"{g.material_base} Scrap"
	return mapping


def scrap_recovery(filters=None):
	filters = frappe._dict(filters or {})
	to_date = getdate(filters.get("to_date") or today())
	from_date = getdate(filters.get("from_date") or get_first_day(add_months(to_date, -5)))
	company = filters.get("company")
	rows = {}

	def row_for(month, metal):
		return rows.setdefault(
			(month, metal),
			frappe._dict(
				month=month,
				metal=metal,
				kg_generated=0.0,
				kg_sold=0.0,
				value_realised=0.0,
				master_value=0.0,
				rm_issued_kg=0.0,
			),
		)

	w_filters = {"docstatus": 1, "weighment_date": ["between", [from_date, to_date]]}
	s_filters = {"docstatus": 1, "sale_date": ["between", [from_date, to_date]]}
	if company:
		w_filters["company"] = company
		s_filters["company"] = company
	for w in frappe.get_all(WEIGHMENT, filters=w_filters, fields=["weighment_date", "scrap_item", "net_kg"]):
		row_for(_month(w.weighment_date), metal_of(w.scrap_item)).kg_generated += flt(w.net_kg)
	sales = frappe.get_all(SALE, filters=s_filters, fields=["name", "sale_date"])
	dates = {s.name: s.sale_date for s in sales}
	if dates:
		for line in frappe.get_all(
			"PEPL Scrap Sale Item",
			filters={"parent": ["in", list(dates)], "parenttype": SALE},
			fields=["parent", "scrap_item", "kg", "amount"],
		):
			sold_on = dates[line.parent]
			row = row_for(_month(sold_on), metal_of(line.scrap_item))
			row.kg_sold += flt(line.kg)
			row.value_realised += flt(line.amount)
			row.master_value += flt(line.kg) * flt(rate_on(line.scrap_item, sold_on) or 0)
	# Raw material issued from stores (not counting the WIP side of a transfer).
	rm_map = _rm_metal_map()
	if rm_map:
		conditions = ["sle.is_cancelled = 0", "sle.actual_qty < 0", "sle.voucher_type = 'Stock Entry'"]
		values = {"from": from_date, "to": to_date, "groups": list(rm_map)}
		conditions += ["sle.posting_date between %(from)s and %(to)s", "i.item_group in %(groups)s"]
		if company:
			conditions.append("sle.company = %(company)s")
			values["company"] = company
		issued = frappe.db.sql(
			f"""select sle.posting_date, i.item_group, sle.warehouse, -sle.actual_qty as qty
			from `tabStock Ledger Entry` sle join `tabItem` i on i.name = sle.item_code
			where {" and ".join(conditions)}""",
			values,
			as_dict=True,
		)
		wip = _wip_warehouses()
		for r in issued:
			if r.warehouse in wip:
				continue
			metal = rm_map[r.item_group]
			key = (_month(r.posting_date), metal)
			if key in rows:
				rows[key].rm_issued_kg += flt(r.qty)
	# Closing kg and value per metal at each month end (scrap warehouses only).
	result = []
	for key in sorted(rows):
		row = rows[key]
		month_end = min(get_last_day(getdate(row.month + "-01")), to_date)
		row.closing_kg, row.closing_value = _closing(row.metal, month_end, company)
		row.avg_realised_rate = row.value_realised / row.kg_sold if row.kg_sold else 0
		row.avg_master_rate = row.master_value / row.kg_sold if row.kg_sold else 0
		row.scrap_percent_of_rm = (row.kg_generated / row.rm_issued_kg * 100) if row.rm_issued_kg else None
		if filters.get("metal") and row.metal != filters.metal:
			continue
		result.append(row)
	return result


def _wip_warehouses():
	groups = frappe.get_all(
		"Warehouse", filters={"warehouse_name": stock_tree.WIP_GROUP, "is_group": 1}, fields=["lft", "rgt"]
	)
	names = set()
	for g in groups:
		names.update(
			frappe.get_all("Warehouse", filters={"lft": [">", g.lft], "rgt": ["<", g.rgt]}, pluck="name")
		)
	return names


def _metal_items(metal):
	if metal == CSM_SCRAP_GROUP:
		return frappe.get_all("Item", filters={"item_group": CSM_SCRAP_GROUP}, pluck="name")
	groups = [metal]
	lft, rgt = frappe.db.get_value("Item Group", metal, ["lft", "rgt"]) or (None, None)
	if lft:
		groups = frappe.get_all("Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")
	return frappe.get_all("Item", filters={"item_group": ["in", groups]}, pluck="name")


def _closing(metal, on_date, company=None):
	items = _metal_items(metal)
	if not items:
		return 0.0, 0.0
	scrap_stores = frappe.get_all(
		"Warehouse", filters={"warehouse_name": ["in", [SCRAP_YARD, CSM_SCRAP_GROUP]]}, pluck="name"
	)
	if not scrap_stores:
		return 0.0, 0.0
	conditions = "sle.is_cancelled = 0 and sle.item_code in %(items)s and sle.warehouse in %(stores)s and sle.posting_date <= %(on)s"
	values = {"items": items, "stores": scrap_stores, "on": on_date}
	if company:
		conditions += " and sle.company = %(company)s"
		values["company"] = company
	row = frappe.db.sql(
		f"select ifnull(sum(actual_qty), 0), ifnull(sum(stock_value_difference), 0) from `tabStock Ledger Entry` sle where {conditions}",
		values,
	)
	return flt(row[0][0]), flt(row[0][1])


@frappe.whitelist()
def get_rate(scrap_item, on_date=None):
	"""For the forms: today's (or that day's) scrap rate."""
	return rate_on(scrap_item, on_date)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def scrap_item_query(doctype, txt, searchfield, start, page_len, filters):
	"""Item picker: PEPL scrap items (under Scrap); with include_csm also the CSM Scrap items."""
	groups = [stock_tree.SCRAP]
	lft, rgt = frappe.db.get_value("Item Group", stock_tree.SCRAP, ["lft", "rgt"]) or (None, None)
	if lft:
		groups = frappe.get_all("Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")
	if (filters or {}).get("include_csm"):
		groups.append(CSM_SCRAP_GROUP)
	return frappe.db.sql(
		"""select name, item_name, item_group from `tabItem`
		where disabled = 0 and item_group in %(groups)s and (name like %(txt)s or item_name like %(txt)s)
		order by name limit %(start)s, %(page_len)s""",
		{"groups": groups, "txt": f"%{txt}%", "start": cint(start), "page_len": cint(page_len)},
	)
