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
	"Request for Quotation": "public/js/supplier_gate.js",
	"Purchase Order": "public/js/supplier_gate.js",
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

doc_events = {
	"PEPL System Parameters": {
		# C2-02: no negative days, percentages 0-100, class A + B below 100.
		"validate": "pepl_os.pepl_purchase.params.validate_purchase_params",
		# A5: a changed audit-log retention applies immediately.
		"on_update": "pepl_os.pepl_governance.retention.on_parameters_update",
	},
	# C2-03: Udyam number required for MSME suppliers.
	"Supplier": {"validate": "pepl_os.pepl_purchase.supplier.validate_supplier"},
	# C2-04: stock class from the Item Group; Capital never stock; CSM customer-provided.
	"Item": {"validate": "pepl_os.pepl_stores.stock_tree.validate_item"},
	# C2-04: customer-supplied material and PEPL material never share a store.
	"Stock Entry": {"validate": CSM_SEGREGATION},
	"Purchase Receipt": {"validate": CSM_SEGREGATION},
	"Delivery Note": {"validate": CSM_SEGREGATION},
	# C2-07: draft the Material Request for bought-out and short raw material
	"Sales Order": {"on_submit": "pepl_os.pepl_purchase.material_request.on_sales_order_submit"},
	# C2-08: the supplier approval gate
	"Request for Quotation": {"before_submit": SUPPLIER_GATE},
	"Purchase Order": {"before_submit": SUPPLIER_GATE},
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
	],
}
