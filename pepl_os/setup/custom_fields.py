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

PEPL_VALUE = "Entered by PEPL at sign-off."


def _chain(fields, after):
	"""Set insert_after on each field so they appear in the order written."""
	for field in fields:
		field.setdefault("insert_after", after)
		after = field["fieldname"]
	return fields


# C2-02 - Purchase & Stores rulebook (one tab). Fields without a default are
# PEPL-owned values: the HODs enter them on the test site at sign-off (C2-06).
PURCHASE_STORES_FIELDS = _chain(
	[
		{"fieldname": "custom_purchase_stores_tab", "label": "Purchase & Stores", "fieldtype": "Tab Break"},
		{"fieldname": "custom_purchase_section", "label": "Purchase", "fieldtype": "Section Break"},
		{
			"fieldname": "custom_po_approval_value_threshold",
			"label": "PO Approval Value (MD above)",
			"fieldtype": "Currency",
			"non_negative": 1,
			"description": "Purchase Orders with a grand total above this value need MD / CEO approval. "
			+ PEPL_VALUE,
		},
		{
			"fieldname": "custom_md_approver",
			"label": "MD / CEO (approves POs above the value)",
			"fieldtype": "Link",
			"options": "User",
			"description": "Receives a ToDo for every Purchase Order waiting for MD approval. "
			"Falls back to Notification Fallback Owner when empty.",
		},
		{
			"fieldname": "custom_enforce_override_reason",
			"label": "Require a Reason for Every Override",
			"fieldtype": "Check",
			"default": "1",
			"description": "When on, choosing a non-approved supplier or a non-lowest quote needs a typed reason, "
			"recorded with the user's name.",
		},
		{
			"fieldname": "custom_msme_payment_days",
			"label": "MSME Payment Days",
			"fieldtype": "Int",
			"default": "45",
			"non_negative": 1,
			"description": "Days within which an MSME supplier must be paid (MSMED Act, section 15).",
		},
		{
			"fieldname": "custom_msme_clock_basis",
			"label": "MSME Clock Starts From",
			"fieldtype": "Select",
			"options": "Bill Date\nReceipt Date",
			"default": "Bill Date",
			"description": "The date the MSME payment days are counted from.",
		},
		{
			"fieldname": "custom_vendor_payment_mode_of_payment",
			"label": "Vendor Payment: Mode of Payment",
			"fieldtype": "Link",
			"options": "Mode of Payment",
			"description": "Used on every vendor Payment Entry recorded from a Tally payment.",
		},
		{
			"fieldname": "custom_vendor_payment_bank_account",
			"label": "Vendor Payment: Bank Account",
			"fieldtype": "Link",
			"options": "Account",
			"description": "The bank ledger (Account Type Bank) vendor payments are made from.",
		},
		{
			"fieldname": "custom_vendor_tds_account",
			"label": "Vendor Payment: TDS Payable Account",
			"fieldtype": "Link",
			"options": "Account",
			"description": "Credited with the TDS deducted when a vendor is paid.",
		},
		{"fieldname": "custom_purchase_column", "fieldtype": "Column Break"},
		{
			"fieldname": "custom_delivery_alert_lead_days",
			"label": "Delivery Alert Lead Days",
			"fieldtype": "Int",
			"non_negative": 1,
			"description": "A PO line shows as Due Soon this many days before its promised date. "
			+ PEPL_VALUE,
		},
		{
			"fieldname": "custom_late_grace_days",
			"label": "Late Delivery Grace Days",
			"fieldtype": "Int",
			"default": "0",
			"non_negative": 1,
			"description": "A delivery counts as late only after this many days past the promised date.",
		},
		{
			"fieldname": "custom_receipt_short_tolerance_percent",
			"label": "Short Receipt Tolerance (%)",
			"fieldtype": "Percent",
			"description": "A closed PO line short by more than this % of the ordered qty is logged as a short "
			"delivery. " + PEPL_VALUE,
		},
		{
			"fieldname": "custom_vendor_score_lookback_days",
			"label": "Vendor Score Period (Days)",
			"fieldtype": "Int",
			"default": "365",
			"non_negative": 1,
			"description": "Supplier delivery and quality scores cover this many past days.",
		},
		{
			"fieldname": "custom_supplier_docs_section",
			"label": "Supplier Documents and Heat Numbers",
			"fieldtype": "Section Break",
		},
		{
			"fieldname": "custom_supplier_doc_expiry_alert_days",
			"label": "Document Expiry Alert Days",
			"fieldtype": "Int",
			"default": "30",
			"non_negative": 1,
			"description": "Alert this many days before a supplier document, warranty or AMC expires.",
		},
		{"fieldname": "custom_supplier_docs_column", "fieldtype": "Column Break"},
		{
			"fieldname": "custom_heat_number_gate_mode",
			"label": "Heat Number Gate",
			"fieldtype": "Select",
			"options": "Hard Block\nReason Required",
			"default": "Hard Block",
			"description": "What happens when raw material is received or issued without a heat number.",
		},
		{
			"fieldname": "custom_stock_planning_section",
			"label": "Reorder and Cycle Count",
			"fieldtype": "Section Break",
		},
		{
			"fieldname": "custom_reorder_lookback_days",
			"label": "Reorder: Usage Period (Days)",
			"fieldtype": "Int",
			"default": "90",
			"non_negative": 1,
			"description": "Average daily usage is taken over this many past days.",
		},
		{
			"fieldname": "custom_reorder_safety_days",
			"label": "Reorder: Safety Stock (Days)",
			"fieldtype": "Int",
			"non_negative": 1,
			"description": "Days of usage kept as safety stock. " + PEPL_VALUE,
		},
		{
			"fieldname": "custom_abc_a_value_percent",
			"label": "Class A: Share of Value (%)",
			"fieldtype": "Percent",
			"default": "80",
			"description": "Items making up the top this % of consumption value are class A.",
		},
		{
			"fieldname": "custom_abc_b_value_percent",
			"label": "Class B: Share of Value (%)",
			"fieldtype": "Percent",
			"default": "15",
			"description": "The next this % of value is class B; the rest is class C. A + B must be below 100.",
		},
		{"fieldname": "custom_stock_planning_column", "fieldtype": "Column Break"},
		{
			"fieldname": "custom_count_frequency_a_days",
			"label": "Count Class A Every (Days)",
			"fieldtype": "Int",
			"default": "30",
			"non_negative": 1,
		},
		{
			"fieldname": "custom_count_frequency_b_days",
			"label": "Count Class B Every (Days)",
			"fieldtype": "Int",
			"default": "90",
			"non_negative": 1,
		},
		{
			"fieldname": "custom_count_frequency_c_days",
			"label": "Count Class C Every (Days)",
			"fieldtype": "Int",
			"default": "180",
			"non_negative": 1,
		},
		{
			"fieldname": "custom_count_variance_approval_percent",
			"label": "Count Variance Needing Approval (%)",
			"fieldtype": "Percent",
			"description": "A counted difference above this % of book stock needs approval. " + PEPL_VALUE,
		},
		{
			"fieldname": "custom_stores_structure_section",
			"label": "Stores Structure",
			"fieldtype": "Section Break",
		},
		{
			"fieldname": "custom_workshops",
			"label": "Workshops",
			"fieldtype": "Small Text",
			"default": "Main Workshop",
			"description": "One workshop per line. Each gets its own WIP store (e.g. 'WIP Main Workshop'). "
			"Removing a line never deletes a store.",
		},
		{"fieldname": "custom_costing_section", "label": "Production Costing", "fieldtype": "Section Break"},
		{
			"fieldname": "custom_machine_hour_rates",
			"label": "Machine-Hour Rates",
			"fieldtype": "Table",
			"options": "PEPL Machine Hour Rate",
			"description": "Rate per hour for each machine group, used for cost per component. " + PEPL_VALUE,
		},
		{
			"fieldname": "custom_overhead_percent",
			"label": "Overhead (%)",
			"fieldtype": "Percent",
			"description": "Added on top of material and machine cost. " + PEPL_VALUE,
		},
	],
	after="custom_audit_log_retention_days",
)

