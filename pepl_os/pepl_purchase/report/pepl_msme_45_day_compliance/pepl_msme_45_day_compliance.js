// C2-17 - MSME 45-Day Compliance: Paid on time / Paid late / Open / Breach for every MSME bill.
frappe.query_reports["PEPL MSME 45-Day Compliance"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "from_date", label: __("Bills From"), fieldtype: "Date" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Paid on time", "Paid late", "Open", "Breach", "Settled without payment"] },
		{ fieldname: "as_of", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colour = { "Paid on time": "green", "Paid late": "orange", Open: "blue", Breach: "red" }[data.status] || "gray";
			value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
