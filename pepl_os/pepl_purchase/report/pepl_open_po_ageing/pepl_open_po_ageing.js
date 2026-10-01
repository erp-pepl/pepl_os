// C2-13 - Open PO Ageing: computed live from the Purchase Tracker lines.
frappe.query_reports["PEPL Open PO Ageing"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "as_of", label: __("As of"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
