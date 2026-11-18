app_name = "pepl_os"
app_title = "PEPL OS"
app_publisher = "Anshiv"
app_description = "PEPL Operating System: Purchase, Stores, Production, Quality, HR and Tally mirror"
app_email = "erp.pepl@gmail.com"
app_license = "mit"

# pepl_os builds on pepl_sales (System Parameters, ToDo engine, document
# generator). Dependencies point one way only: pepl_os -> pepl_sales.
required_apps = ["erpnext", "pepl_sales"]

# Shared client helpers: pepl.ask_reason(), pepl.record_override(), pepl.panel()
app_include_js = ["/assets/pepl_os/js/pepl_os_common.js"]

# C3a-B1: a kiosk login (role PEPL Kiosk, no Desk) opens the shift-entry kiosk after logging in: pepl_os is listed as
# an app whose page is /kiosk, shown only to kiosk logins, and is their Default App; the role's home page is the kiosk.
add_to_apps_screen = [
	{
		"name": "pepl_os",
		"logo": "/assets/frappe/images/frappe-framework-logo.svg",
		"title": "Shift Entry Kiosk",
		"route": "/kiosk",
		"has_permission": "pepl_os.pepl_production.kiosk.kiosk_app_permission",
	}
]
role_home_page = {"PEPL Kiosk": "kiosk"}

# Installation
# ------------
# Custom fields and property setters are applied here (idempotent), never in
# patches: Frappe marks patches as done without running them on fresh installs.
before_install = "pepl_os.install.before_install"
after_install = "pepl_os.install.after_install"
before_migrate = "pepl_os.install.before_migrate"
after_migrate = "pepl_os.install.after_migrate"

# Client scripts for standard DocTypes are added per deliverable, e.g.
# "Purchase Order": "public/js/purchase_order.js"
doctype_js = {
	# C2-07: stock, orders and approved suppliers per line
	"Material Request": "public/js/material_request.js",
	# C2-08: reason before submitting to a supplier who is not approved
	# C2-10: "Quotation Comparison" button on a submitted RFQ
	"Request for Quotation": ["public/js/supplier_gate.js", "public/js/request_for_quotation.js"],
	# C2-11 approval check runs before the C2-08 reason dialog
	"Purchase Order": ["public/js/purchase_order.js", "public/js/supplier_gate.js"],
	# C2-15: heat panel, Split by heat, reason dialog when the gate asks for one
	# C3b-Q1: Incoming QC panel and the reason dialog of the incoming QC gate
	"Purchase Receipt": ["public/js/purchase_receipt.js", "public/js/purchase_receipt_qc.js"],
	# C2-16: Sales Order (CSM) picked from submitted orders of the company
	# C3a-P3: job work outstanding at the job worker for the items of the entry
	"Stock Entry": "public/js/stock_entry.js",
	# C2-16: "CSM Balance" button once the order holds customer-supplied material
	# C3a-X11: LD terms and today's LD exposure on a submitted order
	"Sales Order": ["public/js/csm_sales_order.js", "public/js/sales_order_ld.js"],
	# C2-17: payment-priority panel ("Rank #4 this week · MSME due in 6 days")
	"Purchase Invoice": "public/js/purchase_invoice.js",
	# C3a-P3: job work outstanding on a job worker
	"Supplier": "public/js/supplier_payments.js",
	# C2-19: reorder level vs projected stock; "Create Material Request" when below
	"Item": "public/js/item_reorder.js",
	# C3b-Q5: Dispatch QC panel and the reason dialog of the dispatch gate
	"Delivery Note": "public/js/delivery_note_dispatch.js",
	# C3b-Q2: reason dialog when a reading's instrument is out of calibration (Calibration Gate = Soft Block)
	"Quality Inspection": "public/js/quality_inspection.js",
	# C3a-P1: Job Order status panel (quantity, routing progress, delivery, LD)
	# C3a-P4: customer-supplied material held against what the Job Order still needs
	"Work Order": "public/js/work_order.js",
	# C3a-X6: reason dialog before submitting a plan that double-books a machine (Soft Block)
	# C3a-P2: machine load panel (booked hours against available hours per machine)
	"Production Plan": "public/js/production_plan.js",
}

# C2-03: Supplier list coloured by approval state.
doctype_list_js = {"Supplier": "public/js/supplier_list.js"}

# Values the desk needs in the browser (alert days for list colours and panels).
boot_session = "pepl_os.boot.boot_session"

