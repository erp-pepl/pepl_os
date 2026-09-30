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
	# C2-04: stock class from the Item Group; Capital never stock; CSM customer-provided.
	"Item": {"validate": "pepl_os.pepl_stores.stock_tree.validate_item"},
	# C2-04: customer-supplied material and PEPL material never share a store.
	"Stock Entry": {"validate": CSM_SEGREGATION},
	"Purchase Receipt": {
		"validate": CSM_SEGREGATION,
		# C2-12: a receipt recomputes the trackers of its Purchase Orders
		"on_submit": f"{TRACKER}.on_receipt_change",
		"on_cancel": f"{TRACKER}.on_receipt_change",
	},
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
	],
}
