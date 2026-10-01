// C2-18 - Scrap Sale: buyer from Scrap Buyers, lines from Scrap Yard / CSM Scrap; prints a gate pass.
frappe.ui.form.on("PEPL Scrap Sale", {
	setup(frm) {
		frm.set_query("buyer", () => ({ filters: { customer_group: "Scrap Buyers" } }));
		frm.set_query("scrap_item", "items", () => ({ query: "pepl_os.pepl_stores.scrap.scrap_item_query", filters: { include_csm: 1 } }));
		frm.set_query("warehouse", "items", () => ({ filters: { company: frm.doc.company, warehouse_name: ["in", ["Scrap Yard", "CSM Scrap"]] } }));
		frm.set_query("sales_order", "items", () => ({ filters: { docstatus: 1, company: frm.doc.company } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Gate Pass"), () => frm.print_doc ? frm.print_doc() : frappe.set_route("print", frm.doctype, frm.doc.name));
		}
	},
});
frappe.ui.form.on("PEPL Scrap Sale Item", {
	kg: (frm, cdt, cdn) => pepl_scrap_amount(frm, cdt, cdn),
	rate: (frm, cdt, cdn) => pepl_scrap_amount(frm, cdt, cdn),
	scrap_item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.scrap_item) return;
		frappe.call("pepl_os.pepl_stores.scrap.get_rate", { scrap_item: row.scrap_item, on_date: frm.doc.sale_date }).then((r) => {
			if (r.message && !row.rate) frappe.model.set_value(cdt, cdn, "rate", r.message);
		});
	},
});
function pepl_scrap_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.kg) * flt(row.rate));
}