# CI / test sites: build ERPNext's standard test company, items, suppliers and
# warehouses (the setup wizard never runs there), then apply pepl_os setup to them.
before_tests = "pepl_os.tests.bootstrap.before_tests"

# Document events are added per deliverable.
CSM_SEGREGATION = "pepl_os.pepl_stores.stock_tree.validate_csm_segregation"
CSM_USE = "pepl_os.pepl_production.csm_consumption"
SUPPLIER_GATE = "pepl_os.pepl_purchase.supplier_approval.before_submit_gate"
PO_APPROVAL = "pepl_os.pepl_purchase.po_approval"
TRACKER = "pepl_os.pepl_purchase.tracker"
LETDOWN = "pepl_os.pepl_purchase.letdown"
HEAT = "pepl_os.pepl_stores.heat"
INCOMING_QC = "pepl_os.pepl_quality.incoming_qc"
CALIBRATION = "pepl_os.pepl_quality.calibration"
NCR = "pepl_os.pepl_quality.ncr"
DISPATCH = "pepl_os.pepl_quality.dispatch"
HISTORIC = "pepl_os.pepl_accounts.historic"
CSM = "pepl_os.pepl_stores.csm"
PAYMENTS = "pepl_os.pepl_purchase.payments"

# CR2 - tender data (PEPL Tender, PEPL CST Cost Sheet) open only to the users listed in site_config.json
# (pepl_tender_access_users), plus Administrator. See pepl_os/pepl_governance/tender_access.py.
TENDER_ACCESS = "pepl_os.pepl_governance.tender_access"
_TA_GATED = ("PEPL Tender", "PEPL CST Cost Sheet", "PEPL Generated Document")
_TA_TABLES = (
	"PEPL Tender",
	"PEPL CST Cost Sheet",
	"PEPL Tender Item",
	"PEPL Tender Item Competitor",
	"PEPL Tender Bid Document",
	"PEPL Tender PO Schedule",
	"PEPL Tender Source Link",
	"PEPL CST Component",
	"PEPL CST Competitor History",
)
# records pointing at a tender / Cost Sheet: their files, history, comments, assignments, logs, shares
_TA_RELATED = {
	"File": "file_conditions",
	"Version": "version_conditions",
	"Comment": "comment_conditions",
	"ToDo": "todo_conditions",
	"Communication": "communication_conditions",
	"Deleted Document": "deleted_document_conditions",
	"Activity Log": "activity_log_conditions",
	"Access Log": "access_log_conditions",
	"View Log": "view_log_conditions",
	"Notification Log": "notification_log_conditions",
	"Email Queue": "email_queue_conditions",
	"DocShare": "docshare_conditions",
}

has_permission = {
	**{doctype: f"{TENDER_ACCESS}.has_permission" for doctype in _TA_GATED},
	**{doctype: f"{TENDER_ACCESS}.has_related_permission" for doctype in _TA_RELATED},
}

permission_query_conditions = {
	**{doctype: f"{TENDER_ACCESS}.query_conditions" for doctype in _TA_TABLES},
	"PEPL Generated Document": f"{TENDER_ACCESS}.generated_document_conditions",
	**{doctype: f"{TENDER_ACCESS}.{method}" for doctype, method in _TA_RELATED.items()},
}

