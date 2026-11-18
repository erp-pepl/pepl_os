// C3b-B2 - Cost of Quality: what poor quality cost, by month or by item. "Not priced" lists rejected pieces without a
// cost a piece and NCRs without a cost - fill those in for a true figure.
frappe.query_reports["PEPL Cost of Quality"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.month_end(), reqd: 1 },
		{ fieldname: "group_by", label: __("By"), fieldtype: "Select", options: ["Month", "Item"], default: "Month" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "notes" && data.notes) value = `<span style="color:var(--orange-600)">${value}</span>`;
		if (data && column.fieldname === "total") value = `<b>${value}</b>`;
		return value;
	},
};
