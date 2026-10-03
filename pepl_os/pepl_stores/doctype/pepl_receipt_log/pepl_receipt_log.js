// Brief Phase 2 - Receipt Log heat panel: heat number, test certificate, QC status, and the recall trace.
frappe.ui.form.on("PEPL Receipt Log", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call("pepl_os.pepl_stores.heat.get_receipt_log_panel", { name: frm.doc.name }).then((r) => {
			const d = r.message;
			if (!d) return;
			const actions = [];
			if (d.heat_number) {
				actions.push({
					label: __("Heat Number Trace"),
					handler: () => frappe.set_route("query-report", "PEPL Heat Number Trace", { heat_number: d.heat_number }),
				});
			}
			actions.push({ label: __("Purchase Receipt"), handler: () => frappe.set_route("Form", "Purchase Receipt", d.purchase_receipt) });
			pepl.panel(frm, { title: __("Heat and test certificate"), rows: d.rows, actions });
		});
	},
});
