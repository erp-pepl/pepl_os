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
	"Purchase Receipt": "public/js/purchase_receipt.js",
	# C2-16: Sales Order (CSM) picked from submitted orders of the company
	"Stock Entry": "public/js/stock_entry.js",
	# C2-16: "CSM Balance" button once the order holds customer-supplied material
	"Sales Order": "public/js/csm_sales_order.js",
	# C2-17: payment-priority panel ("Rank #4 this week · MSME due in 6 days")
	"Purchase Invoice": "public/js/purchase_invoice.js",
	"Supplier": "public/js/supplier_payments.js",
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
SUPPLIER_GATE = "pepl_os.pepl_purchase.supplier_approval.before_submit_gate"
PO_APPROVAL = "pepl_os.pepl_purchase.po_approval"
TRACKER = "pepl_os.pepl_purchase.tracker"
LETDOWN = "pepl_os.pepl_purchase.letdown"
HEAT = "pepl_os.pepl_stores.heat"
CSM = "pepl_os.pepl_stores.csm"
PAYMENTS = "pepl_os.pepl_purchase.payments"

doc_events = {
	"PEPL System Parameters": {
		# C2-02: no negative days, percentages 0-100, class A + B below 100.
		"validate": "pepl_os.pepl_purchase.params.validate_purchase_params",
		# A5: a changed audit-log retention applies immediately.
		"on_update": "pepl_os.pepl_governance.retention.on_parameters_update",
	},
	# C2-04: a company created after install gets PEPL's stores at once.
	"Company": {"on_update": "pepl_os.pepl_stores.stock_tree.on_company_update"},
	# C2-03: Udyam number required for MSME suppliers.
	"Supplier": {"validate": "pepl_os.pepl_purchase.supplier.validate_supplier"},
	# C2-17: MSME flag and pay-by date on the bill
	"Purchase Invoice": {"validate": f"{PAYMENTS}.validate_invoice"},
	# C2-17: one submitted entry per Tally voucher; Payment Run rows and MSME ToDos follow payments
	"Payment Entry": {
		"validate": f"{PAYMENTS}.validate_payment_entry",
		"on_submit": f"{PAYMENTS}.on_payment_entry_change",
		"on_cancel": f"{PAYMENTS}.on_payment_entry_change",
	},
	# C2-04: stock class from the Item Group; Capital never stock; CSM customer-provided.
	"Item": {"validate": "pepl_os.pepl_stores.stock_tree.validate_item"},
	# C2-04: customer-supplied material and PEPL material never share a store.
	# C2-15: heat number -> Batch on receipts, Batch -> heat on issues; the heat number gate
	# C2-16: every customer-supplied line moves against its Sales Order; the order shows its scrap option
	"Stock Entry": {
		"before_validate": [f"{CSM}.before_validate_stock_entry", f"{HEAT}.before_validate_stock_entry"],
		"validate": [CSM_SEGREGATION, f"{CSM}.validate_stock_entry"],
		"before_submit": f"{HEAT}.before_submit_stock_entry",
		"on_submit": f"{CSM}.on_stock_entry_change",
		"on_cancel": f"{CSM}.on_stock_entry_change",
	},
	"Purchase Receipt": {
		# C2-15: heat number -> Batch, the heat / MTC gate, the Receipt Log
		"before_validate": f"{HEAT}.before_validate_receipt",
		"validate": CSM_SEGREGATION,
		"before_submit": f"{HEAT}.before_submit_receipt",
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
	"Delivery Note": {"validate": CSM_SEGREGATION},
	# C2-07: draft the Material Request for bought-out and short raw material
	"Sales Order": {"on_submit": "pepl_os.pepl_purchase.material_request.on_sales_order_submit"},
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
	],
}

# C2-13: the Vendor Chase Letter print format lists a supplier's pending lines.
jinja = {"methods": ["pepl_os.pepl_purchase.chase.pepl_chase_lines"]}
