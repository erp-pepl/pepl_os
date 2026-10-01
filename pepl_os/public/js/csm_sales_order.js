// C2-16 - Sales Order: the customer's material held against this order.
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frm.doc.custom_has_csm) return;
		frm.add_custom_button(__("CSM Balance"), () => {
			frappe.set_route("query-report", "PEPL CSM Balance by Order", { sales_order: frm.doc.name });
		}, __("View"));
	},
});
