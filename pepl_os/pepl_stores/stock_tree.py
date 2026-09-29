"""C2-04 - The PEPL stock classes, their stores, and the rules that keep them apart.

Item Group tree (under the root "All Item Groups"):
  Raw Material                 children: each PEPL RM Group of a metal / raw base
  Bought-Out Components        children: RM Groups of bought-out bases
  Consumables                  children: RM Groups of consumable bases
  Tools & Gauges               children: RM Groups of tooling bases
  WIP / Semi-Finished
  Finished Goods
  Scrap                        children: Brass / Steel / Copper / Aluminium Scrap
  Customer-Supplied Material   (CSM: zero value, own stores)
  Capital Equipment            (never stock; see PEPL Capital Equipment)

Seeding is additive and safe to repeat: it creates what is missing, fills
empty Item Group defaults, and moves an RM Group's Item Group only while it
still sits directly under "Raw Material" or the root (where pepl_sales puts
it). A group PEPL has moved by hand is left where it is.
"""

import frappe
from frappe import _
from frappe.utils import cstr
from frappe.utils.nestedset import get_root_of

RAW_MATERIAL = "Raw Material"
BOUGHT_OUT = "Bought-Out Components"
CONSUMABLES = "Consumables"
TOOLS = "Tools & Gauges"
WIP = "WIP / Semi-Finished"
FINISHED_GOODS = "Finished Goods"
SCRAP = "Scrap"
CSM = "Customer-Supplied Material"
CAPITAL = "Capital Equipment"

STOCK_CLASSES = (RAW_MATERIAL, BOUGHT_OUT, CONSUMABLES, TOOLS, WIP, FINISHED_GOODS, SCRAP, CSM, CAPITAL)
SCRAP_CHILDREN = ("Brass Scrap", "Steel Scrap", "Copper Scrap", "Aluminium Scrap")

# PEPL RM Group.material_base -> the class its Item Group belongs under.
# Bases not listed (Process Service, Other) are services or undecided and stay where they are.
MATERIAL_BASE_CLASS = {
	"Brass": RAW_MATERIAL,
	"Steel": RAW_MATERIAL,
	"Aluminium": RAW_MATERIAL,
	"Copper": RAW_MATERIAL,
	"Plastic-Rubber": RAW_MATERIAL,
	"Plastic": RAW_MATERIAL,
	"Forgings": RAW_MATERIAL,
	"Castings": RAW_MATERIAL,
	"Bought Out": BOUGHT_OUT,
	"Bought-out Components": BOUGHT_OUT,
	"Hardware": BOUGHT_OUT,
	"Hardware and Fasteners": BOUGHT_OUT,
	"Electrical": BOUGHT_OUT,
	"Consumable": CONSUMABLES,
	"Packaging": CONSUMABLES,
	"Tooling": TOOLS,
	"Tool": TOOLS,
	"Inspection": TOOLS,
	"Capital": CAPITAL,
	"IT Hardware": CAPITAL,
}

# Warehouses (warehouse_name) created under each company. WIP stores are added
# per workshop from System Parameters; CSM stores sit in their own group.
LEAF_STORES = (
	"RM Stores",
	"Bought-Out Stores",
	"Consumables Stores",
	"Tool Room",
	"FG Stores",
	"Scrap Yard",
	"QC Hold",
	"Rejected",
)
WIP_GROUP = "WIP"
CSM_GROUP = "CSM"
CSM_STORES = ("CSM Stores", "CSM Scrap")

CLASS_DEFAULT_STORE = {
	RAW_MATERIAL: "RM Stores",
	BOUGHT_OUT: "Bought-Out Stores",
	CONSUMABLES: "Consumables Stores",
	TOOLS: "Tool Room",
	FINISHED_GOODS: "FG Stores",
	SCRAP: "Scrap Yard",
	CSM: "CSM Stores",
	# WIP: the first workshop's WIP store (see default_store_for)
	# CAPITAL: none, capital equipment is not stock
}

# Warehouse fields on the item rows of stock transactions.
ROW_WAREHOUSE_FIELDS = (
	"warehouse",
	"s_warehouse",
	"t_warehouse",
	"rejected_warehouse",
	"from_warehouse",
	"target_warehouse",
)


# Item Group tree ----------------------------------------------------------


def root_item_group():
	return get_root_of("Item Group") or _("All Item Groups")


