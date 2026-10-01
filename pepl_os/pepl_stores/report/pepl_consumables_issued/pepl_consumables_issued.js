// C2-21 - Consumables Issued: per day / week / month, grouped by item, item group or machine group; and % of sales.
frappe.query_reports["PEPL Consumables Issued"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "period", label: __("Period"), fieldtype: "Select", options: ["Day", "Week", "Month"], default: "Day", reqd: 1 },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -29), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select", options: ["Item", "Item Group", "Machine Group"], default: "Item" },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Select", options: ["Value", "% of Sales"], default: "Value" },
	],
};
