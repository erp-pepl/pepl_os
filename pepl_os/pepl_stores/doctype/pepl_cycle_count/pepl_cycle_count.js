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
		if (frm.doc.needs_hod_approval && frm.doc.docstatus === 0) {
			frm.dashboard.set_headline_alert(__("The variance is above the approval limit: the Stores HOD must submit this count."), "orange");
		}
	},
});
frappe.ui.form.on("PEPL Cycle Count Item", {
	counted_qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (flt(row.counted_qty) !== 0 && !row.counted) frappe.model.set_value(cdt, cdn, "counted", 1);
	},
});
