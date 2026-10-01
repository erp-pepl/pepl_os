// C2-15 - Stock Entry: the reason dialog when a heat-tracked line has no heat number (gate = Reason Required).
// C2-16 - Sales Order (CSM): only submitted orders of this company.
frappe.ui.form.on("Stock Entry", {
	setup(frm) {
		frm.set_query("custom_sales_order", () => ({ filters: { docstatus: 1, company: frm.doc.company } }));
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
