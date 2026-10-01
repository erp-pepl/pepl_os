// C2-15 - Heat Number Trace: the recall view, from receipt to issue, Work Order and dispatch.
frappe.query_reports["PEPL Heat Number Trace"] = {
	filters: [{ fieldname: "heat_number", label: __("Heat Number"), fieldtype: "Data", reqd: 1 }],
};
