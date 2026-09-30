frappe.listview_settings["PEPL Supplier Approval"] = {
	add_fields: ["state"],
	get_indicator(doc) {
		const colour = { Approved: "green", "Conditionally Approved": "green", "Under Review": "orange", Draft: "gray", Suspended: "red", Expired: "red", Rejected: "red" }[doc.state] || "gray";
		return [__(doc.state), colour, `state,=,${doc.state}`];
	},
};
