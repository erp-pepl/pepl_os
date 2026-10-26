// C3a-X10 - Daily Stand-up: the page as e-mailed; "Build again" and "E-mail now" for the Production Manager.
frappe.ui.form.on("PEPL Daily Standup", {
	refresh(frm) {
		frm.disable_save();
		frm.fields_dict.summary_html.$wrapper.html(frm.doc.summary || "");
		if (frappe.user.has_role("Manufacturing Manager") || frappe.user.has_role("System Manager")) {
			const run = (email) =>
				frappe
					.call("pepl_os.pepl_production.standup.build_standup_now", { day: frm.doc.standup_date, email })
					.then(() => frm.reload_doc());
			frm.add_custom_button(__("Build again"), () => run(0));
			frm.add_custom_button(__("E-mail now"), () => run(1));
		}
	},
});