doc_events = {
	# C3a-B1: a login given the PEPL Kiosk profile opens the kiosk after logging in
	# CR2: the PEPL Tender Access role belongs to exactly the listed users
	"User": {
		"validate": f"{TENDER_ACCESS}.validate_user",
		"on_update": "pepl_os.pepl_production.kiosk.on_user_update",
	},
	# CR2: a tender / Cost Sheet is never assigned or shared to someone outside the list
	"ToDo": {"validate": f"{TENDER_ACCESS}.validate_todo"},
	"DocShare": {"validate": f"{TENDER_ACCESS}.validate_docshare"},
	# C3a-B3: an operator linked to an Employee follows it (name, joining date, login, Left / Inactive)
	"Employee": {"on_update": "pepl_os.pepl_production.hr_lite.on_employee_update"},
	"PEPL System Parameters": {
		# C2-02: no negative days, percentages 0-100, class A + B below 100.
		# C3a-X2: operator PIN length 4-6.
		"validate": [
			"pepl_os.pepl_purchase.params.validate_purchase_params",
			"pepl_os.pepl_production.params.validate_production_params",
			"pepl_os.pepl_quality.params.validate_quality_params",
		],
		"on_update": [
			# A5: a changed audit-log retention applies immediately.
			"pepl_os.pepl_governance.retention.on_parameters_update",
			# C3b-Q1: a changed "Incoming QC: Stock Classes" ticks / unticks the items' inspection
			f"{INCOMING_QC}.on_parameters_update",
		],
	},
	# C2-04: a company created after install gets PEPL's stores at once.
	"Company": {"on_update": "pepl_os.pepl_stores.stock_tree.on_company_update"},
	# C2-03: Udyam number required for MSME suppliers.
	"Supplier": {"validate": "pepl_os.pepl_purchase.supplier.validate_supplier"},
	# CR1: an invoice dated before "Historic Booking: Documents Dated Before" - Tally Invoice No., no e-Invoice /
	# e-Waybill, a valuation rate for stock never received
	"Sales Invoice": {
		"validate": f"{HISTORIC}.validate_sales_invoice",
		"before_submit": f"{HISTORIC}.before_submit_sales_invoice",
	},
	# C2-17: MSME flag and pay-by date on the bill
	"Purchase Invoice": {"validate": f"{PAYMENTS}.validate_invoice"},
	# C2-17: one submitted entry per Tally voucher; Payment Run rows and MSME ToDos follow payments
	"Payment Entry": {
		"validate": f"{PAYMENTS}.validate_payment_entry",
		"on_submit": f"{PAYMENTS}.on_payment_entry_change",
		"on_cancel": f"{PAYMENTS}.on_payment_entry_change",
	},
	# C2-04: stock class from the Item Group; Capital never stock; CSM customer-provided.
	# C3b-Q1: an item of a class in "Incoming QC: Stock Classes" is inspected on receipt
	"Item": {"validate": ["pepl_os.pepl_stores.stock_tree.validate_item", f"{INCOMING_QC}.validate_item"]},
	# C3b-Q1: an incoming QC Inspection names its supplier
	# C3b-Q2: a reading taken with an instrument out of calibration (the Calibration Gate)
	"Quality Inspection": {
		"validate": f"{INCOMING_QC}.validate_inspection",
		"before_submit": f"{CALIBRATION}.before_submit_inspection",
		# C3b-Q3: a QC Inspection submitted as Rejected raises an NCR (QA-NCR-QI); cancelling it cancels the NCR
		"on_submit": f"{NCR}.on_inspection_submit",
		"on_cancel": f"{NCR}.on_inspection_cancel",
	},
	# C2-04: customer-supplied material and PEPL material never share a store.
	# C2-15: heat number -> Batch on receipts, Batch -> heat on issues; the heat number gate
	# C2-16: every customer-supplied line moves against its Sales Order; the order shows its scrap option
	"Stock Entry": {
		"before_validate": [f"{CSM}.before_validate_stock_entry", f"{HEAT}.before_validate_stock_entry"],
		# C3a-X8: each job-work movement says what it is
		"validate": [
			CSM_SEGREGATION,
			f"{CSM}.validate_stock_entry",
			"pepl_os.pepl_production.job_work.validate_stock_entry",
		],
		"before_submit": f"{HEAT}.before_submit_stock_entry",
		"on_submit": f"{CSM}.on_stock_entry_change",
		"on_cancel": f"{CSM}.on_stock_entry_change",
	},
	"Purchase Receipt": {
		# C2-15: heat number -> Batch, the heat / MTC gate, the Receipt Log
		# C3b-Q1: a line keeps only this receipt's own QC Inspection
		"before_validate": [f"{HEAT}.before_validate_receipt", f"{INCOMING_QC}.before_validate_receipt"],
		"validate": CSM_SEGREGATION,
		# C3b-Q1: each line that needs inspection gets its draft QC Inspection; the incoming QC gate
		"on_update": f"{INCOMING_QC}.sync_inspections",
		"on_trash": f"{INCOMING_QC}.on_trash_receipt",
		"before_submit": [f"{HEAT}.before_submit_receipt", f"{INCOMING_QC}.before_submit_receipt"],
		# C2-12: a receipt recomputes the trackers of its Purchase Orders
		# C2-14: a late receipt line is logged as a letdown; cancelling the receipt removes it
		"on_submit": [
			f"{TRACKER}.on_receipt_change",
			f"{LETDOWN}.on_receipt_submit",
			f"{HEAT}.on_submit_receipt",
		],
		"on_cancel": [
			f"{TRACKER}.on_receipt_change",
			f"{LETDOWN}.on_receipt_cancel",
			f"{HEAT}.on_cancel_receipt",
		],
	},
	# C2-15: a heat-tracked item's Batch carries its heat number
	"Batch": {"validate": f"{HEAT}.validate_batch"},
	# C2-14: a PO closed short logs a Short letdown; re-opened, it is removed
	"PEPL Purchase Tracker": {"on_update": f"{LETDOWN}.sync_short_letdowns"},
	# C2-16 segregation; C3a-X9 CSM consumed by the delivery and the material gate
	"Delivery Note": {
		# C3b-Q5: a line keeps only this delivery's own final inspection
		"before_validate": f"{DISPATCH}.before_validate_delivery",
		"validate": [CSM_SEGREGATION, f"{CSM_USE}.validate_delivery_note"],
		# C3b-Q5: each line that needs a final inspection gets its draft QC Inspection; the dispatch gate
		"on_update": f"{DISPATCH}.sync_final_inspections",
		"on_trash": f"{DISPATCH}.on_trash_delivery",
		"before_submit": [f"{CSM_USE}.before_submit_delivery_note", f"{DISPATCH}.before_submit_delivery"],
		# C3b-Q3: a customer return (Delivery Note return) raises one NCR per item (QA-NCR-RETURN)
		"on_submit": [f"{CSM_USE}.on_submit_delivery_note", f"{NCR}.on_delivery_note_submit"],
		"on_cancel": [f"{CSM_USE}.on_cancel_delivery_note", f"{NCR}.on_delivery_note_cancel"],
	},
	# C2-07: draft the Material Request for bought-out and short raw material
	# C2-07 Material Request; C3a-X5 draft Job Orders (deleted again on cancel)
	"Sales Order": {
		# CR2 (0.62.1): only the Tender Access users make a Sales Order from a tender (PEPL, 16 Nov 2026)
		"before_insert": f"{TENDER_ACCESS}.guard_sales_order_tender",
		"before_validate": f"{TENDER_ACCESS}.guard_sales_order_tender",
		# CR1: an order dated before "Historic Booking: Documents Dated Before" is marked historic
		# C3a-X11: the LD clause (sector defaults, sensible values)
		"validate": [f"{HISTORIC}.validate_sales_order", "pepl_os.pepl_production.ld.validate_sales_order"],
		"on_submit": [
			"pepl_os.pepl_purchase.material_request.on_sales_order_submit",
			"pepl_os.pepl_production.job_orders.on_sales_order_submit",
			f"{HISTORIC}.on_sales_order_submit",
		],
		"on_cancel": "pepl_os.pepl_production.job_orders.on_sales_order_cancel",
	},
	# C3a-X6: machine double-booking
	"Production Plan": {
		"validate": "pepl_os.pepl_production.machine_booking.check_on_save",
		"before_submit": "pepl_os.pepl_production.machine_booking.check_on_submit",
	},
	# C2-08: the supplier approval gate
	"Request for Quotation": {"before_submit": SUPPLIER_GATE},
	# C2-08 supplier gate; C2-11 approval by value (MD above) and promised dates
	"Purchase Order": {
		"validate": f"{PO_APPROVAL}.validate",
		"before_submit": [f"{PO_APPROVAL}.before_submit", SUPPLIER_GATE],
		"on_update": f"{PO_APPROVAL}.on_update",
		"on_submit": f"{PO_APPROVAL}.on_update",
		"on_cancel": f"{PO_APPROVAL}.on_update",
		# C2-12: submit creates the Purchase Tracker; cancel, close and Update Items recompute it
		"on_change": f"{TRACKER}.on_po_change",
		"on_trash": f"{TRACKER}.on_po_trash",
	},
}

