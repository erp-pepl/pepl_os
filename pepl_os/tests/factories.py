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
