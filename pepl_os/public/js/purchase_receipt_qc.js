// C3b-Q1 - Purchase Receipt: the "Incoming QC" panel (one line per line that is inspected) and the reason
// dialog when the incoming QC gate is Soft Block.
const PEPL_INCOMING_QC = "pepl_os.pepl_quality.incoming_qc";

frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call(`${PEPL_INCOMING_QC}.get_receipt_qc_panel`, { purchase_receipt: frm.doc.name }).then((r) => {
			if (!r.message) return;
			const actions =
				frm.doc.docstatus === 0
					? [
							{
								label: __("QC Inspections"),
								handler: () => frappe.set_route("List", "Quality Inspection", { reference_name: frm.doc.name }),
							},
						]
					: [];
			pepl.panel(frm, { title: __("Incoming QC"), rows: r.message, actions });
		});
	},
	async before_submit(frm) {
		const r = await frappe.call(`${PEPL_INCOMING_QC}.qc_gate_check`, { name: frm.doc.name });
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
