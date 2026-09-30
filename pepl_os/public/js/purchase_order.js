// C2-11 - Purchase Order: who may submit it (MD above the PO Approval Value), shown before submit.
const PEPL_PO = "pepl_os.pepl_purchase.po_approval.po_approval_info";

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 0) return;
		frappe.call(PEPL_PO, { purchase_order: frm.doc.name }).then((r) => {
			const i = r.message;
			if (!i) return;
			const rows = [];
			if (!i.threshold) {
				rows.push({ text: __("No PO Approval Value set: the Purchase Manager submits every PO."), colour: "gray" });
			} else if (i.needs_md) {
				rows.push({
					text: __("Total {0} is above the PO Approval Value {1}: needs MD approval.", [i.total_text, i.threshold_text]),
					colour: "orange",
				});
			} else {
				rows.push({
					text: __("Total {0} is within the PO Approval Value {1}: the Purchase Manager submits it.", [i.total_text, i.threshold_text]),
					colour: "green",
				});
			}
			if (i.refusal) rows.push({ text: i.refusal, colour: "red" });
			pepl.panel(frm, { title: __("PO approval"), rows });
		});
	},
	async before_submit(frm) {
		const r = await frappe.call(PEPL_PO, { purchase_order: frm.doc.name });
		if (r.message && r.message.refusal) {
			frappe.validated = false;
			frappe.throw({ title: __("Approval needed"), message: r.message.refusal });
		}
	},
});
