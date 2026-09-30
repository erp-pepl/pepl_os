"""Where an item is normally stored, per company (Item default, else its Item Group default)."""

import frappe


def default_store(item_code, company):
	for parenttype, parent in (
		("Item", item_code),
		("Item Group", frappe.get_cached_value("Item", item_code, "item_group")),
	):
		if not parent:
			continue
		warehouse = frappe.db.get_value(
			"Item Default",
			{"parenttype": parenttype, "parent": parent, "company": company},
			"default_warehouse",
		)
		if warehouse:
			return warehouse
	return frappe.db.get_single_value("Stock Settings", "default_warehouse")


def bin_quantities(item_code, warehouse):
	"""On hand, reserved, on order and requested for one item in one store."""
	row = frappe.db.get_value(
		"Bin",
		{"item_code": item_code, "warehouse": warehouse},
		["actual_qty", "reserved_qty", "ordered_qty", "indented_qty", "projected_qty"],
		as_dict=True,
	)
	return row or frappe._dict(actual_qty=0, reserved_qty=0, ordered_qty=0, indented_qty=0, projected_qty=0)
