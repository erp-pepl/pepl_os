// C2-18 - Scrap Weighment: gross - tare = net kg; the scrap rate of the day; CSM scrap against its order.
frappe.ui.form.on("PEPL Scrap Weighment", {
	setup(frm) {
		frm.set_query("scrap_item", () =>
			frm.doc.source === "CSM"
				? { filters: { item_group: "CSM Scrap", disabled: 0 } }
				: { query: "pepl_os.pepl_stores.scrap.scrap_item_query" }
		);
		frm.set_query("sales_order", () => ({ filters: { docstatus: 1, company: frm.doc.company } }));
	},
	gross_kg: (frm) => frm.trigger("net"),
	tare_kg: (frm) => frm.trigger("net"),
	net(frm) {
		frm.set_value("net_kg", flt(frm.doc.gross_kg) - flt(frm.doc.tare_kg));
	},
	source(frm) {
		frm.set_value("scrap_item", null);
		if (frm.doc.source !== "CSM") frm.set_value("sales_order", null);
	},
	scrap_item(frm) {
		if (!frm.doc.scrap_item || frm.doc.source === "CSM") return;
		frappe.call("pepl_os.pepl_stores.scrap.get_rate", { scrap_item: frm.doc.scrap_item, on_date: frm.doc.weighment_date }).then((r) => {
			if (!r.message) frappe.show_alert({ message: __("No scrap rate for {0} yet: add one in PEPL Scrap Rate.", [frm.doc.scrap_item]), indicator: "orange" });
		});
	},
});
