// C3b-P4 - Instrument panel: fit to measure today, due date and days left, last calibration and history, where it
// was used, draft inspections the Calibration Gate would stop, and what to do next.
frappe.ui.form.on("PEPL Instrument", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call("pepl_os.pepl_quality.instrument_panel.get_instrument_panel", { name: frm.doc.name }).then((r) => {
			if (r.message) pepl.panel(frm, { title: __("Calibration"), rows: r.message });
		});
		if (frm.doc.status !== "Scrapped") {
			frm.add_custom_button(__("New Calibration Record"), () =>
				frappe.new_doc("PEPL Calibration Record", { instrument: frm.doc.name })
			);
		}
	},
});
