// C3a-X3 - Daily OEE: built by the system from the shift entries; the form only shows it.
// C3a-C1 - the headline also names Availability / Performance / Quality when below their own targets.
frappe.ui.form.on("PEPL OEE Daily", {
	refresh(frm) {
		frm.disable_save();
		if (frm.doc.oee !== undefined) {
			const ok = !frm.doc.below_target;
			// C3a-C1: name the factors below their own target
			const why = frm.doc.factors_below_target ? " · " + __("Below target: {0}", [frm.doc.factors_below_target]) : "";
			frm.dashboard.set_headline(
				__("OEE {0}% against a target of {1}%", [frm.doc.oee, frm.doc.target]) + why,
				ok ? "green" : "orange"
			);
		}
	},
});
