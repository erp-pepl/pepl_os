// C3a-B2 - Estimate vs Actual Cost: the CST estimate a piece against the Job Order's actual cost a piece.
frappe.query_reports["PEPL Estimate vs Actual Cost"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("Planned Start From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -3) },
		{ fieldname: "to_date", label: __("Planned Start To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "sales_order", label: __("Sales Order"), fieldtype: "Link", options: "Sales Order" },
		{ fieldname: "job_order", label: __("Job Order"), fieldtype: "Link", options: "Work Order" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Completed", "In Process", "Not Started", "Stopped", "Closed"] },
		{ fieldname: "group_by", label: __("Show"), fieldtype: "Select", options: ["Job Order", "Item"], default: "Job Order" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && ["variance", "variance_percent", "act_total"].includes(column.fieldname) && data.colour && data.colour !== "gray") {
			const colour = data.colour === "red" ? "var(--red-600)" : "var(--green-600)";
			value = `<span style="color:${colour};font-weight:600">${value}</span>`;
		}
		return value;
	},
};
