// C3a-CC - Downtime by Cause: the last days before today (today's shifts are still running).
frappe.query_reports["PEPL Downtime by Cause"] = {
	filters: [{ fieldname: "days", label: __("Last Days"), fieldtype: "Int", default: 7, reqd: 1 }],
};
