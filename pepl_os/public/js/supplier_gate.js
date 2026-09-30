// C2-08 - Before submitting an RFQ or PO to a supplier who is not approved, ask for a reason.
// The server refuses the submit without it (rule SUP-NOT-APPROVED) and the reason goes to the Audit Trail.
// Loaded as doctype_js for both forms, so register once only.
frappe.provide("pepl");
if (!pepl.supplier_gate_registered) {
pepl.supplier_gate_registered = true;
["Request for Quotation", "Purchase Order"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		async before_submit(frm) {
			const r = await frappe.call("pepl_os.pepl_purchase.supplier_approval.gate_check", {
				doctype: frm.doctype,
				name: frm.doc.name,
			});
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
});
}
