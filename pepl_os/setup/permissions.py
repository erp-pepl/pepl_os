"""A2 / A5 - Delete rights restricted to the System Manager.

Applied on install and on every migrate, so a delete right re-granted by
hand in Role Permission Manager is removed again at the next deploy. Other
rights (read, write, submit, cancel, amend) are never touched.

Note: the first change on a DocType copies its standard permissions into
Custom DocPerm (exactly what Role Permission Manager does); from then on
that DocType's permissions are managed as customisations.
"""

import frappe
from frappe.permissions import update_permission_property

ALLOWED_TO_DELETE = {"System Manager", "Administrator"}

# Transactions and masters in operational use.
CORE_DOCTYPES = (
	"Item",
	"Supplier",
	"Customer",
	"Warehouse",
	"BOM",
	"Quotation",
	"Sales Order",
	"Delivery Note",
	"Sales Invoice",
	"Material Request",
	"Request for Quotation",
	"Supplier Quotation",
	"Purchase Order",
	"Purchase Receipt",
	"Purchase Invoice",
	"Stock Entry",
	"Stock Reconciliation",
	"Payment Entry",
	"Journal Entry",
	"Work Order",
	"Job Card",
	"Quality Inspection",
)

# A5 - the audit trail itself.
LOG_DOCTYPES = (
	"Version",
	"Activity Log",
	"Access Log",
	"Deleted Document",
	"View Log",
	"PEPL Override Log",
	"PEPL Job Run",
)

PEPL_MODULES = (
	"PEPL Sales",
	"PEPL Governance",
	"PEPL Purchase",
	"PEPL Stores",
	"PEPL Production",
	"PEPL Quality",
	"PEPL People",
	"PEPL Tally Mirror",
)


def pepl_doctypes():
	"""Every non-child, non-single DocType of pepl_sales and pepl_os."""
	return frappe.get_all(
		"DocType",
		filters={"module": ["in", PEPL_MODULES], "istable": 0, "issingle": 0},
		pluck="name",
	)


def delete_restricted_doctypes():
	names = [*CORE_DOCTYPES, *LOG_DOCTYPES, *pepl_doctypes()]
	seen = set()
	return [d for d in names if not (d in seen or seen.add(d)) and frappe.db.exists("DocType", d)]


def perm_rows(doctype):
	"""Effective permission rows: Custom DocPerm when present, else DocPerm."""
	table = "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": doctype}) else "DocPerm"
	return frappe.get_all(
		table,
		filters={"parent": doctype},
		fields=["role", "permlevel", "delete"],
	)


def roles_with_delete(doctype):
	return sorted({r.role for r in perm_rows(doctype) if r.delete and r.role not in ALLOWED_TO_DELETE})


def enforcement_enabled():
	from pepl_os.common import params

	return params.is_enabled("custom_enforce_delete_restriction", 1)


def restrict_delete(doctypes=None, force=False):
	"""Remove delete from every role except System Manager. Returns what changed.

	Skipped when "Restrict Delete to System Manager" is switched off in
	PEPL System Parameters (unless force=True, used by tests).
	"""
	changed = {}
	if not (force or enforcement_enabled()):
		return changed
	for doctype in doctypes or delete_restricted_doctypes():
		offenders = [r for r in perm_rows(doctype) if r.delete and r.role not in ALLOWED_TO_DELETE]
		if not offenders:
			continue
		for row in offenders:
			update_permission_property(doctype, row.role, row.permlevel, "delete", 0, validate=False)
		changed[doctype] = sorted({r.role for r in offenders})
		frappe.clear_cache(doctype=doctype)
	return changed
