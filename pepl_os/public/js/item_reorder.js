// C2-19 - Item: reorder level against the projected stock, and "Create Material Request" when it is below.
frappe.ui.form.on("Item", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.is_stock_item || !(frm.doc.reorder_levels || []).length) return;
		frappe.call("pepl_os.pepl_stores.reorder.get_item_panel", { item_code: frm.doc.name }).then((r) => {
			const rows = r.message || [];
			if (!rows.length) return;
			pepl.panel(frm, { title: __("Reorder"), rows });
			rows.filter((x) => x.low).forEach((x) => {
				frm.add_custom_button(__("Create Material Request ({0})", [x.warehouse]), () =>
					frappe
						.call({ method: "pepl_os.pepl_stores.reorder.make_reorder_mr", args: { item_code: frm.doc.name, warehouse: x.warehouse }, freeze: true })
						.then((res) => frappe.set_route("Form", "Material Request", res.message))
				);
			});
		});
	},
});
