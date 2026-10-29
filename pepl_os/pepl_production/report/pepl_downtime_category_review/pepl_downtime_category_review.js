// C3a-C1 - Downtime Category Review: open a category to merge it into another of the same kind.
frappe.query_reports["PEPL Downtime Category Review"] = {
	filters: [{ fieldname: "days", label: __("Look-back Days"), fieldtype: "Int", default: 90, reqd: 1 }],
};
