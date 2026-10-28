// C3a-X6 - A Production Plan that books a machine for more jobs at the same time than it can run.
// Soft Block: before submit, ask for a reason (Override Log, rule PRD-DOUBLE-BOOK); the server refuses the
// submit without it. Hard Block is refused by the server with the clash in the message.
// C3a-P2 - Machine load: each machine's booked hours (this plan + already booked) against its available hours.
frappe.ui.form.on("Production Plan", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe
			.call("pepl_os.pepl_production.load_view.get_production_plan_load", { production_plan: frm.doc.name })
			.then((r) => pepl.panel(frm, { title: __("Machine load"), rows: (r.message || {}).rows || [] }));
	},
	async before_submit(frm) {
		const r = await frappe.call("pepl_os.pepl_production.machine_booking.booking_gate_check", {
			name: frm.doc.name,
		});
		if (r.message) {
			try {
				await pepl.override(frm, r.message.rule_code, r.message.message);
			} catch (e) {
				frappe.validated = false;
				throw e;
			}
		}
	},
});
