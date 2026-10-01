// C2-18 - Scrap Rate: rate per kg from a date; the latest row on or before a date applies.
frappe.ui.form.on("PEPL Scrap Rate", {
	setup(frm) {
		frm.set_query("scrap_item", () => ({ query: "pepl_os.pepl_stores.scrap.scrap_item_query" }));
	},
});
