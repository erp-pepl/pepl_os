// C3a-X2 - Downtime category panel: what this stop does to OEE and MTBF / MTTR, in plain words.
frappe.ui.form.on("PEPL Downtime Category", {
	refresh(frm) {
		if (frm.is_new()) return;
		const colour = frm.doc.stop_type === "Unplanned" ? (frm.doc.is_breakdown ? "red" : "orange") : "green";
		const rows = [{ text: frm.doc.effect || "", colour }];
		if (!frm.doc.is_active) rows.push({ text: __("Inactive: operators cannot choose it"), colour: "gray" });
		pepl.panel(frm, { title: __("Downtime category"), rows });
	},
	stop_type(frm) {
		if (frm.doc.stop_type !== "Unplanned") frm.set_value("is_breakdown", 0);
	},
});
