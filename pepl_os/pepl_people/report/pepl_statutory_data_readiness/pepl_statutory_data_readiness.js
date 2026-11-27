// C4-H5 - Statutory Data Readiness
frappe.query_reports["PEPL Statutory Data Readiness"] = {
	filters: [
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "Active\nInactive\nSuspended\nLeft", default: "Active" },
		{ fieldname: "only_missing", label: __("Only Rows Still Missing Something"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "missing" && data && data.missing) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
