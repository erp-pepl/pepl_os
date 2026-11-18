// C3b-Q5 - Delivery Note: the "Dispatch QC" panel (final inspection of each line, open NCRs) and the reason dialog
// when the dispatch gate is Soft Block.
const PEPL_DISPATCH = "pepl_os.pepl_quality.dispatch";

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call(`${PEPL_DISPATCH}.get_dispatch_panel`, { delivery_note: frm.doc.name }).then((r) => {
			if (r.message) pepl.panel(frm, { title: __("Dispatch QC"), rows: r.message });
		});
	},
	async before_submit(frm) {
		const r = await frappe.call(`${PEPL_DISPATCH}.dispatch_gate_check`, { name: frm.doc.name });
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