CUSTOM_FIELDS[SYSTEM_PARAMETERS] += PURCHASE_STORES_FIELDS

# C2-03 - Supplier: criticality, MSME and the RM groups supplied.
APPROVAL_STATES = "\nDraft\nUnder Review\nApproved\nConditionally Approved\nSuspended\nExpired\nRejected"
CUSTOM_FIELDS["Supplier"] = _chain(
	[
		{"fieldname": "custom_pepl_section", "label": "PEPL", "fieldtype": "Section Break", "collapsible": 0},
		{
			"fieldname": "custom_vendor_criticality",
			"label": "Vendor Criticality",
			"fieldtype": "Select",
			"options": "Critical\nImportant\nRoutine",
			"default": "Routine",
			"reqd": 1,
			"in_standard_filter": 1,
			"description": "Critical: a late delivery stops production. Chase lists are sorted by this.",
		},
		{"fieldname": "custom_is_msme", "label": "Is MSME", "fieldtype": "Check", "in_standard_filter": 1},
		{
			"fieldname": "custom_udyam_number",
			"label": "Udyam Registration Number",
			"fieldtype": "Data",
			"depends_on": "custom_is_msme",
			"mandatory_depends_on": "custom_is_msme",
			"description": "Format UDYAM-XX-00-0000000.",
		},
		{
			"fieldname": "custom_msme_category",
			"label": "MSME Category",
			"fieldtype": "Select",
			"options": "\nMicro\nSmall\nMedium",
			"depends_on": "custom_is_msme",
			"description": "For information only.",
		},
		{
			"fieldname": "custom_rm_groups",
			"label": "RM Groups Supplied",
			"fieldtype": "Table MultiSelect",
			"options": "PEPL Supplier RM Group",
		},
		{"fieldname": "custom_pepl_column", "fieldtype": "Column Break"},
		{
			"fieldname": "custom_approval_state",
			"label": "Approval State",
			"fieldtype": "Select",
			"options": APPROVAL_STATES,
			"read_only": 1,
			"no_copy": 1,
			"in_list_view": 1,
			"in_standard_filter": 1,
			"description": "Filled by PEPL Supplier Approval.",
		},
		{
			"fieldname": "custom_approval_expiry",
			"label": "Approval Valid Until",
			"fieldtype": "Date",
			"read_only": 1,
			"no_copy": 1,
			"description": "Earliest expiry of a mandatory approval document.",
		},
		{
			"fieldname": "custom_delivery_score",
			"label": "Delivery Score (%)",
			"fieldtype": "Percent",
			"read_only": 1,
			"no_copy": 1,
			"description": "PO lines received complete by their promised date, as a % of the lines that fell due "
			"in the Vendor Score Period. Updated every morning (C2-14).",
		},
		{
			"fieldname": "custom_delivery_scored_lines",
			"label": "Lines Scored",
			"fieldtype": "Int",
			"read_only": 1,
			"no_copy": 1,
			"description": "How many PO lines the delivery score is based on. 0 means no score yet.",
		},
		{
			"fieldname": "custom_quality_score",
			"label": "Quality Score (%)",
			"fieldtype": "Percent",
			"read_only": 1,
			"no_copy": 1,
		},
	],
	after="supplier_group",
)

