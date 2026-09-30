// C2-07 - Material Request helper panel: stock, orders already placed, other requests, approved suppliers.
frappe.ui.form.on("Material Request", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.material_request_type !== "Purchase") return;
		frappe
			.call("pepl_os.pepl_purchase.material_request.get_mr_panel", { material_request: frm.doc.name })
			.then((r) => {
				const rows = [];
				if (frm.doc.custom_sales_order) {
					rows.push({ text: __("Drafted from Sales Order {0}", [frm.doc.custom_sales_order]), colour: "blue" });
				}
				(r.message || []).forEach((l) => {
					rows.push({
						text: __("Row {0} {1}: on hand {2}, on order {3}", [l.idx, l.item_code, l.on_hand, l.on_order]),
						colour: "gray",
					});
					if (l.requested_elsewhere > 0) {
						rows.push({
							text: __("Row {0}: {1} already requested in other open Material Requests", [l.idx, l.requested_elsewhere]),
							colour: "orange",
						});
					}
					rows.push({
						text: l.rm_group
							? __("Row {0}: {1} approved supplier(s) for {2}", [l.idx, l.approved_suppliers, l.rm_group])
							: __("Row {0}: item has no RM Group, so no approved suppliers can be suggested", [l.idx]),
						colour: l.rm_group && l.approved_suppliers > 0 ? "green" : "red",
					});
				});
				pepl.panel(frm, { title: __("Purchase check"), rows });
			});
	},
});
