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


def make_item(item_code, item_group, is_stock_item=1, **fields):
	"""An Item in the given group (UOM Nos). Returns the existing one if it is already there."""
	ensure_test_masters()
	if frappe.db.exists("Item", item_code):
		return frappe.get_doc("Item", item_code)
	return frappe.get_doc(
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


def make_file(file_name, content=None):
	"""A private File, for Attach fields. Returns its file_url."""
	return (
		frappe.get_doc(
			{"doctype": "File", "file_name": file_name, "content": content or blank_pdf(), "is_private": 1}
		)
		.insert(ignore_permissions=True)
		.file_url
	)
