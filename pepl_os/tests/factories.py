"""Test data factories shared by every pepl_os test.

The CI site is a bare install: ERPNext is installed but its setup wizard has
not run, so masters such as UOM, Item Group, Company and Warehouse do not
exist. Every test that needs master data gets it from here, created once and
idempotently. Never create a record directly in a test if it links to a
master; add (or reuse) a factory instead.

Frappe fills empty fields with their DocType default before saving, so a
link left empty in a test can still point at a master that must exist.
"""

import frappe

# Units referenced by defaults of PEPL and ERPNext DocTypes used in tests.
TEST_UOMS = ("Kg", "Nos")


def ensure_uom(uom_name):
	if not frappe.db.exists("UOM", uom_name):
		frappe.get_doc({"doctype": "UOM", "uom_name": uom_name}).insert(ignore_permissions=True)
	return uom_name


def ensure_test_masters():
	for uom in TEST_UOMS:
		ensure_uom(uom)


def make_rm_group(name, material_base="Brass", wastage=5):
	"""A PEPL RM Group: a change-tracked PEPL record with a single master link (UOM)."""
	ensure_test_masters()
	if frappe.db.exists("PEPL RM Group", name):
		return frappe.get_doc("PEPL RM Group", name)
	return frappe.get_doc(
		{
			"doctype": "PEPL RM Group",
			"group_name": name,
			"material_base": material_base,
			"default_uom": "Kg",
			"typical_wastage_percent": wastage,
			"is_active": 1,
			"auto_sync_to_item_group": 0,
		}
	).insert(ignore_permissions=True)


# Cycle 2 ------------------------------------------------------------------
# These need ERPNext's standard test data (tests/bootstrap.py builds it before the suite).

TEST_COMPANY = "_Test Company"
TEST_SUPPLIER_GROUP = "_Test Supplier Group"


def make_item(item_code, item_group, is_stock_item=1, heat_tracked=None, **fields):
	"""An Item in the given group (UOM Nos). Returns the existing one if it is already there.

	New raw material is heat-tracked with Batch = heat (C2-15). Pass heat_tracked=False
	for a plain raw-material item in tests that are not about heat numbers.
	"""
	ensure_test_masters()
	if frappe.db.exists("Item", item_code):
		return frappe.get_doc("Item", item_code)
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_code,
			"item_group": item_group,
			"stock_uom": "Nos",
			"is_stock_item": is_stock_item,
			**fields,
		}
	).insert(ignore_permissions=True)
	if heat_tracked is False:
		frappe.db.set_value("Item", item.name, {"custom_heat_tracked": 0, "has_batch_no": 0})
		frappe.clear_document_cache("Item", item.name)
		item.reload()
	return item


def make_supplier(name, **fields):
	return frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": name,
			"supplier_group": TEST_SUPPLIER_GROUP,
			**fields,
		}
	)


def blank_pdf():
	"""A real one-page PDF. Frappe opens every uploaded PDF to check it for scripts,
	so a file that only looks like a PDF is refused."""
	from io import BytesIO

	from pypdf import PdfWriter

	writer = PdfWriter()
	writer.add_blank_page(width=72, height=72)
	out = BytesIO()
	writer.write(out)
	return out.getvalue()


def blank_png():
	"""A real 1 x 1 PNG, for Attach Image fields (e.g. the tool-change photo)."""
	import base64

	return base64.b64decode(
		"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
	)


def make_file(file_name, content=None):
	"""A private File, for Attach fields. Returns its file_url."""
	return (
		frappe.get_doc(
			{"doctype": "File", "file_name": file_name, "content": content or blank_pdf(), "is_private": 1}
		)
		.insert(ignore_permissions=True)
		.file_url
	)


# Cycle 3a ------------------------------------------------------------------


def make_workstation_type(name):
	"""A machine group (ERPNext Workstation Type)."""
	if not frappe.db.exists("Workstation Type", name):
		frappe.get_doc({"doctype": "Workstation Type", "workstation_type": name}).insert(
			ignore_permissions=True
		)
	return name