# C2-07 - Material Request drafted from a Sales Order.
CUSTOM_FIELDS["Material Request"] = [
	{
		"fieldname": "custom_sales_order",
		"label": "Drafted from Sales Order",
		"fieldtype": "Link",
		"options": "Sales Order",
		# C2-16: the storekeeper names the order on a Customer Provided request; it then
		# carries over to the Stock Entry that receives the customer's material.
		"read_only": 0,
		"read_only_depends_on": "eval:doc.material_request_type != 'Customer Provided'",
		"description": "For a Customer Provided request: the Sales Order the customer's material is for.",
		"no_copy": 1,
		"in_standard_filter": 1,
		"insert_after": "material_request_type",
	},
]

# C2-09 - RFQ created per RM group from a Material Request.
CUSTOM_FIELDS["Request for Quotation"] = [
	{
		"fieldname": "custom_rm_group",
		"label": "RM Group",
		"fieldtype": "Link",
		"options": "PEPL RM Group",
		"read_only": 1,
		"no_copy": 1,
		"in_standard_filter": 1,
		"in_list_view": 1,
		"insert_after": "transaction_date",
	},
	{
		"fieldname": "custom_material_request",
		"label": "From Material Request",
		"fieldtype": "Link",
		"options": "Material Request",
		"read_only": 1,
		"no_copy": 1,
		"in_standard_filter": 1,
		"insert_after": "custom_rm_group",
	},
]