def _ensure_item_group(name, parent, is_group=1):
	if frappe.db.exists("Item Group", name):
		doc = frappe.get_doc("Item Group", name)
		changed = False
		if is_group and not doc.is_group:
			doc.is_group = 1
			changed = True
		if changed:
			doc.save(ignore_permissions=True)
		return doc
	return frappe.get_doc(
		{"doctype": "Item Group", "item_group_name": name, "parent_item_group": parent, "is_group": is_group}
	).insert(ignore_permissions=True)


def seed_item_groups():
	"""Create the class tree and place each RM Group's Item Group. Returns what moved."""
	root = root_item_group()
	if not frappe.db.exists("Item Group", root):
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": root, "is_group": 1, "parent_item_group": ""}
		).insert(ignore_permissions=True)

	for name in STOCK_CLASSES:
		doc = _ensure_item_group(name, root)
		if doc.parent_item_group != root and stock_class_of(doc.name) is None:
			# A class name used somewhere outside the tree: bring it to the top.
			doc.parent_item_group = root
			doc.save(ignore_permissions=True)
	for name in SCRAP_CHILDREN:
		_ensure_item_group(name, SCRAP, is_group=0)

	moved = {}
	for rm in frappe.get_all(
		"PEPL RM Group",
		filters={"linked_item_group": ["is", "set"]},
		fields=["linked_item_group", "material_base"],
	):
		target = MATERIAL_BASE_CLASS.get(rm.material_base)
		if not target or not frappe.db.exists("Item Group", rm.linked_item_group):
			continue
		group = frappe.get_doc("Item Group", rm.linked_item_group)
		if group.name in STOCK_CLASSES or group.parent_item_group == target:
			continue
		if group.parent_item_group not in (root, RAW_MATERIAL):
			continue  # moved by hand: respect it
		group.parent_item_group = target
		group.save(ignore_permissions=True)
		moved[group.name] = target
	return moved


def _top_groups():
	"""{name: (lft, rgt)} of the class groups that exist."""
	rows = frappe.get_all(
		"Item Group", filters={"name": ["in", STOCK_CLASSES]}, fields=["name", "lft", "rgt"]
	)
	return {r.name: (r.lft, r.rgt) for r in rows}


def stock_class_of(item_group):
	"""The PEPL stock class an Item Group belongs to, or None when it is outside the tree."""
	if not item_group:
		return None
	row = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=True)
	if not row:
		return None
	root = root_item_group()
	for name, (lft, rgt) in _top_groups().items():
		if lft <= row.lft and row.rgt <= rgt:
			if frappe.db.get_value("Item Group", name, "parent_item_group") == root:
				return name
	return None


def groups_in_class(stock_class):
	lft, rgt = frappe.db.get_value("Item Group", stock_class, ["lft", "rgt"])
	return frappe.get_all("Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")


# Warehouses ---------------------------------------------------------------


def workshops():
	from pepl_os.common import params

	lines = cstr(params.get("custom_workshops") or "Main Workshop").splitlines()
	names = [line.strip() for line in lines if line.strip()]
	return names or ["Main Workshop"]


def _company_root_warehouse(company):
	return frappe.db.get_value(
		"Warehouse",
		{"company": company, "is_group": 1, "parent_warehouse": ["is", "not set"]},
		"name",
	) or frappe.db.get_value("Warehouse", {"company": company, "is_group": 1}, "name", order_by="lft asc")


def warehouse_name(company, store):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	return f"{store} - {abbr}"


def _ensure_warehouse(company, store, parent, is_group=0):
	name = frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store}, "name")
	if name:
		return name
	return (
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": store,
				"company": company,
				"parent_warehouse": parent,
				"is_group": is_group,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def seed_warehouses(company):
	"""Create PEPL's stores under the company. Returns {store: warehouse name}."""
	root = _company_root_warehouse(company)
	if not root:
		return {}
	made = {store: _ensure_warehouse(company, store, root) for store in LEAF_STORES}
	wip = _ensure_warehouse(company, WIP_GROUP, root, is_group=1)
	for shop in workshops():
		made[f"WIP {shop}"] = _ensure_warehouse(company, f"WIP {shop}", wip)
	csm = _ensure_warehouse(company, CSM_GROUP, root, is_group=1)
	for store in CSM_STORES:
		made[store] = _ensure_warehouse(company, store, csm)
	return made


def default_store_for(stock_class):
	if stock_class == WIP:
		return f"WIP {workshops()[0]}"
	return CLASS_DEFAULT_STORE.get(stock_class)


def set_item_group_defaults(company):
	"""Give every Item Group in a class its default store for this company. Fills only empty ones."""
	changed = []
	for stock_class in STOCK_CLASSES:
		store = default_store_for(stock_class)
		if not store or not frappe.db.exists("Item Group", stock_class):
			continue
		warehouse = frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store}, "name")
		if not warehouse:
			continue
		for group_name in groups_in_class(stock_class):
			group = frappe.get_doc("Item Group", group_name)
			if any(d.company == company for d in group.item_group_defaults):
				continue
			group.append("item_group_defaults", {"company": company, "default_warehouse": warehouse})
			group.save(ignore_permissions=True)
			changed.append(group_name)
	return changed


