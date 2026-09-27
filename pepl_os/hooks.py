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
after_install = "pepl_os.install.after_install"
after_migrate = "pepl_os.install.after_migrate"

# Client scripts for standard DocTypes are added per deliverable, e.g.
# "Purchase Order": "public/js/purchase_order.js"
doctype_js = {}

# Document events are added per deliverable.
doc_events = {}

# Every job is wrapped in @tracked_job so each run is recorded in PEPL Job Run
# and shown on the PEPL System Health page.
scheduler_events = {
	"daily": [
		"pepl_os.pepl_governance.jobs.daily_heartbeat",
	],
}
