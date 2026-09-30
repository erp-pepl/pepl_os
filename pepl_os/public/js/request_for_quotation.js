// C2-10 - Open (or create) the Quotation Comparison for a submitted RFQ.
frappe.ui.form.on("Request for Quotation", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		frm.add_custom_button(__("Quotation Comparison"), () =>
			frappe
				.call({
					method: "pepl_os.pepl_purchase.quotation_comparison.make_comparison",
					args: { request_for_quotation: frm.doc.name },
					freeze: true,
				})
				.then((r) => r.message && frappe.set_route("Form", "PEPL Quotation Comparison", r.message))
		).addClass("btn-primary");
	},
});