def default_company():
	return frappe.defaults.get_global_default("company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def seed_stock_structure(company=None):
	"""The whole C2-04 seed. Called from after_migrate; safe to repeat."""
	seed_item_groups()
	company = company or default_company()
	if company and frappe.db.exists("Company", company):
		seed_warehouses(company)
		set_item_group_defaults(company)


# Rules --------------------------------------------------------------------


def validate_item(doc, method=None):
	"""Item validate: set the stock class; Capital is never stock; CSM is customer-provided."""
	stock_class = stock_class_of(doc.item_group)
	doc.custom_stock_class = stock_class

	if stock_class == CAPITAL:
		doc.is_stock_item = 0

	if stock_class == CSM:
		# ERPNext then gives every receipt of it a zero valuation rate.
		doc.is_customer_provided_item = 1
		doc.is_purchase_item = 0
		doc.valuation_rate = 0
		doc.default_material_request_type = "Customer Provided"
	elif doc.is_customer_provided_item:
		frappe.throw(
			_("A customer-provided item must be in the Item Group {0}.").format(frappe.bold(CSM)),
			title=_("Stock class"),
		)

	if doc.is_stock_item and not stock_class:
		if frappe.flags.pepl_allow_items_outside_tree:
			return  # only while ERPNext builds its standard test data (tests/bootstrap.py)
		group_changed = doc.is_new() or doc.has_value_changed("item_group")
		message = _(
			"Item Group {0} is outside the PEPL stock classes. Choose a group under one of: {1}."
		).format(frappe.bold(doc.item_group), ", ".join(STOCK_CLASSES))
		if group_changed:
			frappe.throw(message, title=_("Stock class"))
		frappe.msgprint(message, indicator="orange", alert=True)


def _is_csm_item(item_code):
	values = frappe.get_cached_value("Item", item_code, ["is_customer_provided_item", "item_group"])
	if not values:
		return False
	provided, group = values
	return bool(provided) or stock_class_of(group) == CSM


def _csm_bounds(company):
	return frappe.db.get_value(
		"Warehouse", {"company": company, "warehouse_name": CSM_GROUP, "is_group": 1}, ["lft", "rgt"]
	)


def is_csm_warehouse(warehouse):
	row = frappe.get_cached_value("Warehouse", warehouse, ["company", "lft", "rgt"])
	if not row:
		return False
	company, lft, rgt = row
	bounds = _csm_bounds(company)
	return bool(bounds) and bounds[0] <= lft and rgt <= bounds[1]


def validate_csm_segregation(doc, method=None):
	"""Stock Entry / Purchase Receipt / Delivery Note: CSM and PEPL stock never share a store.

	A hard rule, not overridable: mixing them would put customer material into
	PEPL's stock value (or the reverse).
	"""
	errors = []
	for row in doc.get("items") or []:
		if not row.get("item_code"):
			continue
		csm_item = _is_csm_item(row.item_code)
		for field in ROW_WAREHOUSE_FIELDS:
			warehouse = row.get(field)
			if not warehouse:
				continue
			csm_store = is_csm_warehouse(warehouse)
			if csm_item and not csm_store:
				errors.append(
					_(
						"Row {0}: {1} is customer-supplied material and can only be in a CSM store, not {2}."
					).format(row.idx, frappe.bold(row.item_code), frappe.bold(warehouse))
				)
			elif csm_store and not csm_item:
				errors.append(
					_("Row {0}: {1} is PEPL material and cannot be put in the CSM store {2}.").format(
						row.idx, frappe.bold(row.item_code), frappe.bold(warehouse)
					)
				)
	if errors:
		frappe.throw("<br>".join(errors), title=_("Customer-supplied material"))
