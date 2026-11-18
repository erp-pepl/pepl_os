// C3b-P2 - NCR panel: status and age, what and where from, disposition and cost, sign-offs, CAPA, dispatch hold,
// and what still stops closing. C3b-Q3 - the "Sign off" button for a user holding a role still to sign.
const PEPL_NCR = "pepl_os.pepl_quality.ncr";

frappe.ui.form.on("PEPL NCR", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call("pepl_os.pepl_quality.ncr_panel.get_ncr_panel", { name: frm.doc.name }).then((r) => {
			const s = r.message;
			if (!s) return;
			const actions = s.can_sign
				? [
						{
							label: __("Sign off"),
							handler: () =>
								frappe.prompt(
									{ fieldtype: "Data", fieldname: "remarks", label: __("Remarks (optional)") },
									(v) =>
										frappe
											.call(`${PEPL_NCR}.sign_off`, { ncr: frm.doc.name, remarks: v.remarks })
											.then(() => frm.reload_doc()),
									__("Sign off this NCR"),
									__("Sign off")
								),
						},
					]
				: [];
			pepl.panel(frm, { title: __("NCR"), rows: s.rows, actions });
		});
	},
});