# Every job is wrapped in @tracked_job so each run is recorded in PEPL Job Run
# and shown on the PEPL System Health page.
scheduler_events = {
	"daily": [
		"pepl_os.pepl_governance.jobs.daily_heartbeat",
		# C2-05: warranty and AMC expiry alerts
		"pepl_os.pepl_stores.capital_equipment.daily_equipment_alerts",
		# C2-08: supplier documents expiring / expired
		"pepl_os.pepl_purchase.supplier_approval.daily_supplier_approvals",
		# C2-12: every open Purchase Tracker, so days overdue move on each morning
		"pepl_os.pepl_purchase.tracker.refresh_open_purchase_trackers",
		# C2-14: each supplier's on-time delivery score
		"pepl_os.pepl_purchase.letdown.daily_delivery_scores",
		# C2-17: MSME days left; ToDo to Accounts at 7 days or fewer (PUR-MSME-DUE)
		"pepl_os.pepl_purchase.payments.daily_msme_payments",
		# C2-19: one ToDo per item below its reorder level (STO-REORDER)
		"pepl_os.pepl_stores.reorder.daily_reorder_alerts",
		# C3a-X3: yesterday's OEE for every machine (safety net; entries rebuild their day at once)
		"pepl_os.pepl_production.oee.daily_oee",
		# C3a-X8: one ToDo per job worker holding overdue material (PRD-JW-OVERDUE)
		"pepl_os.pepl_production.job_work.daily_job_work_alerts",
		# C3b-Q2: instruments due / overdue / never calibrated -> one ToDo each to Quality (QA-CAL-DUE)
		f"{CALIBRATION}.daily_calibration_alerts",
		# CR2: the Tender Access role and the Sales Order tender fields follow the list in site_config.json
		f"{TENDER_ACCESS}.daily_sync",
	],
	"cron": {
		# C3a-X4: every Monday 02:30, last week's MTBF / MTTR / CPC for every machine
		"30 2 * * 1": ["pepl_os.pepl_production.machine_week.weekly_machine_figures"],
		# C3a-X10: every morning 07:45, yesterday's Daily Stand-up, built and e-mailed
		"45 7 * * *": ["pepl_os.pepl_production.standup.daily_standup"],
	},
	"monthly": [
		# C2-19: next month's draft Reorder Review for the Stores HOD
		"pepl_os.pepl_stores.reorder.monthly_reorder_review",
		# C2-20: A / B / C class of every stock item by 12-month consumption value
		"pepl_os.pepl_stores.cycle_count.monthly_classify_abc",
	],
}

