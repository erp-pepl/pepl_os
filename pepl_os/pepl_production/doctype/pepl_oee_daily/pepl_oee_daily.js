// C3a-X3 - Daily OEE: built by the system from the shift entries; the form only shows it.
frappe.ui.form.on("PEPL OEE Daily", {
	refresh(frm) {
		frm.disable_save();
		if (frm.doc.oee !== undefined) {
			const ok = !frm.doc.below_target;
			frm.dashboard.set_headline(
				__("OEE {0}% against a target of {1}%", [frm.doc.oee, frm.doc.target]),
				ok ? "green" : "orange"
			);
		}
	},
});
