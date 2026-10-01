// C2-12 - Purchase Tracker: lines coloured by status, and "Refresh now".
const PEPL_TRK = "pepl_os.pepl_purchase.tracker";

frappe.ui.form.on("PEPL Purchase Tracker", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Refresh now"), () =>
			frappe.call({ method: `${PEPL_TRK}.refresh_now`, args: { name: frm.doc.name }, freeze: true }).then(() => frm.reload_doc())
		);
		frm.add_custom_button(__("Purchase Order"), () => frappe.set_route("Form", "Purchase Order", frm.doc.purchase_order));
		if (!["Completed", "Cancelled"].includes(frm.doc.status)) {
			// C2-13: e-mail the vendor one letter with all its pending lines
			frm.add_custom_button(__("Chase vendor"), () =>
				frappe.confirm(__("E-mail {0} the chase letter with all its pending lines?", [(frm.doc.supplier_name || frm.doc.supplier).bold()]), () =>
					frappe
						.call({ method: "pepl_os.pepl_purchase.chase.chase_vendor_now", args: { tracker: frm.doc.name }, freeze: true })
						.then(() => {
							frappe.show_alert({ message: __("Chase letter sent"), indicator: "green" });
							frm.reload_doc();
						})
				)
			).addClass("btn-primary");
			frm.add_custom_button(__("Preview chase letter"), () =>
				window.open(
					`/printview?doctype=Supplier&name=${encodeURIComponent(frm.doc.supplier)}&format=${encodeURIComponent("PEPL Vendor Chase Letter")}`
				)
			);
		}
		frappe.call(`${PEPL_TRK}.get_panel`, { name: frm.doc.name }).then((r) => {
			if (r.message) pepl.panel(frm, { title: __("Delivery status"), rows: r.message.rows });
		});
	},
});
