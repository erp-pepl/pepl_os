// C2-17 - Outstanding Vendor Bills: compare the total with ERPNext's Accounts Payable (same company, same date).
frappe.query_reports["PEPL Outstanding Vendor Bills"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "as_of", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