# C2-13: the Vendor Chase Letter print format lists a supplier's pending lines.
# C2-24: the RFQ Cover Letter's addressee and message.
jinja = {
	"methods": [
		"pepl_os.pepl_purchase.chase.pepl_chase_lines",
		"pepl_os.common.letterhead.pepl_rfq_letter",
	]
}

# C2-24: PEPL print formats come out of the PDF button on the official letterhead.
# Every other print format is passed straight to Frappe / ERPNext unchanged.
override_whitelisted_methods = {
	"frappe.utils.print_format.download_pdf": "pepl_os.common.letterhead.download_pdf",
	"erpnext.buying.doctype.request_for_quotation.request_for_quotation.get_pdf": (
		"pepl_os.common.letterhead.rfq_pdf"
	),
	# CR2: pepl_sales methods that read or change tender / Cost Sheet data without asking Frappe first
	"pepl_sales.pepl_sales.doctype.pepl_tender.pepl_tender.get_tender_summary": f"{TENDER_ACCESS}.get_tender_summary",
	"pepl_sales.pepl_sales.doctype.pepl_cst_cost_sheet.pepl_cst_cost_sheet.sync_components_from_product": (
		f"{TENDER_ACCESS}.sync_components_from_product"
	),
	"pepl_sales.pepl_sales.doctype.pepl_cst_cost_sheet.pepl_cst_cost_sheet.fetch_competitor_history": (
		f"{TENDER_ACCESS}.fetch_competitor_history"
	),
	"pepl_sales.pepl_sales.doctype.pepl_cst_cost_sheet.pepl_cst_cost_sheet.clone_cost_sheet_for_new_tender": (
		f"{TENDER_ACCESS}.clone_cost_sheet_for_new_tender"
	),
	"pepl_sales.pepl_sales.doctype.pepl_cst_cost_sheet.pepl_cst_cost_sheet.create_or_update_draft_bom": (
		f"{TENDER_ACCESS}.create_or_update_draft_bom"
	),
	"pepl_sales.pepl_sales.tender_cst_sync.backfill_existing_tender_cost_sheets": (
		f"{TENDER_ACCESS}.backfill_existing_tender_cost_sheets"
	),
	"pepl_sales.operational_notifications.run_tender_deadline_notifications": (
		f"{TENDER_ACCESS}.run_tender_deadline_notifications"
	),
}

# C2-24: the RFQ e-mail to suppliers attaches the cover letter on the letterhead.
override_doctype_class = {
	"Request for Quotation": "pepl_os.pepl_purchase.rfq.PEPLRequestforQuotation",
}
