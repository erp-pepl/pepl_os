// C3a-X8 - Job-Work Reconciliation: what is sent, received back processed, returned, and still outside.
frappe.query_reports["PEPL Job-Work Reconciliation"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "supplier", label: __("Job Worker"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "as_on", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "outstanding_only", label: __("Only What Is Outside"), fieldtype: "Check", default: 1 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colour = { Clear: "green", Outside: "blue", Overdue: "orange" }[data.status] || "red";
			value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
