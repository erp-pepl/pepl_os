frappe.query_reports["PEPL Audit Trail"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "user",
			label: __("User"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "event_type",
			label: __("Event"),
			fieldtype: "Select",
			options: ["", "Field Change", "Login / Logout", "Print / Export", "Deletion", "View", "Override"],
		},
		{
			fieldname: "reference_doctype",
			label: __("Record Type"),
			fieldtype: "Link",
			options: "DocType",
		},
		{
			fieldname: "reference_name",
			label: __("Record"),
			fieldtype: "Data",
		},
	],
};
