// C2-17 - Supplier: its open bills in this week's payment order.
frappe.ui.form.on("Supplier", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call("pepl_os.pepl_purchase.payments.get_supplier_panel", { supplier: frm.doc.name }).then((r) => {
			if (r.message && r.message.length) pepl.panel(frm, { title: __("Payment priority"), rows: r.message });
		});
	},
});