def make_workstation(name, workstation_type=None, **fields):
	"""A machine (ERPNext Workstation), optionally in a machine group."""
	if frappe.db.exists("Workstation", name):
		return frappe.get_doc("Workstation", name)
	if workstation_type:
		make_workstation_type(workstation_type)
	return frappe.get_doc(
		{"doctype": "Workstation", "workstation_name": name, "workstation_type": workstation_type, **fields}
	).insert(ignore_permissions=True)


def make_shift(name, start="08:00:00", end="16:30:00", break_minutes=30):
	if frappe.db.exists("PEPL Shift", name):
		return frappe.get_doc("PEPL Shift", name)
	return frappe.get_doc(
		{
			"doctype": "PEPL Shift",
			"shift_name": name,
			"start_time": start,
			"end_time": end,
			"break_minutes": break_minutes,
		}
	).insert(ignore_permissions=True)


def make_downtime_category(name, stop_type="Unplanned", is_breakdown=0):
	if frappe.db.exists("PEPL Downtime Category", name):
		return frappe.get_doc("PEPL Downtime Category", name)
	return frappe.get_doc(
		{
			"doctype": "PEPL Downtime Category",
			"category_name": name,
			"stop_type": stop_type,
			"is_breakdown": is_breakdown,
		}
	).insert(ignore_permissions=True)


def make_operator(code, name=None, pin="1234", skills=(), **fields):
	"""A shop-floor operator. skills: [(machine group, level), ...] or dicts for full rows."""
	if frappe.db.exists("PEPL Operator", code):
		return frappe.get_doc("PEPL Operator", code)
	doc = frappe.get_doc(
		{
			"doctype": "PEPL Operator",
			"employee_code": code,
			"operator_name": name or f"Operator {code}",
			"pin": pin,
			**fields,
		}
	)
	for skill in skills:
		row = skill if isinstance(skill, dict) else {"workstation_type": skill[0], "level": skill[1]}
		make_workstation_type(row["workstation_type"])
		doc.append("skills", row)
	return doc.insert(ignore_permissions=True)


def test_warehouse(store, company=TEST_COMPANY):
	"""A PEPL store of the test company by its short name, e.g. "Consumables Stores"."""
	return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store}, "name")


def make_operation(name, workstation):
	if not frappe.db.exists("Operation", name):
		frappe.get_doc({"doctype": "Operation", "name": name, "workstation": workstation}).insert(
			ignore_permissions=True
		)
	return name


def make_job_card(workstation, prefix, qty=10, minutes_per_piece=6):
	"""A real ERPNext Job Card on `workstation`: FG + RM items, an operation, a BOM with that operation,
	and a submitted Work Order (ERPNext creates the Job Card on submit). Returns the Job Card (draft).

	Capacity planning is switched off for the test, so the Job Card has no planned time slots.
	"""
	from frappe.utils import now

	from pepl_os.pepl_stores import stock_tree as st
	from pepl_os.tests.utils import set_single

	set_single("Manufacturing Settings", "disable_capacity_planning", 1)
	fg = make_item(f"{prefix}-FG", st.FINISHED_GOODS).name
	rm = make_item(f"{prefix}-RM", st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10).name
	bom = make_bom(fg, rm, workstation, f"{prefix} Turning", minutes_per_piece)
	work_order = frappe.get_doc(
		{
			"doctype": "Work Order",
			"production_item": fg,
			"bom_no": bom.name,
			"qty": qty,
			"stock_uom": "Nos",
			"company": TEST_COMPANY,
			"skip_transfer": 1,
			"fg_warehouse": test_warehouse("FG Stores"),
			"planned_start_date": now(),
			"transfer_material_against": "Work Order",
		}
	)
	work_order.get_items_and_operations_from_bom()
	work_order.insert(ignore_permissions=True)
	work_order.submit()
	name = frappe.get_all("Job Card", filters={"work_order": work_order.name}, pluck="name")[0]
	return frappe.get_doc("Job Card", name)


