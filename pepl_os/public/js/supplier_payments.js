// C2-08 + C2-17 (C2-22) - Supplier: approval state and expiry, and its open bills in this week's payment order.
frappe.ui.form.on("Supplier", {
	refresh(frm) {
		if (frm.is_new()) return;
		pepl.supplier_approval_panel(frm);
		frappe.call("pepl_os.pepl_purchase.payments.get_supplier_panel", { supplier: frm.doc.name }).then((r) => {
			if (r.message && r.message.length) pepl.panel(frm, { title: __("Payment priority"), rows: r.message });
		});
	},
});

frappe.provide("pepl");
pepl.supplier_approval_panel = function (frm) {
	const state = frm.doc.custom_approval_state;
	const expiry = frm.doc.custom_approval_expiry;
	const alertDays = cint(frappe.boot.pepl_supplier_doc_alert_days || 30);
	const rows = [];
	if (["Approved", "Conditionally Approved"].includes(state)) {
		if (expiry) {
			const days = frappe.datetime.get_day_diff(expiry, frappe.datetime.get_today());
			if (days < 0) rows.push({ text: __("{0}, but a document expired on {1}", [__(state), frappe.datetime.str_to_user(expiry)]), colour: "red" });
			else if (days <= alertDays) rows.push({ text: __("{0}: a document expires in {1} day(s) ({2})", [__(state), days, frappe.datetime.str_to_user(expiry)]), colour: "orange" });
			else rows.push({ text: __("{0}, valid until {1}", [__(state), frappe.datetime.str_to_user(expiry)]), colour: "green" });
		} else {
			rows.push({ text: __(state), colour: "green" });
		}
	} else if (["Suspended", "Expired", "Rejected"].includes(state)) {
		rows.push({ text: __("{0}: buying from this supplier needs a reason", [__(state)]), colour: "red" });
	} else {
		rows.push({ text: __("Not approved yet: buying from this supplier needs a reason"), colour: state ? "gray" : "red" });
	}
	frappe.db.get_value("PEPL Supplier Approval", { supplier: frm.doc.name }, "name").then((r) => {
		const name = r.message && r.message.name;
		pepl.panel(frm, {
			title: __("Supplier approval"),
			rows,
			actions: [
				{
					label: name ? __("Supplier Approval") : __("Start Supplier Approval"),
					handler: () =>
						name
							? frappe.set_route("Form", "PEPL Supplier Approval", name)
							: frappe.new_doc("PEPL Supplier Approval", { supplier: frm.doc.name }),
				},
			],
		});
	});
};
