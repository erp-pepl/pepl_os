// C3a-X1 - Shift Production Entry: pick lists limited to what fits, and the shift panel.
// C3a-P5 - Entry aids: gaps (with a button to add downtime rows for them), Job Cards left, speed, open Job Cards.
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
		// C3a-P5: entry aids - gaps in the shift, Job Cards left, speed against standard, open Job Cards
		frappe.call("pepl_os.pepl_production.spr_aids.get_spr_aids", { name: frm.doc.name }).then((r) => {
			const data = r.message || {};
			const actions = [];
			if (frm.doc.docstatus === 0 && (data.gaps || []).length) {
				actions.push({
					label: __("Add rows for the gaps"),
					handler: () => {
						data.gaps.forEach((gap) => frm.add_child("downtime", { from_time: gap.from_time, to_time: gap.to_time }));
						frm.refresh_field("downtime");
						frappe.show_alert({
							message: __("{0} downtime row(s) added: pick the category of each, then save.", [data.gaps.length]),
							indicator: "orange",
						});
					},
				});
			}
			pepl.panel(frm, { title: __("Entry aids"), rows: data.rows || [], actions });
		});
	},
	async before_submit(frm) {
		// C3a-X7: Soft Block - an operator below the minimum skill level needs a reason, logged with the user's name.
		const r = await frappe.call("pepl_os.pepl_production.skill.skill_gate_check", { name: frm.doc.name });
		if (r.message) {
			try {
				await pepl.override(frm, r.message.rule_code, r.message.message);
			} catch (e) {
				frappe.validated = false;
				throw e;
			}
		}
	},
	workstation(frm) {
		// Job Cards belong to one machine: rows picked for another machine would be refused on save.
		(frm.doc.production || []).forEach((row) => {
			if (row.job_card) frappe.model.set_value(row.doctype, row.name, "job_card", "");
		});
	},
});
