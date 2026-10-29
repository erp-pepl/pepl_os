// C3a-P1 - Job Order (Work Order) status: quantity against target, routing progress, delivery and LD.
// C3a-P4 - Customer-supplied material: what this Job Order and its Sales Order still need, against what is held.
frappe.ui.form.on("Work Order", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus === 2) return;
		// C3a-P4: is the customer's material there (draft and submitted Job Orders)
		frappe.call("pepl_os.pepl_production.csm_panel.get_job_order_csm_panel", { work_order: frm.doc.name }).then((r) => {
			const rows = (r.message || {}).rows || [];
			if (rows.length) pepl.panel(frm, { title: __("Customer-supplied material"), rows });
		});
		if (frm.doc.docstatus !== 1) return;
		frappe
			.call("pepl_os.pepl_production.job_order_panel.get_job_order_panel", { work_order: frm.doc.name })
			.then((r) => pepl.panel(frm, { title: __("Job Order status"), rows: (r.message || {}).rows || [] }));
	},
});
