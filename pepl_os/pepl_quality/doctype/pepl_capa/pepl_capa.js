// C3b-P3 - CAPA panel: status, age and owner, target (days left / overdue), NCRs, containment, five-why, each open
// action (who, due, overdue) and what still stops closing. (Replaces the C3b-Q4 five-why / closing panel.)
// C3b-B3 - "Verify Effectiveness" on a CAPA awaiting its effectiveness check (Quality Manager).
frappe.ui.form.on("PEPL CAPA", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call("pepl_os.pepl_quality.capa_panel.get_capa_panel", { name: frm.doc.name }).then((r) => {
			if (r.message) pepl.panel(frm, { title: __("CAPA"), rows: r.message });
		});
		const verifier = frappe.user.has_role("Quality Manager") || frappe.user.has_role("System Manager");
		if (frm.doc.status === "Awaiting Verification" && verifier) {
			frm.add_custom_button(__("Verify Effectiveness"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Effectiveness of {0}", [frm.doc.name]),
					fields: [
						{
							fieldname: "result",
							fieldtype: "Select",
							label: __("Result"),
							options: "Effective\nNot Effective",
							reqd: 1,
							description: __("Effective (on or after {0}) closes the CAPA; Not Effective sends it back to In Progress.", [
								frappe.datetime.str_to_user(frm.doc.verification_due_on),
							]),
						},
						{
							fieldname: "remarks",
							fieldtype: "Small Text",
							label: __("What was checked"),
							reqd: 1,
							description: __("e.g. lots inspected since and their result, rejections on the machine."),
						},
					],
					primary_action_label: __("Record"),
					primary_action(values) {
						frappe
							.call("pepl_os.pepl_quality.capa.verify_capa", {
								capa: frm.doc.name,
								result: values.result,
								remarks: values.remarks,
							})
							.then(() => {
								d.hide();
								frm.reload_doc();
							});
					},
				});
				d.show();
			}).addClass("btn-primary");
		}
	},
});
