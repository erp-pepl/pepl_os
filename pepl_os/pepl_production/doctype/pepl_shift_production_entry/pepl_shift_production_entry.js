// C3a-X1 - Shift Production Entry: pick lists limited to what fits, and the shift panel.
frappe.ui.form.on("PEPL Shift Production Entry", {
	setup(frm) {
		frm.set_query("shift", () => ({ filters: { is_active: 1 } }));
		frm.set_query("operator", () => ({ filters: { status: "Active" } }));
		frm.set_query("workstation", () => ({ filters: { disabled: 0 } }));
		frm.set_query("job_card", "production", () => ({
			filters: { workstation: frm.doc.workstation, docstatus: 0 },
		}));
		frm.set_query("downtime_category", "downtime", () => ({ filters: { is_active: 1 } }));
		frm.set_query("item_code", "consumables", () => ({
			filters: [
				["item_group", "descendants of (inclusive)", "Consumables"],
				["is_stock_item", "=", 1],
				["disabled", "=", 0],
			],
		}));
		frm.set_query("tool_item", "tool_changes", () => ({
			filters: [["item_group", "descendants of (inclusive)", "Tools & Gauges"]],
		}));
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},
	refresh(frm) {
		if (frm.is_new()) return;
		frappe
			.call({ method: "pepl_os.pepl_production.spr.get_spr_panel", args: { name: frm.doc.name } })
			.then((r) => pepl.panel(frm, { title: __("Shift"), rows: (r.message || {}).rows || [] }));
	},
	workstation(frm) {
		// Job Cards belong to one machine: rows picked for another machine would be refused on save.
		(frm.doc.production || []).forEach((row) => {
			if (row.job_card) frappe.model.set_value(row.doctype, row.name, "job_card", "");
		});
	},
});
