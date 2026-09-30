"""A2 - Role Access Matrix: what each PEPL Role Profile can do on each record.

Read live from the site (Custom DocPerm when present, else standard DocPerm),
so the matrix is always what the software really enforces today, including
the delete restriction and any change made in Role Permission Manager.
"""

import frappe

from pepl_os.common.rights import RIGHTS, combine, summarise
from pepl_os.setup.permissions import perm_rows
from pepl_os.setup.roles import ROLE_PROFILES

# (Area, DocType, name PEPL uses). Order is the order PEPL reads the sheet.
MATRIX_DOCTYPES = (
	("Masters", "Item", "Item (materials and products)"),
	("Masters", "Supplier", "Supplier"),
	("Masters", "Customer", "Customer"),
	("Masters", "Warehouse", "Warehouse / store location"),
	("Masters", "Item Price", "Item Price"),
	("Masters", "BOM", "Bill of Materials (BOM)"),
	("Sales", "PEPL Tender", "Tender"),
	("Sales", "PEPL CST Cost Sheet", "Cost Sheet (CST)"),
	("Sales", "Quotation", "Quotation"),
	("Sales", "Sales Order", "Sales Order"),
	("Sales", "Delivery Note", "Delivery Note (dispatch)"),
	("Sales", "Sales Invoice", "Sales Invoice"),
	("Sales", "PEPL Document Tracker", "Document Tracker"),
	("Sales", "PEPL Payment Tracker", "Payment Tracker"),
	("Sales", "PEPL PSD Tracker", "PSD / BG Tracker"),
	("Engineering", "PEPL Product Master", "Product Master (drawings, specs)"),
	("Engineering", "Vendor Approval Status", "Vendor Approval Status"),
	("Purchase", "PEPL Supplier Approval", "Supplier Approval"),
	("Purchase", "Material Request", "Material Request (indent)"),
	("Purchase", "Request for Quotation", "Request for Quotation"),
	("Purchase", "Supplier Quotation", "Supplier Quotation"),
	("Purchase", "PEPL Quotation Comparison", "Quotation Comparison"),
	("Purchase", "Purchase Order", "Purchase Order"),
	("Purchase", "PEPL Purchase Tracker", "Purchase Tracker"),
	("Purchase", "Purchase Invoice", "Purchase Invoice (bill)"),
	("Stores", "Purchase Receipt", "Purchase Receipt (GRN)"),
	("Stores", "Stock Entry", "Stock Entry (issue / transfer)"),
	("Stores", "Stock Reconciliation", "Stock count correction"),
	("Stores", "PEPL Capital Equipment", "Capital Equipment Register"),
	("Production", "Work Order", "Job Order"),
	("Production", "Job Card", "Job Card"),
	("Production", "Production Plan", "Production Plan"),
	("Production", "Workstation", "Machine (Workstation)"),
	("Quality", "Quality Inspection", "Quality Inspection"),
	("Accounts", "Payment Entry", "Payment Entry"),
	("Accounts", "Journal Entry", "Journal Entry"),
	("Accounts", "PEPL Company Document", "Company Documents (PAN, GST, Udyam)"),
)

AREAS = tuple(dict.fromkeys(area for area, _dt, _label in MATRIX_DOCTYPES))


def pepl_profiles():
	"""PEPL profiles on this site: the seeded ones first, then any PEPL adds by hand."""
	on_site = set(frappe.get_all("Role Profile", filters={"name": ["like", "PEPL%"]}, pluck="name"))
	seeded = [p for p in ROLE_PROFILES if p in on_site]
	return seeded + sorted(on_site - set(seeded))


def profile_roles(profile):
	return frappe.get_all("Has Role", filters={"parent": profile, "parenttype": "Role Profile"}, pluck="role")


def get_rows(filters=None):
	filters = frappe._dict(filters or {})
	profiles = [filters.role_profile] if filters.get("role_profile") else pepl_profiles()
	doctypes = [d for d in MATRIX_DOCTYPES if frappe.db.exists("DocType", d[1])]
	if filters.get("area"):
		doctypes = [d for d in doctypes if d[0] == filters.area]

	perms = {dt: perm_rows(dt) for _area, dt, _label in doctypes}
	rows = []
	for profile in profiles:
		roles = profile_roles(profile)
		for area, doctype, label in doctypes:
			rights = combine(perms[doctype], roles)
			if filters.get("only_with_access") and not rights["read"] and not rights["create"]:
				continue
			rows.append(
				{
					"role_profile": profile,
					"area": area,
					"document": label,
					"doctype": doctype,
					"in_plain_words": summarise(rights),
					**rights,
				}
			)
	return rows


def rights_for(profile, doctype):
	"""Convenience for tests and other modules."""
	return combine(perm_rows(doctype), profile_roles(profile))


__all__ = ["AREAS", "MATRIX_DOCTYPES", "RIGHTS", "get_rows", "pepl_profiles", "rights_for"]