# C2-10 - Purchase Order created from an approved Quotation Comparison.
CUSTOM_FIELDS["Purchase Order"] = [
	{
		"fieldname": "custom_quotation_comparison",
		"label": "From Quotation Comparison",
		"fieldtype": "Link",
		"options": "PEPL Quotation Comparison",
		"read_only": 1,
		"no_copy": 1,
		"in_standard_filter": 1,
		"insert_after": "transaction_date",
	},
	{
		# C2-11
		"fieldname": "custom_needs_md_approval",
		"label": "Needs MD Approval",
		"fieldtype": "Check",
		"read_only": 1,
		"no_copy": 1,
		"in_standard_filter": 1,
		"insert_after": "custom_quotation_comparison",
		"description": "Set automatically when the grand total is above the PO Approval Value "
		"in PEPL System Parameters. Only the MD / CEO can then submit it.",
	},
]

# C2-04 - Item: the stock class, set from the Item Group tree.
CUSTOM_FIELDS["Item"] = [
	{
		"fieldname": "custom_stock_class",
		"label": "Stock Class",
		"fieldtype": "Data",
		"read_only": 1,
		"no_copy": 1,
		"in_standard_filter": 1,
		"insert_after": "item_group",
		"description": "Set from the Item Group. One of the PEPL stock classes.",
	},
	{
		# C2-15
		"fieldname": "custom_heat_tracked",
		"label": "Heat Number Tracked",
		"fieldtype": "Check",
		"insert_after": "custom_stock_class",
		"description": "Receipts and issues must name the heat number (and receipts the test certificate). "
		"On for new raw material. Without stock history the heat is kept as the Batch.",
	},
]

# C2-15 - Heat numbers and test certificates.
HEAT_NUMBER = {
	"fieldname": "custom_heat_number",
	"label": "Heat Number",
	"fieldtype": "Data",
	"in_list_view": 1,
	"in_standard_filter": 1,
}
TEST_CERTIFICATE = {
	"fieldname": "custom_test_certificate",
	"label": "Test Certificate (MTC)",
	"fieldtype": "Attach",
}
CUSTOM_FIELDS["Batch"] = [
	{**HEAT_NUMBER, "insert_after": "item_name", "description": "Mandatory for heat-tracked items."},
	{**TEST_CERTIFICATE, "insert_after": "custom_heat_number", "in_list_view": 0},
]
CUSTOM_FIELDS["Purchase Receipt Item"] = [
	{**HEAT_NUMBER, "insert_after": "batch_no", "columns": 1},
	{**TEST_CERTIFICATE, "insert_after": "custom_heat_number"},
]
CUSTOM_FIELDS["Stock Entry Detail"] = [
	{
		**HEAT_NUMBER,
		"insert_after": "batch_no",
		"columns": 1,
		"description": "Filled from the Batch for heat-batch items; type it for other heat-tracked items.",
	},
]

