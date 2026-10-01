// C2-17 - Payment Run: build this week's bills from the worklist, approve, submit; Accounts pays.
frappe.ui.form.on("PEPL Payment Run", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Build from worklist"), () => {
				const go = () =>
					frappe
						.call({ method: "pepl_os.pepl_purchase.payments.build_from_worklist", args: { name: frm.doc.name }, freeze: true })
						.then((r) => {
							frappe.show_alert({ message: __("{0} bill(s) added in rank order", [r.message]), indicator: "green" });
							frm.reload_doc();
						});
				if ((frm.doc.items || []).length) frappe.confirm(__("Replace the bills with this week's worklist?"), go);
				else go();
			});
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Vendor Payment Priority"), () =>
				frappe.set_route("query-report", "PEPL Vendor Payment Priority", { company: frm.doc.company })
			);
		}
	},
});
