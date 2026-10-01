// C2-07 - Material Request helper panel: stock, orders already placed, other requests, approved suppliers.
frappe.ui.form.on("Material Request", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.material_request_type !== "Purchase") return;
		if (frm.doc.docstatus === 1 && !["Stopped", "Cancelled"].includes(frm.doc.status)) {
			// C2-09
			frm.add_custom_button(__("RFQ by RM Group"), () => pepl.rfq_by_rm_group(frm)).addClass("btn-primary");
		}
		frappe
			.call("pepl_os.pepl_purchase.material_request.get_mr_panel", { material_request: frm.doc.name })
			.then((r) => {
				const rows = [];
				if (frm.doc.custom_sales_order) {
					rows.push({ text: __("Drafted from Sales Order {0}", [frm.doc.custom_sales_order]), colour: "gray" });
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

// C2-09 - One draft RFQ per RM group, the approved suppliers of each group ticked already.
frappe.provide("pepl");
pepl.rfq_by_rm_group = async function (frm) {
	const esc = frappe.utils.escape_html;
	const r = await frappe.call("pepl_os.pepl_purchase.rfq.get_rfq_plan", { material_request: frm.doc.name });
	const plan = r.message || { groups: [], skipped: [] };
	const skipped = plan.skipped.map((s) =>
		__("Row {0} {1} is already on {2}", [s.idx, esc(s.item_code), esc(s.rfq)])
	);
	if (!plan.groups.length) {
		frappe.msgprint(skipped.join("<br>") || __("No lines to send."), __("Nothing to send"));
		return;
	}
	const score = (v) => (v === null || v === undefined ? __("no score yet") : `${Math.round(v)}%`);
	const fields = [];
	if (skipped.length) {
		fields.push({ fieldtype: "HTML", fieldname: "skipped", options: `<p class="text-muted">${skipped.join("<br>")}</p>` });
	}
	plan.groups.forEach((g, i) => {
		fields.push({ fieldtype: "Section Break", label: g.rm_group ? esc(g.rm_group) : __("Items without an RM Group") });
		const lines = g.lines
			.map((l) => `<tr><td>${l.idx}</td><td>${esc(l.item_code)}</td><td>${esc(l.item_name || "")}</td><td class="text-right">${l.qty} ${esc(l.uom || "")}</td></tr>`)
			.join("");
		fields.push({
			fieldtype: "HTML",
			fieldname: `lines_${i}`,
			options: `<table class="table table-bordered table-condensed"><thead><tr><th>#</th><th>${__("Item")}</th><th>${__("Name")}</th><th class="text-right">${__("Qty")}</th></tr></thead><tbody>${lines}</tbody></table>`,
		});
		if (g.suppliers.length) {
			fields.push({
				fieldtype: "MultiCheck",
				fieldname: `suppliers_${i}`,
				label: __("Approved suppliers (untick to leave one out)"),
				columns: 1,
				options: g.suppliers.map((s) => ({
					label: `${esc(s.supplier_name || s.supplier)} · ${__(s.state)} · ${__("Delivery")} ${score(s.delivery_score)} · ${__("Quality")} ${score(s.quality_score)}${s.has_email ? "" : " · " + __("no e-mail on file, the RFQ will not be mailed to them")}`,
					value: s.supplier,
					checked: 1,
				})),
			});
		} else {
			fields.push({
				fieldtype: "HTML",
				fieldname: `none_${i}`,
				options: `<p class="text-danger">${
					g.rm_group ? __("No approved supplier for this RM Group yet.") : __("These items have no RM Group, so no supplier can be suggested.")
				} ${__("Add one below, or this group is left out.")}</p>`,
			});
		}
		fields.push({
			fieldtype: "MultiSelectList",
			fieldname: `extra_${i}`,
			label: __("Add another supplier"),
			description: __("A supplier not approved for this group needs a reason when the RFQ is submitted."),
			get_data: (txt) => frappe.db.get_link_options("Supplier", txt),
		});
	});
	const dialog = new frappe.ui.Dialog({
		title: __("Request for Quotation by RM Group"),
		size: "large",
		fields,
		primary_action_label: __("Create RFQs"),
		async primary_action(values) {
			const groups = plan.groups
				.map((g, i) => ({
					rm_group: g.rm_group,
					lines: g.lines.map((l) => l.name),
					suppliers: [...(values[`suppliers_${i}`] || []), ...(values[`extra_${i}`] || [])],
				}))
				.filter((g) => g.suppliers.length);
			if (!groups.length) {
				frappe.msgprint(__("Choose at least one supplier."));
				return;
			}
			const left = plan.groups.length - groups.length;
			const res = await frappe.call({
				method: "pepl_os.pepl_purchase.rfq.create_rfqs",
				args: { material_request: frm.doc.name, groups },
				freeze: true,
			});
			dialog.hide();
			const links = (res.message || []).map((n) => frappe.utils.get_form_link("Request for Quotation", n, true));
			frappe.msgprint(
				__("Draft RFQs created: {0}", [links.join(", ")]) +
					(left ? `<br>${__("{0} group(s) had no supplier and were left out.", [left])}` : "") +
					`<br>${__("Open each one, check it and submit it to e-mail the suppliers.")}`,
				__("RFQs created")
			);
			frm.reload_doc();
		},
	});
	dialog.show();
};
