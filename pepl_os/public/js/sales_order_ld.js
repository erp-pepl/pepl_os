// C3a-X11 - Sales Order: the LD clause and what late delivery costs as of today.
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frm.doc.custom_ld_applicable) return;
		frappe
			.call("pepl_os.pepl_production.ld.get_ld_exposure", { sales_order: frm.doc.name })
			.then((r) => {
				const x = r.message || {};
				const t = x.terms || {};
				const money = (v) => format_currency(v || 0, frm.doc.currency);
				const rows = [
					{
						text: __("LD {0}% per {1}, cap {2}% ({3}), grace {4} days", [
							t.rate, __(t.period || "Week").toLowerCase(), t.cap, __(t.basis || ""), t.grace || 0,
						]),
						colour: "gray",
					},
				];
				if (x.total) {
					rows.push({
						text: __("LD exposure today: {0} on {1} late line(s) (cap {2})", [money(x.total), x.late_lines, money(x.cap_amount)]),
						colour: "red",
					});
				} else {
					rows.push({ text: __("No LD so far: nothing late"), colour: "green" });
				}
				pepl.panel(frm, { title: __("Liquidated Damages"), rows });
			});
	},
});
