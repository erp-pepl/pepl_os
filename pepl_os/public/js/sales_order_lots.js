// C3b-B1 - Sales Order: "Inspection Lot" (Create) for an order inspected by an outside agency.
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		frm.add_custom_button(
			__("Inspection Lot"),
			() => frappe.new_doc("PEPL Inspection Lot", { sales_order: frm.doc.name }),
			__("Create")
		);
	},
});
