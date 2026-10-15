// C3a-X2 - Operator panel: kiosk PIN and machine groups with level and validity.
frappe.ui.form.on("PEPL Operator", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe
			.call({ method: "pepl_os.pepl_production.masters.get_operator_panel", args: { name: frm.doc.name } })
			.then((r) => pepl.panel(frm, { title: __("Operator"), rows: (r.message || {}).rows || [] }));
	},
});
