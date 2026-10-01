// C2-18 - Scrap Recovery: per month and metal, generated vs sold, realised rate vs the rate master, closing stock.
frappe.query_reports["PEPL Scrap Recovery"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.month_start(), -5) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "metal", label: __("Metal"), fieldtype: "Link", options: "Item Group" },
	],
};
