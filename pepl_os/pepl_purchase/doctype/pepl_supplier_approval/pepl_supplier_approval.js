// C2-08 - Supplier Approval form: checklist sync and a panel of what is missing or expiring.
frappe.ui.form.on("PEPL Supplier Approval", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Sync checklist"), () =>
			frappe
				.call("pepl_os.pepl_purchase.supplier_approval.sync_now", { name: frm.doc.name })
				.then((r) => {
					frappe.show_alert({ message: __("{0} document(s) added", [r.message || 0]), indicator: "green" });
					frm.reload_doc();
				})
		);
		const colours = { Available: "green", Expiring: "orange", Expired: "red", Pending: "red", "Not Applicable": "gray" };
		const rows = [];
		const problems = (frm.doc.documents || []).filter(
			(d) => d.mandatory && !["Available", "Not Applicable"].includes(d.status)
		);
		if (!problems.length) {
			rows.push({ text: __("All mandatory documents in order"), colour: "green" });
		}
		problems.forEach((d) =>
			rows.push({
				text: `${d.requirement}: ${__(d.status)}${d.expiry_date ? " (" + frappe.datetime.str_to_user(d.expiry_date) + ")" : ""}`,
				colour: colours[d.status] || "gray",
			})
		);
		if (frm.doc.earliest_expiry) {
			rows.push({ text: __("Earliest expiry: {0}", [frappe.datetime.str_to_user(frm.doc.earliest_expiry)]), colour: "gray" });
		}
		pepl.panel(frm, { title: __("Approval documents"), rows });
	},
});
