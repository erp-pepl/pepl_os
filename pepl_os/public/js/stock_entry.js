// C2-15 - Stock Entry: the reason dialog when a heat-tracked line has no heat number (gate = Reason Required).
// C2-16 - Sales Order (CSM): only submitted orders of this company.
// C3a-P3 - an entry to or from a job worker's store: what is outside there for its items.
frappe.ui.form.on("Stock Entry", {
	setup(frm) {
		frm.set_query("custom_sales_order", () => ({ filters: { docstatus: 1, company: frm.doc.company } }));
	},
	refresh(frm) {
		// C3a-P3: material at a job worker for the items of this entry
		if (frm.is_new() || frm.doc.docstatus === 2) return;
		frappe.call("pepl_os.pepl_production.job_work_panel.get_stock_entry_job_work_panel", { stock_entry: frm.doc.name }).then((r) => {
			const rows = (r.message || {}).rows || [];
			if (rows.length) pepl.panel(frm, { title: __("Job work outstanding"), rows });
		});
	},
	async before_submit(frm) {
		const r = await frappe.call("pepl_os.pepl_stores.heat.heat_gate_check", { doctype: frm.doctype, name: frm.doc.name });
		if (r.message) {
			try {
				await pepl.override(frm, r.message.rule_code, r.message.message);
			} catch (e) {
				frappe.validated = false;
				throw e;
			}
		}
	},
});
