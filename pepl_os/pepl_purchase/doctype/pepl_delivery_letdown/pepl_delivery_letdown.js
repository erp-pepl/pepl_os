// C2-14 - Delivery letdown: the Purchase Manager can excuse it with a reason (logged to the Audit Trail).
frappe.ui.form.on("PEPL Delivery Letdown", {
	refresh(frm) {
		if (frm.is_new()) return;
		const rows = [
			{
				text: frm.doc.excused
					? __("Excused by {0}: does not count against the supplier", [frm.doc.excused_by])
					: __("{0}: counts against {1}'s delivery score", [__(frm.doc.letdown_type), frm.doc.supplier_name || frm.doc.supplier]),
				colour: frm.doc.excused ? "gray" : "red",
			},
		];
		pepl.panel(frm, { title: __("Delivery letdown"), rows });
		if (!frm.doc.excused && (frappe.user.has_role("Purchase Manager") || frappe.user.has_role("System Manager"))) {
			frm.add_custom_button(__("Excuse"), async () => {
				const reason = await pepl.ask_reason(__("Excuse this letdown"), __("Why should this letdown not count against the supplier?"));
				await frappe.call({
					method: "pepl_os.pepl_purchase.letdown.excuse_letdown",
					args: { name: frm.doc.name, reason },
					freeze: true,
				});
				frm.reload_doc();
			});
		}
	},
});
