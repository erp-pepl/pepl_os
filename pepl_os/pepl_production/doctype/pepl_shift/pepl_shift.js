// C3a-X2 - Shift panel: planned production time and whether the shift runs past midnight.
frappe.ui.form.on("PEPL Shift", {
	refresh(frm) {
		if (frm.is_new()) return;
		const minutes = cint(frm.doc.planned_minutes);
		const rows = [
			{
				text: __("Planned production time: {0} minutes ({1} h {2} min) after {3} minutes of breaks", [
					minutes,
					Math.floor(minutes / 60),
					minutes % 60,
					cint(frm.doc.break_minutes),
				]),
				colour: "green",
			},
		];
		if (frm.doc.crosses_midnight) rows.push({ text: __("Runs past midnight: entries belong to the day the shift started"), colour: "gray" });
		if (!frm.doc.is_active) rows.push({ text: __("Inactive: not offered on shift entry"), colour: "gray" });
		pepl.panel(frm, { title: __("Shift"), rows });
	},
});
