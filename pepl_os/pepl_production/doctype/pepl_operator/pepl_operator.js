// C3a-X2 - Operator panel: kiosk PIN and machine groups with level and validity.
// C4-H1 - "Make Employee" for an operator without one: a new Employee with this code as its Employee Number; once
// saved, the operator is linked to it automatically.
frappe.ui.form.on("PEPL Operator", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe
			.call({ method: "pepl_os.pepl_production.masters.get_operator_panel", args: { name: frm.doc.name } })
			.then((r) => pepl.panel(frm, { title: __("Operator"), rows: (r.message || {}).rows || [] }));
		if (!frm.doc.employee) {
			frm.add_custom_button(__("Make Employee"), () => {
				frappe.new_doc("Employee", {
					first_name: frm.doc.operator_name,
					employee_number: frm.doc.employee_code,
					date_of_joining: frm.doc.joining_date,
				});
			});
		}
	},
});
