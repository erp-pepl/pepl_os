// C3b-B1 - Inspection Lot: the steps (lot request, proof, bulk lot offer, IC), the order line, what comes next.
frappe.ui.form.on("PEPL Inspection Lot", {
	setup(frm) {
		frm.set_query("item", () => ({
			query: "pepl_os.pepl_quality.inspection_lot.order_items",
			filters: { sales_order: frm.doc.sales_order },
		}));
		frm.set_query("internal_inspection", () => ({
			filters: { item_code: frm.doc.item, docstatus: 1, status: "Accepted" },
		}));
		["lot_request_document", "proof_schedule_document", "offer_document"].forEach((f) =>
			frm.set_query(f, () => ({ filters: { sales_order: frm.doc.sales_order } }))
		);
	},
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call("pepl_os.pepl_quality.inspection_lot.get_lot_panel", { name: frm.doc.name }).then((r) => {
			if (r.message) pepl.panel(frm, { title: __("Inspection Lot"), rows: r.message });
		});
	},
});
