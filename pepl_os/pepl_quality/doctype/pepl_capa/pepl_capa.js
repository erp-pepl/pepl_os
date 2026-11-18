// C3b-P3 - CAPA panel: status, age and owner, target (days left / overdue), NCRs, containment, five-why, each open
// action (who, due, overdue) and what still stops closing. (Replaces the C3b-Q4 five-why / closing panel.)
frappe.ui.form.on("PEPL CAPA", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call("pepl_os.pepl_quality.capa_panel.get_capa_panel", { name: frm.doc.name }).then((r) => {
			if (r.message) pepl.panel(frm, { title: __("CAPA"), rows: r.message });
		});
	},
});
