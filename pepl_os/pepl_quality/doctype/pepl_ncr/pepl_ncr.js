// C3b-Q3 - NCR: who still has to sign, and the "Sign off" button for a user holding one of those roles.
const PEPL_NCR = "pepl_os.pepl_quality.ncr";

frappe.ui.form.on("PEPL NCR", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call(`${PEPL_NCR}.get_sign_off_state`, { ncr: frm.doc.name }).then((r) => {
			const s = r.message;
			if (!s) return;
			const rows = [];
			s.signed.forEach((x) => rows.push({ text: __("Signed: {0} by {1}", [x.role, x.user]), colour: "green" }));
			s.missing.forEach((role) => rows.push({ text: __("Still to sign: {0}", [role]), colour: "orange" }));
			if (!s.missing.length) rows.push({ text: __("All sign-offs done"), colour: "green" });
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
			pepl.panel(frm, { title: __("Sign-off ({0})", [frm.doc.severity]), rows, actions });
		});
	},
});
