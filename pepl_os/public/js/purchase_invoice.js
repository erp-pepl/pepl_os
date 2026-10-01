// C2-17 - Purchase Invoice: where this bill stands in this week's payment order.
frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !(frm.doc.outstanding_amount > 0)) return;
		frappe.call("pepl_os.pepl_purchase.payments.get_invoice_panel", { purchase_invoice: frm.doc.name }).then((r) => {
			if (r.message && r.message.length) pepl.panel(frm, { title: __("Payment priority"), rows: r.message });
		});
	},
});
