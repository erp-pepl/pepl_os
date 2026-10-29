// C3a-X2 - Downtime category panel: what this stop does to OEE and MTBF / MTTR, in plain words.
// C3a-C1 - Use and cleanup: how often it is used, look-alikes, and Merge into (same kind of stop only).
frappe.ui.form.on("PEPL Downtime Category", {
	refresh(frm) {
		if (frm.is_new()) return;
		const colour = frm.doc.stop_type === "Unplanned" ? (frm.doc.is_breakdown ? "red" : "orange") : "green";
		const rows = [{ text: frm.doc.effect || "", colour }];
		if (!frm.doc.is_active) rows.push({ text: __("Inactive: operators cannot choose it"), colour: "gray" });
		pepl.panel(frm, { title: __("Downtime category"), rows });
		// C3a-C1: how often it is used, look-alike categories, and "Merge into" for the Production Manager
		frappe.call("pepl_os.pepl_production.config.get_downtime_category_review", { name: frm.doc.name }).then((r) => {
			const data = r.message || {};
			const actions = [];
			if (data.can_merge && frm.doc.is_active) {
				actions.push({ label: __("Merge into another category"), handler: () => pepl.merge_downtime_category(frm) });
			}
			pepl.panel(frm, { title: __("Use and cleanup"), rows: data.rows || [], actions });
		});
	},
	stop_type(frm) {
		if (frm.doc.stop_type !== "Unplanned") frm.set_value("is_breakdown", 0);
	},
});

frappe.provide("pepl");
pepl.merge_downtime_category = function (frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Merge {0} into", [frm.doc.name]),
		fields: [
			{
				fieldname: "target",
				fieldtype: "Link",
				options: "PEPL Downtime Category",
				label: __("Category to keep"),
				reqd: 1,
				get_query: () => ({
					filters: {
						name: ["!=", frm.doc.name],
						is_active: 1,
						stop_type: frm.doc.stop_type,
						is_breakdown: frm.doc.is_breakdown,
					},
				}),
				description: __("Only categories of the same stop type and breakdown flag. Every shift-entry row moves to it; this category is switched off."),
			},
		],
		primary_action_label: __("Merge"),
		primary_action(values) {
			frappe
				.call("pepl_os.pepl_production.config.merge_downtime_category", { source: frm.doc.name, target: values.target })
				.then((r) => {
					dialog.hide();
					frappe.show_alert({ message: (r.message || {}).message || __("Merged"), indicator: "green" });
					frm.reload_doc();
				});
		},
	});
	dialog.show();
};