# C2-16 - Customer-supplied material moves against its Sales Order.
CUSTOM_FIELDS["Stock Entry"] = [
	{
		"fieldname": "custom_sales_order",
		"label": "Sales Order (CSM)",
		"fieldtype": "Link",
		"options": "Sales Order",
		"insert_after": "stock_entry_type",
		"in_standard_filter": 1,
		"search_index": 1,
		"description": "Mandatory when a line is customer-supplied material (CSM).",
	},
	{
		"fieldname": "custom_csm_customer",
		"label": "Customer (CSM)",
		"fieldtype": "Data",
		"read_only": 1,
		"fetch_from": "custom_sales_order.customer_name",
		"depends_on": "eval:doc.custom_sales_order",
		"insert_after": "custom_sales_order",
	},
]
CUSTOM_FIELDS["Sales Order"] = [
	{
		"fieldname": "custom_has_csm",
		"label": "Has Customer-Supplied Material",
		"fieldtype": "Check",
		"read_only": 1,
		"hidden": 1,
		"no_copy": 1,
		"allow_on_submit": 1,
		"insert_after": "delivery_date",
	},
	{
		"fieldname": "custom_csm_scrap_disposition",
		"label": "CSM Scrap",
		"fieldtype": "Select",
		"options": "Hold\nReturn to Customer\nPEPL May Sell",
		"default": "Hold",
		"allow_on_submit": 1,
		"no_copy": 1,
		"depends_on": "eval:doc.custom_has_csm",
		"insert_after": "custom_has_csm",
		"description": "What happens to scrap of the customer's material. Hold until the customer decides.",
	},
]

# C2-17 - Vendor payments: MSME 45-day clock on the bill; Tally payments recorded as Payment Entries.
CUSTOM_FIELDS["Purchase Invoice"] = [
	{
		"fieldname": "custom_is_msme",
		"label": "MSME Supplier",
		"fieldtype": "Check",
		"read_only": 1,
		"fetch_from": "supplier.custom_is_msme",
		"in_standard_filter": 1,
		"insert_after": "supplier_name",
	},
	{
		"fieldname": "custom_msme_due_date",
		"label": "MSME Pay By",
		"fieldtype": "Date",
		"read_only": 1,
		"no_copy": 1,
		"allow_on_submit": 1,
		"depends_on": "custom_is_msme",
		"insert_after": "custom_is_msme",
		"description": "Bill date (or receipt date, per System Parameters) + MSME Payment Days.",
	},
	{
		"fieldname": "custom_msme_days_left",
		"label": "MSME Days Left",
		"fieldtype": "Int",
		"read_only": 1,
		"no_copy": 1,
		"allow_on_submit": 1,
		"depends_on": "custom_is_msme",
		"insert_after": "custom_msme_due_date",
		"description": "Recomputed every morning. Negative = past the MSME deadline.",
	},
]
CUSTOM_FIELDS["Payment Entry"] = [
	{
		"fieldname": "custom_tally_voucher_no",
		"label": "Tally Voucher No",
		"fieldtype": "Data",
		"no_copy": 1,
		"search_index": 1,
		"in_standard_filter": 1,
		"insert_after": "reference_date",
		"description": "The Tally payment voucher this entry mirrors. One submitted entry per voucher.",
	},
	{
		"fieldname": "custom_payment_source",
		"label": "Payment Source",
		"fieldtype": "Select",
		"options": "\nManual Tick\nTally Mirror",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "custom_tally_voucher_no",
	},
	{
		"fieldname": "custom_payment_run",
		"label": "Payment Run",
		"fieldtype": "Link",
		"options": "PEPL Payment Run",
		"no_copy": 1,
		"insert_after": "custom_payment_source",
	},
]


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
