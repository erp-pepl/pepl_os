// C2-15 - Purchase Receipt: heat panel, "Split by heat", and the reason dialog when the gate is Reason Required.
const PEPL_HEAT = "pepl_os.pepl_stores.heat";

frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call(`${PEPL_HEAT}.get_receipt_panel`, { purchase_receipt: frm.doc.name }).then((r) => {
			if (r.message) pepl.panel(frm, { title: __("Heat numbers"), rows: r.message });
		});
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Split by heat"), () => pepl.split_by_heat(frm));
		}
	},
	async before_submit(frm) {
		const r = await frappe.call(`${PEPL_HEAT}.heat_gate_check`, { doctype: frm.doctype, name: frm.doc.name });
		if (r.message) {
			try {
				await pepl.override(frm, r.message.rule_code, r.message.message);
			} catch (e) {
				frappe.validated = false;
				throw e;
			}
		}
	},
});

frappe.provide("pepl");
pepl.split_by_heat = function (frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the receipt first."));
		return;
	}
	const lines = (frm.doc.items || []).map((r) => ({ label: `${r.idx}: ${r.item_code} (${r.qty} ${r.uom || ""})`, value: r.name }));
	const dialog = new frappe.ui.Dialog({
		title: __("Split a line by heat number"),
		size: "large",
		fields: [
			{ fieldtype: "Select", fieldname: "row_name", label: __("Line"), options: lines, reqd: 1 },
			{
				fieldtype: "Table",
				fieldname: "splits",
				label: __("Heats"),
				cannot_add_rows: false,
				in_place_edit: true,
				data: [{}, {}],
				fields: [
					{ fieldtype: "Data", fieldname: "heat_number", label: __("Heat Number"), in_list_view: 1, reqd: 1 },
					{ fieldtype: "Float", fieldname: "qty", label: __("Qty"), in_list_view: 1, reqd: 1 },
				],
			},
			{
				fieldtype: "HTML",
				fieldname: "help",
				options: `<p class="text-muted">${__("The quantities must add up to the line's quantity. Rate and Purchase Order link are kept. Attach each heat's test certificate on its new line afterwards.")}</p>`,
			},
		],
		primary_action_label: __("Split"),
		primary_action(values) {
			frappe
				.call({
					method: `${PEPL_HEAT}.split_by_heat`,
					args: { purchase_receipt: frm.doc.name, row_name: values.row_name, splits: values.splits || [] },
					freeze: true,
				})
				.then(() => {
					dialog.hide();
					frm.reload_doc();
				});
		},
	});
	dialog.show();
};
