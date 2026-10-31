// C3a-B4 - Bottleneck: wait in front of each machine group between Job Order operations (clock hours).
frappe.query_reports["PEPL Bottleneck"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("Started From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30), reqd: 1 },
		{ fieldname: "to_date", label: __("Started To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "workstation_type", label: __("Machine Group"), fieldtype: "Link", options: "Workstation Type" },
		{ fieldname: "job_order", label: __("Job Order"), fieldtype: "Link", options: "Work Order" },
		{ fieldname: "show", label: __("Show"), fieldtype: "Select", options: ["Machine Groups", "Operations"], default: "Machine Groups" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.colour && ["workstation_type", "average_hours"].includes(column.fieldname)) {
			const css = { red: "var(--red-600)", orange: "var(--orange-600)", green: "var(--green-600)" }[data.colour];
			value = `<span style="color:${css};font-weight:600">${value}</span>`;
		}
		if (data && data.bottleneck && column.fieldname === "workstation_type") value += ` <b>${__("bottleneck")}</b>`;
		if (data && data.state === "waiting" && column.fieldname === "state_text") value = `<b style="color:var(--orange-600)">${value}</b>`;
		return value;
	},
};
