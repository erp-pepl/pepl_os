// C2-20 - Cycle Count: generate the sheet of due items, print it blind, type the counted qty; HOD above the limit.
frappe.ui.form.on("PEPL Cycle Count", {
	setup(frm) {
		frm.set_query("warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Generate count sheet"), () => {
				const go = () =>
					frappe
						.call({ method: "pepl_os.pepl_stores.cycle_count.generate_count_sheet", args: { name: frm.doc.name }, freeze: true })
						.then((r) => {
							frappe.show_alert({ message: __("{0} line(s) due for counting", [r.message]), indicator: "green" });
							frm.reload_doc();
						});
				if ((frm.doc.items || []).length) frappe.confirm(__("Replace the lines with a fresh sheet?"), go);
				else go();
			});
		}
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			const lines = frm.doc.items || [];
			const left = lines.filter((r) => !r.counted).length;
			const rows = [];
			if (!lines.length) rows.push({ text: __("No sheet yet: press Generate count sheet."), colour: "gray" });
			else if (left) rows.push({ text: __("{0} of {1} line(s) still to count", [left, lines.length]), colour: "orange" });
			else rows.push({ text: __("All {0} line(s) counted", [lines.length]), colour: "green" });
			if (frm.doc.needs_hod_approval) rows.push({ text: __("Variance above the approval limit: the Stores HOD must submit this count."), colour: "orange" });
			pepl.panel(frm, { title: __("Cycle count"), rows });
		}
	},
});
frappe.ui.form.on("PEPL Cycle Count Item", {
	counted_qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (flt(row.counted_qty) !== 0 && !row.counted) frappe.model.set_value(cdt, cdn, "counted", 1);
	},
});
