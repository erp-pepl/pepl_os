// C2-16 - CSM Balance by Order: received, issued, scrapped, returned and balance of the customer's material.
frappe.query_reports["PEPL CSM Balance by Order"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "sales_order", label: __("Sales Order"), fieldtype: "Link", options: "Sales Order" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "item_code", label: __("CSM Item"), fieldtype: "Link", options: "Item", get_query: () => ({ filters: { is_customer_provided_item: 1 } }) },
		{ fieldname: "to_date", label: __("As On"), fieldtype: "Date" },
	],
};
