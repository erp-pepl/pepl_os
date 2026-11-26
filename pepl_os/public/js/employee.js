// C4-H1 - Employee: "Make Operator" (the operator code is the Employee Number) and the operator's link.
frappe.ui.form.on("Employee", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.db.get_value("PEPL Operator", { employee: frm.doc.name }, "name").then((r) => {
			const op = r.message && r.message.name;
			if (op) {
				frm.add_custom_button(__("Operator {0}", [op]), () => frappe.set_route("Form", "PEPL Operator", op), __("PEPL"));
				return;
			}
			frm.add_custom_button(
				__("Make Operator"),
				() => {
					if (!frm.doc.employee_number) {
						frappe.msgprint(__("Set the Employee Number first: it becomes the operator code."));
						return;
					}
					frappe
						.call({ method: "pepl_os.pepl_people.people.make_operator", args: { employee: frm.doc.name } })
						.then((res) => res.message && frappe.set_route("Form", "PEPL Operator", res.message));
				},
				__("PEPL")
			);
		});
	},
});
