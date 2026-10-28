// C3a-P1 - Job Order (Work Order) status: quantity against target, routing progress, delivery and LD.
frappe.ui.form.on("Work Order", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 1) return;
		frappe
			.call("pepl_os.pepl_production.job_order_panel.get_job_order_panel", { work_order: frm.doc.name })
			.then((r) => pepl.panel(frm, { title: __("Job Order status"), rows: (r.message || {}).rows || [] }));
	},
});
