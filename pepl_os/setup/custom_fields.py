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

# Cycle 3a - Production rulebook (one tab). Each deliverable adds its rules here.
PRODUCTION_FIELDS = _chain(
	[
		{"fieldname": "custom_production_tab", "label": "Production", "fieldtype": "Tab Break"},
		# C3a-X2 - shop-floor masters
		{"fieldname": "custom_shop_floor_section", "label": "Shop Floor", "fieldtype": "Section Break"},
		{
			"fieldname": "custom_operator_pin_digits",
			"label": "Operator PIN Digits",
			"fieldtype": "Int",
			"default": "4",
			"description": "How many digits each operator's kiosk PIN has (4 to 6).",
		},
		# C3a-X7 - skill check (the mode itself is "Operator Skill Check Mode" on the first tab)
		{
			"fieldname": "custom_skill_min_level",
			"label": "Minimum Skill Level to Run a Machine",
			"fieldtype": "Select",
			"options": "1 - Trainee\n2 - Runs under supervision\n3 - Runs independently\n4 - Sets up and trains others",
			"default": "3 - Runs independently",
			"description": "An operator below this level on the machine's group is flagged on the shift entry; "
			"what happens then follows 'Operator Skill Check Mode' (Advisory / Soft Block / Hard Block).",
		},
		# C3a-X1 - Shift Production Entry
		{"fieldname": "custom_spr_column", "fieldtype": "Column Break"},
		{
			"fieldname": "custom_spr_shift_grace_minutes",
			"label": "Shift Entry: Minutes Allowed Before / After the Shift",
			"fieldtype": "Int",
			"default": "30",
			"description": "Rows may start this many minutes before the shift and end this many after it "
			"(0 to 120).",
		},
		{
			"fieldname": "custom_spr_max_unaccounted_minutes",
			"label": "Shift Entry: Minutes Allowed Unexplained",
			"fieldtype": "Int",
			"default": "15",
			"description": "A shift entry can be submitted only when no more than this many of the shift's "
			"planned minutes are left without a production or downtime row.",
		},
		{
			"fieldname": "custom_spr_tool_photo_required",
			"label": "Shift Entry: Tool Change Needs a Photo",
			"fieldtype": "Check",
			"default": "1",
			"description": "When on, every tool change needs a photo of the removed tool before submit.",
		},
		# C3a-B1 - the shop-floor kiosk
		{
			"fieldname": "custom_kiosk_pin_tries",
			"label": "Kiosk: Wrong PIN Tries",
			"fieldtype": "Int",
			"default": "5",
			"description": "After this many wrong PINs (3 to 10) the operator's code is locked on the kiosk.",
		},
		{
			"fieldname": "custom_kiosk_lock_minutes",
			"label": "Kiosk: Lock Minutes",
			"fieldtype": "Int",
			"default": "15",
			"description": "How long a code stays locked after too many wrong PINs (1 to 120 minutes).",
		},
		{
			"fieldname": "custom_kiosk_session_minutes",
			"label": "Kiosk: Session Minutes",
			"fieldtype": "Int",
			"default": "30",
			"description": "An operator signed in on the kiosk is signed out after this many minutes without saving "
			"(5 to 240).",
		},
		# C3a-X5 - Job Orders from Sales Orders
		{"fieldname": "custom_job_orders_section", "label": "Job Orders", "fieldtype": "Section Break"},
		{
			"fieldname": "custom_job_order_from_sales_order",
			"label": "Draft Job Orders from Sales Orders",
			"fieldtype": "Check",
			"default": "1",
			"description": "When on, submitting a Sales Order drafts one Job Order for each manufactured line "
			"that has a default BOM; a line without a BOM is flagged to the Production notification owner.",
		},
		# C3a-X6 - machine double-booking in Production Plans
		{
			"fieldname": "custom_double_booking_mode",
			"label": "Machine Double-Booking Mode",
			"fieldtype": "Select",
			"options": "Advisory\nSoft Block\nHard Block",
			"default": "Soft Block",
			"description": "When a Production Plan books a machine for more jobs at the same time than it can run: "
			"Advisory = warning; Soft Block = submitting needs a reason (Override Log, PRD-DOUBLE-BOOK); "
			"Hard Block = the plan cannot be submitted until the clash is resolved.",
		},
		# C3a-P2 - Production Plan load view
		{
			"fieldname": "custom_load_warning_percent",
			"label": "Load View: Warning at % of Machine Hours",
			"fieldtype": "Percent",
			"default": "85",
			"description": "The Production Plan's machine load shows a machine orange from this share of its hours "
			"and red above 100 %. Hours a day come from the machine's Working Hours, else from the active shifts.",
		},
		# C3a-X3 - daily OEE
		{"fieldname": "custom_oee_section", "label": "OEE", "fieldtype": "Section Break"},
		{
			"fieldname": "custom_oee_target_percent",
			"label": "OEE Target %",
			"fieldtype": "Percent",
			"default": "65",
			"description": "Each machine's daily OEE is compared with this; below it, the day is marked "
			"'Below Target'. PM / Calibration follows 'OEE: Exclude PM/Calibration from Planned Time'.",
		},
		# C3a-C1 - OEE thresholds per factor: which of the three let the day down
		{
			"fieldname": "custom_oee_availability_target_percent",
			"label": "OEE: Availability Target %",
			"fieldtype": "Percent",
			"default": "90",
			"description": "Run time against planned production time. A day below it names Availability on its "
			"Daily OEE.",
		},
		{
			"fieldname": "custom_oee_performance_target_percent",
			"label": "OEE: Performance Target %",
			"fieldtype": "Percent",
			"default": "95",
			"description": "Pieces x standard minutes against run time. A day below it names Performance.",
		},
		{
			"fieldname": "custom_oee_quality_target_percent",
			"label": "OEE: Quality Target %",
			"fieldtype": "Percent",
			"default": "99",
			"description": "Good pieces against all pieces made. A day below it names Quality.",
		},
		# C3a-X8 - job work
		{"fieldname": "custom_job_work_section", "label": "Job Work", "fieldtype": "Section Break"},
		{
			"fieldname": "custom_job_work_return_days",
			"label": "Job-Work Return Days",
			"fieldtype": "Int",
			"default": "30",
			"description": "Material at a job worker for longer than this is Overdue; the Production notification "
			"owner gets a ToDo every morning (PRD-JW-OVERDUE).",
		},
		{
			"fieldname": "custom_job_work_gst_warning_days",
			"label": "Job-Work GST Warning Days",
			"fieldtype": "Int",
			"default": "30",
			"description": "Inputs sent for job work must come back within one year (CGST section 143). Material "
			"this many days short of the year is marked 'GST limit near'.",
		},
		# C3a-X10 - Daily Stand-up (the e-mail group is "Standup Email Group" on the first tab)
		{"fieldname": "custom_standup_section", "label": "Daily Stand-up", "fieldtype": "Section Break"},
		{
			"fieldname": "custom_standup_risk_days",
			"label": "Stand-up: Days Ahead for Delivery Risk",
			"fieldtype": "Int",
			"default": "3",
			"description": "Open Job Orders due within this many days (or already late) and not finished are listed "
			"in the morning stand-up, e-mailed at 07:45 to the Standup Email Group.",
		},
		# C3a-C1 - standard-time governance (used by the learning-standards workflow, Work Package E2). The band a
		# run may differ from its standard is pepl_sales "Cycle Deviation Threshold Low / High" (0.8 / 1.2).
		{
			"fieldname": "custom_std_time_section",
			"label": "Standard Times (governance)",
			"fieldtype": "Section Break",
		},
		{
			"fieldname": "custom_std_time_lookback_days",
			"label": "Standard Time: Look-back Days",
			"fieldtype": "Int",
			"default": "90",
			"description": "A new standard cycle time is suggested only from the runs of this many past days (7 to 365).",
		},
		{
			"fieldname": "custom_std_time_min_runs",
			"label": "Standard Time: Minimum Runs Before a Suggestion",
			"fieldtype": "Int",
			"default": "5",
			"description": "Production rows on that operation needed before a new standard time is suggested.",
		},
		{
			"fieldname": "custom_std_time_basis",
			"label": "Standard Time: Suggest From",
			"fieldtype": "Select",
			"options": "Median\nAverage",
			"default": "Median",
			"description": "Median ignores the odd very slow or very fast run; Average uses every run equally.",
		},
		{"fieldname": "custom_std_time_column", "fieldtype": "Column Break"},
		{
			"fieldname": "custom_std_time_max_change_percent",
			"label": "Standard Time: Largest Change per Approval %",
			"fieldtype": "Percent",
			"default": "20",
			"description": "One approval may move a standard time by at most this share; a bigger move is made in steps.",
		},
		{
			"fieldname": "custom_std_time_approver_role",
			"label": "Standard Time: Approved By (Role)",
			"fieldtype": "Link",
			"options": "Role",
			"description": "Only this role approves a new standard cycle time (the HOD). Empty = PEPL Production Manager. "
			"Runs outside 'Cycle Deviation Threshold Low / High' (first tab) are flagged.",
		},
		# C3a-X11 - the standard LD clause for new orders of these sectors
		{
			"fieldname": "custom_ld_defaults_section",
			"label": "Liquidated Damages (LD)",
			"fieldtype": "Section Break",
		},
		{
			"fieldname": "custom_ld_default_sectors",
			"label": "LD: Sectors with LD by Default",
			"fieldtype": "Small Text",
			"default": "Railways\nDefence",
			"description": "One sector per line. A new Sales Order of these sectors starts with the LD clause below.",
		},
		{
			"fieldname": "custom_ld_default_rate_percent",
			"label": "LD: Default Rate %",
			"fieldtype": "Percent",
			"default": "0.5",
		},
		{
			"fieldname": "custom_ld_default_period",
			"label": "LD: Default per",
			"fieldtype": "Select",
			"options": "Week\nDay",
			"default": "Week",
		},
		{
			"fieldname": "custom_ld_default_max_percent",
			"label": "LD: Default Cap %",
			"fieldtype": "Percent",
			"default": "10",
		},
	],
	after="custom_overhead_percent",
)

