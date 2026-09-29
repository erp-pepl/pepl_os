// C2-05 - Capital Equipment panel: missing core documents and days of cover left.
frappe.ui.form.on("PEPL Capital Equipment", {
	refresh(frm) {
		if (frm.is_new()) return;
		const rows = [];
		const missing = (frm.doc.missing_documents || "").split("\n").filter(Boolean);
		if (missing.length) {
			missing.forEach((m) => rows.push({ text: __("Missing: {0}", [m]), colour: "red" }));
		} else {
			rows.push({ text: __("Invoice, manual and warranty / guarantee attached"), colour: "green" });
		}
		const cover = (label, days) => {
			if (days === null || days === undefined || days === "") return;
			const alert = cint(frappe.boot.pepl_supplier_doc_alert_days || 30);
			const colour = days < 0 ? "red" : days <= alert ? "orange" : "green";
			const text = days < 0 ? __("{0} expired {1} day(s) ago", [label, -days]) : __("{0}: {1} day(s) left", [label, days]);
			rows.push({ text, colour });
		};
		if (frm.doc.warranty_until) cover(__("Warranty"), frm.doc.warranty_days_left);
		if (frm.doc.amc_until) cover(__("AMC"), frm.doc.amc_days_left);
		pepl.panel(frm, { title: __("Equipment documents"), rows });
	},
});
