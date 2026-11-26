// C4-H1 - People Register
frappe.query_reports["PEPL People Register"] = {
	filters: [{ fieldname: "only_gaps", label: __("Only Rows to Put Right"), fieldtype: "Check" }],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "gaps" && data && data.gaps) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
