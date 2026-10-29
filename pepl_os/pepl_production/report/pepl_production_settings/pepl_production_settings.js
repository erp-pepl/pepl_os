// C3a-C1 - Production Settings: the values PEPL confirms; "Changed from default" shows what was already set.
frappe.query_reports["PEPL Production Settings"] = {
	filters: [],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colour = data.status.startsWith("Changed") || data.status.startsWith("As") ? "green" : "orange";
			value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
