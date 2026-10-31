// C3a-B5 - LD Exposure: late days x contractual LD rate per open Sales Order, today and in the look-ahead days.
frappe.query_reports["PEPL LD Exposure"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "as_on", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "sector", label: __("Sector"), fieldtype: "Select", options: ["", "Railways", "Defence", "Private", "Others"] },
		{ fieldname: "sales_order", label: __("Sales Order"), fieldtype: "Link", options: "Sales Order" },
		{ fieldname: "only_ld", label: __("Only orders with LD terms"), fieldtype: "Check", default: 1 },
		{ fieldname: "show", label: __("Show"), fieldtype: "Select", options: ["Orders", "Lines"], default: "Orders" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.colour && ["sales_order", "ld_now", "ld_ahead"].includes(column.fieldname)) {
			const css = { red: "var(--red-600)", orange: "var(--orange-600)", green: "var(--green-600)", gray: "var(--gray-600)" }[data.colour];
			value = `<span style="color:${css};font-weight:600">${value}</span>`;
		}
		return value;
	},
};
