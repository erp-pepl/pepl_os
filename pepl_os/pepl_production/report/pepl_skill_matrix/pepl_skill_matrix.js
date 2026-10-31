// C3a-B3 - Skill Matrix: operators against machine groups; the last row counts qualified operators per group.
frappe.query_reports["PEPL Skill Matrix"] = {
	filters: [
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Active", "Inactive"], default: "Active" },
		{ fieldname: "workstation_type", label: __("Machine Group"), fieldtype: "Link", options: "Workstation Type" },
		{ fieldname: "as_of", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		const colour = data[column.fieldname + "_colour"];
		if (colour) {
			const css = { red: "var(--red-600)", orange: "var(--orange-600)", green: "var(--green-600)" }[colour];
			value = `<span style="color:${css};font-weight:600">${value}</span>`;
		}
		if (data.is_cover) value = `<b>${value}</b>`;
		return value;
	},
};
