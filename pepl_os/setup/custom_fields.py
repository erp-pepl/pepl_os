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
	],
}


def apply_custom_fields():
	create_custom_fields(CUSTOM_FIELDS, update=True)
	for doctype in CUSTOM_FIELDS:
		frappe.clear_cache(doctype=doctype)
