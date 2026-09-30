// C2-12 - Purchase Tracker: lines coloured by status, and "Refresh now".
const PEPL_TRK = "pepl_os.pepl_purchase.tracker";

frappe.ui.form.on("PEPL Purchase Tracker", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Refresh now"), () =>
			frappe.call({ method: `${PEPL_TRK}.refresh_now`, args: { name: frm.doc.name }, freeze: true }).then(() => frm.reload_doc())
		);
		frm.add_custom_button(__("Purchase Order"), () => frappe.set_route("Form", "Purchase Order", frm.doc.purchase_order));
		frappe.call(`${PEPL_TRK}.get_panel`, { name: frm.doc.name }).then((r) => {
			if (r.message) pepl.panel(frm, { title: __("Delivery status"), rows: r.message.rows });
		});
	},
});
