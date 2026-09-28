frappe.query_reports["PEPL Role Access Matrix"] = {
	filters: [
		{
			fieldname: "role_profile",
			label: __("Role Profile"),
			fieldtype: "Link",
			options: "Role Profile",
			get_query: () => ({ filters: { name: ["like", "PEPL%"] } }),
		},
		{
			fieldname: "area",
			label: __("Area"),
			fieldtype: "Select",
			options: ["", "Masters", "Sales", "Engineering", "Purchase", "Stores", "Production", "Quality", "Accounts"].join("\n"),
		},
		{
			fieldname: "only_with_access",
			label: __("Hide records with no access"),
			fieldtype: "Check",
			default: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "delete" && data && data.delete) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		if (column.fieldname === "in_plain_words" && data && data.in_plain_words === "No access") {
			value = `<span style="color: var(--gray-500)">${value}</span>`;
		}
		return value;
	},
};
