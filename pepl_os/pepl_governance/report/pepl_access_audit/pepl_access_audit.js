frappe.query_reports["PEPL Access Audit"] = {
	filters: [],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "flags" && data && data.flags) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