CUSTOM_FIELDS[SYSTEM_PARAMETERS] += PRODUCTION_FIELDS

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
	{
		# C2-20
		"fieldname": "custom_abc_class",
		"label": "ABC Class",
		"fieldtype": "Data",
		"read_only": 1,
		"no_copy": 1,
		"in_standard_filter": 1,
		"insert_after": "custom_heat_tracked",
		"description": "A / B / C by 12-month consumption value, set every month. Decides how often it is counted.",
	},
	{
		"fieldname": "custom_last_counted_on",
		"label": "Last Counted On",
		"fieldtype": "Date",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "custom_abc_class",
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
	{
		# C2-21: consumables issued per machine group (Cycle 3a's shift entries fill it)
		"fieldname": "custom_machine_group",
		"label": "Machine Group",
		"fieldtype": "Data",
		"insert_after": "custom_heat_number",
		"description": "For consumables: the machine group they were issued to.",
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
	{
		# C3a-X1: the consumables issue made by a Shift Production Entry
		"fieldname": "custom_shift_production_entry",
		"label": "Shift Production Entry",
		"fieldtype": "Link",
		"options": "PEPL Shift Production Entry",
		"insert_after": "custom_csm_customer",
		"read_only": 1,
		"search_index": 1,
		"depends_on": "eval:doc.custom_shift_production_entry",
	},
	{
		# C3a-X8: what this entry is for the job worker (set automatically when material goes out)
		"fieldname": "custom_job_work_movement",
		"label": "Job-Work Movement",
		"fieldtype": "Select",
		"options": "\nSent to Job Worker\nReceived after Processing\nReturned Unprocessed",
		"insert_after": "custom_shift_production_entry",
		"description": "Material coming back from a job worker's store: processed, or returned as it went.",
	},
	{
		# C3a-X9: the customer-supplied material issue posted by a Delivery Note
		"fieldname": "custom_delivery_note",
		"label": "Delivery Note (CSM consumed)",
		"fieldtype": "Link",
		"options": "Delivery Note",
		"insert_after": "custom_job_work_movement",
		"read_only": 1,
		"search_index": 1,
		"depends_on": "eval:doc.custom_delivery_note",
	},
]

# C3a-X9 - what customer-supplied material a Delivery Note consumes
CUSTOM_FIELDS["Delivery Note"] = [
	{
		"fieldname": "custom_csm_consumption",
		"label": "Customer Material Consumed",
		"fieldtype": "Small Text",
		"insert_after": "items",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "eval:doc.custom_csm_consumption",
		"description": "Customer-supplied material this delivery consumes, per Sales Order (issued on submit).",
	},
]

# C3a-X8 - job workers' stores and what each job-work movement is
CUSTOM_FIELDS["Warehouse"] = [
	{
		"fieldname": "custom_job_worker",
		"label": "Job Worker",
		"fieldtype": "Link",
		"options": "Supplier",
		"insert_after": "parent_warehouse",
		"description": "Fill in when this store holds PEPL's material at a job worker (plating, heat treatment ...). "
		"Everything sent here and back is reconciled in PEPL Job-Work Reconciliation.",
	},
]

# C3a-X6 - the machine clashes found in a Production Plan
CUSTOM_FIELDS["Production Plan"] = [
	{
		"fieldname": "custom_machine_clashes",
		"label": "Machine Double-Bookings",
		"fieldtype": "Small Text",
		"insert_after": "po_items",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "eval:doc.custom_machine_clashes",
		"description": "Machines this plan books for more jobs at the same time than they can run, found when "
		"the plan is saved (System Parameters → Production → Machine Double-Booking Mode).",
	},
]

# C3a-X5 - Job Orders drafted by a submitted Sales Order
CUSTOM_FIELDS["Work Order"] = [
	{
		"fieldname": "custom_auto_from_sales_order",
		"label": "Drafted from the Sales Order",
		"fieldtype": "Check",
		"insert_after": "sales_order",
		"read_only": 1,
		"default": "0",
		"description": "Set when PEPL OS drafted this Job Order on submit of the Sales Order; cancelling the "
		"Sales Order deletes it while it is still a draft.",
	},
]

# C3a-X1 - Job Card time logs posted by a Shift Production Entry
CUSTOM_FIELDS["Job Card Time Log"] = [
	{
		"fieldname": "custom_pepl_spr",
		"label": "Shift Production Entry",
		"fieldtype": "Link",
		"options": "PEPL Shift Production Entry",
		"insert_after": "operation",
		"read_only": 1,
		"search_index": 1,
	},
	{
		"fieldname": "custom_pepl_spr_row",
		"label": "Shift Production Entry Row",
		"fieldtype": "Data",
		"insert_after": "custom_pepl_spr",
		"read_only": 1,
		"hidden": 1,
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

# C3a-X11 - the contractual Liquidated Damages clause (fixed once the order is submitted)
CUSTOM_FIELDS["Sales Order"] += _chain(
	[
		{"fieldname": "custom_ld_section", "label": "Liquidated Damages (LD)", "fieldtype": "Section Break"},
		{
			"fieldname": "custom_ld_applicable",
			"label": "LD Applies",
			"fieldtype": "Check",
			"description": "Ticked by default for the sectors in System Parameters → Production → LD.",
		},
		{
			"fieldname": "custom_ld_rate_percent",
			"label": "LD Rate %",
			"fieldtype": "Percent",
			"depends_on": "eval:doc.custom_ld_applicable",
			"description": "Of the value delivered late, per week (or day) of delay or part thereof.",
		},
		{
			"fieldname": "custom_ld_period",
			"label": "LD per",
			"fieldtype": "Select",
			"options": "Week\nDay",
			"default": "Week",
			"depends_on": "eval:doc.custom_ld_applicable",
		},
		{
			"fieldname": "custom_ld_max_percent",
			"label": "LD Cap %",
			"fieldtype": "Percent",
			"depends_on": "eval:doc.custom_ld_applicable",
			"description": "LD never exceeds this % of the value delivered late (or of the order).",
		},
		{"fieldname": "custom_ld_column", "fieldtype": "Column Break"},
		{
			"fieldname": "custom_ld_grace_days",
			"label": "LD Grace Days",
			"fieldtype": "Int",
			"default": "0",
			"depends_on": "eval:doc.custom_ld_applicable",
			"description": "Days after the delivery date before LD starts.",
		},
		{
			"fieldname": "custom_ld_basis",
			"label": "LD Charged On",
			"fieldtype": "Select",
			"options": "Value of Late Items\nWhole Order Value",
			"default": "Value of Late Items",
			"depends_on": "eval:doc.custom_ld_applicable",
		},
		{
			"fieldname": "custom_ld_clause",
			"label": "LD Clause (contract reference)",
			"fieldtype": "Small Text",
			"depends_on": "eval:doc.custom_ld_applicable",
		},
	],
	after="terms",
)

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
