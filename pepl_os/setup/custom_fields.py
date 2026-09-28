"""All Custom Fields owned by pepl_os, in one place.

Applied from after_install and after_migrate (idempotent), because Frappe
marks every patch as done without running it on a fresh install; a field
created only in a patch would be missing on new sites and in CI.

Each deliverable adds its fields to CUSTOM_FIELDS under the DocType it extends.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SYSTEM_PARAMETERS = "PEPL System Parameters"

# Last field of PEPL System Parameters as shipped by pepl_sales.
SYSTEM_PARAMETERS_LAST_FIELD = "material_receipt_alert_days"

OWNER_HELP = "Receives {0} alerts as ToDos. Falls back to Notification Fallback Owner when empty."

CUSTOM_FIELDS = {
	SYSTEM_PARAMETERS: [
		# F6 - PEPL OS tab and notification owners
		{
			"fieldname": "custom_pepl_os_tab",
			"label": "PEPL OS",
			"fieldtype": "Tab Break",
			"insert_after": SYSTEM_PARAMETERS_LAST_FIELD,
		},
		{
			"fieldname": "custom_owners_section",
			"label": "Notification Owners",
			"fieldtype": "Section Break",
			"insert_after": "custom_pepl_os_tab",
		},
		{
			"fieldname": "custom_purchase_notification_owner",
			"label": "Purchase Notification Owner",
			"fieldtype": "Link",
			"options": "User",
			"insert_after": "custom_owners_section",
			"description": OWNER_HELP.format("Purchase (chase list, supplier documents)"),
		},
		{
			"fieldname": "custom_stores_notification_owner",
			"label": "Stores Notification Owner",
			"fieldtype": "Link",
			"options": "User",
			"insert_after": "custom_purchase_notification_owner",
			"description": OWNER_HELP.format("Stores (reorder, cycle count, warranties)"),
		},
		{
			"fieldname": "custom_owners_column",
			"fieldtype": "Column Break",
			"insert_after": "custom_stores_notification_owner",
		},
		{
			"fieldname": "custom_production_notification_owner",
			"label": "Production Notification Owner",
			"fieldtype": "Link",
			"options": "User",
			"insert_after": "custom_owners_column",
			"description": OWNER_HELP.format("Production (missing BOM, job-work overdue)"),
		},
		{
			"fieldname": "custom_quality_notification_owner",
			"label": "Quality Notification Owner",
			"fieldtype": "Link",
			"options": "User",
			"insert_after": "custom_production_notification_owner",
			"description": OWNER_HELP.format("Quality (calibration due, CAPA verification)"),
		},
		# Work Package A - audit trail rules
		{
			"fieldname": "custom_audit_section",
			"label": "Audit Trail",
			"fieldtype": "Section Break",
			"insert_after": "custom_quality_notification_owner",
		},
		{
			"fieldname": "custom_enforce_delete_restriction",
			"label": "Restrict Delete to System Manager",
			"fieldtype": "Check",
			"default": "1",
			"insert_after": "custom_audit_section",
			"description": "When on, only the System Manager can delete transactions, masters and audit logs. "
			"Re-applied on every deploy.",
		},
		{
			"fieldname": "custom_audit_log_retention_days",
			"label": "Audit Log Retention (Days)",
			"fieldtype": "Int",
			"default": "1095",
			"insert_after": "custom_enforce_delete_restriction",
			"description": "Login history (Activity Log) and other audit logs that Frappe clears automatically "
			"are kept at least this many days. Frappe's own default for login history is 90 days.",
		},
	],
}


def apply_custom_fields():
	create_custom_fields(CUSTOM_FIELDS, update=True)
	for doctype in CUSTOM_FIELDS:
		frappe.clear_cache(doctype=doctype)
	seed_single_defaults()


def seed_single_defaults():
	"""Store the default of each new System Parameter once, so reads return it.

	A Single stores nothing until it is first saved, and an unsaved Check
	reads as 0, so defaults are written explicitly - only when no value exists.
	"""
	for field in CUSTOM_FIELDS[SYSTEM_PARAMETERS]:
		if "default" not in field:
			continue
		if frappe.db.exists("Singles", {"doctype": SYSTEM_PARAMETERS, "field": field["fieldname"]}):
			continue
		frappe.db.set_single_value(SYSTEM_PARAMETERS, field["fieldname"], field["default"])