def make_bom(fg, rm, workstation=None, operation=None, minutes_per_piece=6, rm_qty=1):
	"""A submitted default BOM: rm_qty x rm per piece, with one operation on `workstation` when given."""
	values = {
		"doctype": "BOM",
		"item": fg,
		"company": TEST_COMPANY,
		"currency": frappe.get_cached_value("Company", TEST_COMPANY, "default_currency"),
		"quantity": 1,
		"is_active": 1,
		"is_default": 1,
		"items": [{"item_code": rm, "qty": rm_qty, "rate": 10}],
	}
	if workstation:
		make_operation(operation or f"{fg} Op", workstation)
		values["with_operations"] = 1
		values["operations"] = [
			{
				"operation": operation or f"{fg} Op",
				"workstation": workstation,
				"time_in_mins": minutes_per_piece,
			}
		]
	bom = frappe.get_doc(values).insert(ignore_permissions=True)
	bom.submit()
	return bom


def make_work_order(item, qty, planned_start, submit=True):
	"""A Job Order (Work Order) for `item` from its default BOM, starting at `planned_start`."""
	work_order = frappe.get_doc(
		{
			"doctype": "Work Order",
			"production_item": item,
			"bom_no": frappe.db.get_value("BOM", {"item": item, "is_default": 1, "docstatus": 1}),
			"qty": qty,
			"stock_uom": "Nos",
			"company": TEST_COMPANY,
			"skip_transfer": 1,
			"fg_warehouse": test_warehouse("FG Stores"),
			"planned_start_date": planned_start,
			"transfer_material_against": "Work Order",
		}
	)
	work_order.get_items_and_operations_from_bom()
	work_order.insert(ignore_permissions=True)
	if submit:
		work_order.submit()
	return work_order


def make_production_plan(rows, submit=False):
	"""A Production Plan of the test company; rows are (item_code, qty, planned_start)."""
	from frappe.utils import today

	plan = frappe.get_doc(
		{
			"doctype": "Production Plan",
			"company": TEST_COMPANY,
			"posting_date": today(),
			"po_items": [
				{
					"item_code": code,
					"bom_no": frappe.db.get_value("BOM", {"item": code, "is_default": 1, "docstatus": 1}),
					"planned_qty": qty,
					"planned_start_date": start,
					"stock_uom": "Nos",
					"warehouse": test_warehouse("FG Stores"),
				}
				for code, qty, start in rows
			],
		}
	).insert(ignore_permissions=True)
	if submit:
		plan.submit()
	return plan


def make_delivery_note(sales_order, qty_by_item, submit=False):
	"""A Delivery Note from a submitted Sales Order (ERPNext's own mapping), for the given quantities."""
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note as map_delivery_note

	dn = map_delivery_note(sales_order)
	dn.items = [row for row in dn.items if row.item_code in qty_by_item]
	for row in dn.items:
		row.qty = qty_by_item[row.item_code]
	dn.insert(ignore_permissions=True)
	if submit:
		dn.submit()
	return dn


TEST_CUSTOMER = "_Test Customer"


def make_sales_order(lines, submit=False, delivery_days=10):
	"""A Sales Order of the test company; lines are (item_code, qty), shipped from FG Stores."""
	from frappe.utils import add_days, today

	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": TEST_CUSTOMER,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"delivery_date": add_days(today(), delivery_days),
			"custom_sector": "Private",
			"items": [
				{
					"item_code": code,
					"qty": qty,
					"rate": 100,
					"warehouse": test_warehouse("FG Stores"),
					"delivery_date": add_days(today(), delivery_days),
				}
				for code, qty in lines
			],
		}
	).insert(ignore_permissions=True)
	if submit:
		so.submit()
	return so


def make_spr(
	workstation, shift, operator, posting_date=None, production=(), downtime=(), tools=(), consumables=()
):
	"""An unsaved Shift Production Entry. Rows are dicts in the field names of each table."""
	from frappe.utils import today

	doc = frappe.get_doc(
		{
			"doctype": "PEPL Shift Production Entry",
			"posting_date": posting_date or today(),
			"shift": shift,
			"workstation": workstation,
			"operator": operator,
			"company": TEST_COMPANY,
		}
	)
	for table, rows in (
		("production", production),
		("downtime", downtime),
		("tool_changes", tools),
		("consumables", consumables),
	):
		for row in rows:
			doc.append(table, row)
	return doc
