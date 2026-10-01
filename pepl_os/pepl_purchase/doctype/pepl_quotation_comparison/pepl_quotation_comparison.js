// C2-10 - Quotation Comparison: load quotations, send for approval, and a summary panel.
const QC = "pepl_os.pepl_purchase.quotation_comparison";

frappe.ui.form.on("PEPL Quotation Comparison", {
	refresh(frm) {
		if (frm.is_new()) return;
		const act = (method, done) =>
			frappe.call({ method: `${QC}.${method}`, args: { name: frm.doc.name }, freeze: true }).then((r) => {
				if (done) done(r.message);
				frm.reload_doc();
			});
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Load Quotations"), () =>
				frappe.confirm(__("Read the submitted Supplier Quotations again? Awards go back to L1."), () =>
					act("reload_quotations", (n) => frappe.show_alert({ message: __("{0} quotation line(s) loaded", [n]), indicator: "green" }))
				)
			);
			if (frm.doc.status === "Draft") {
				frm.add_custom_button(__("Send for Approval"), () => {
					const go = () => act("send_for_approval");
					frm.is_dirty() ? frm.save().then(go) : go();
				}).addClass("btn-primary");
			} else if (frm.doc.status === "Pending Approval") {
				frm.add_custom_button(__("Back to Draft"), () => act("back_to_draft"));
			}
		}
		frappe.call({ method: `${QC}.get_panel`, args: { name: frm.doc.name } }).then((r) => {
			const rows = r.message || [];
			if (frm.doc.purchase_orders) {
				rows.unshift({ text: __("Purchase Orders: {0}", [frm.doc.purchase_orders.split("\n").join(", ")]), colour: "gray" });
			}
			pepl.panel(frm, { title: __("Comparison"), rows });
		});
	},
});

frappe.ui.form.on("PEPL Quotation Comparison Row", {
	awarded_qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.awarded_qty > 0 && !row.is_l1) {
			frappe.show_alert({ message: __("{0} is not L1 for line {1}: write the reason in the row.", [row.supplier, row.line]), indicator: "orange" });
		}
	},
});
