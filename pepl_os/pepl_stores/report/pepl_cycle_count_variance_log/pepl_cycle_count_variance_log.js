// C2-20 - Cycle Count Variance Log: every counted difference, by store, reason and month.
frappe.query_reports["PEPL Cycle Count Variance Log"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "warehouse", label: __("Store"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "reason", label: __("Reason"), fieldtype: "Select", options: ["", "Wrong issue entry", "Unrecorded receipt", "Damage", "Measurement", "Suspected loss", "Other"] },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -12) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
