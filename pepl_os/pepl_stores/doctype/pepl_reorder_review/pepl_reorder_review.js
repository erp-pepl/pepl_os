// C2-19 - Reorder Review: compute suggestions from consumption; accepted rows go into each Item's Reorder table on submit.
frappe.ui.form.on("PEPL Reorder Review", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.is_new()) return;
		frm.add_custom_button(__("Compute suggestions"), () => {
			const go = () =>
				frappe
					.call({ method: "pepl_os.pepl_stores.reorder.compute_suggestions", args: { name: frm.doc.name }, freeze: true })
					.then((r) => {
						frappe.show_alert({ message: __("{0} item(s) to review", [r.message]), indicator: "green" });
						frm.reload_doc();
					});
			if ((frm.doc.items || []).length) frappe.confirm(__("Replace the rows with fresh suggestions?"), go);
			else go();
		});
	},
});
