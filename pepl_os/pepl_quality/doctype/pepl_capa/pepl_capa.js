// C3b-Q4 - CAPA: five-why progress and what still stops closing.
frappe.ui.form.on("PEPL CAPA", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call("pepl_os.pepl_quality.capa.get_capa_state", { capa: frm.doc.name }).then((r) => {
			const s = r.message;
			if (!s) return;
			const rows = [
				{
					text: __("Five-why: {0} of {1} whys, root cause {2}", [
						s.whys_filled,
						s.whys_required,
						s.root_cause ? __("given") : __("missing"),
					]),
					colour: s.five_why_complete ? "green" : "orange",
				},
			];
			if (["Closed", "Cancelled"].includes(frm.doc.status)) {
				rows.push({ text: __(frm.doc.status), colour: "gray" });
			} else if (s.closing_gaps.length) {
				rows.push({ text: __("Before closing: {0}", [s.closing_gaps.join("; ")]), colour: "orange" });
			} else {
				rows.push({ text: __("Ready to close"), colour: "green" });
			}
			pepl.panel(frm, { title: __("CAPA"), rows });
		});
	},
});
