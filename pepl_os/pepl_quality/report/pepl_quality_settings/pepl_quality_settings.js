// C3b-C1 - Quality Settings: green = decided / ready, orange = to confirm or complete with PEPL, red = will not work
// as it is (e.g. a sign-off role nobody holds).
frappe.query_reports["PEPL Quality Settings"] = {
	filters: [],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			value = `<span class="indicator-pill ${data.colour || "orange"}">${value}</span>`;
		}
		return value;
	},
};
