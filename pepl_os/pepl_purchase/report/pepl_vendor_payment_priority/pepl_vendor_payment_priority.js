// C2-17 - Vendor Payment Priority: the weekly worklist. "Mark paid" records the Tally payment as a Payment Entry.
frappe.provide("pepl");
pepl.mark_vendor_paid = function (invoice, outstanding) {
	const d = new frappe.ui.Dialog({
		title: __("Mark {0} paid", [invoice]),
		fields: [
			{ fieldtype: "Date", fieldname: "paid_on", label: __("Paid On"), reqd: 1, default: frappe.datetime.get_today() },
			{ fieldtype: "Currency", fieldname: "amount", label: __("Amount Settled"), reqd: 1, default: outstanding,
				description: __("Including any TDS deducted. Less than the outstanding = part payment.") },
			{ fieldtype: "Data", fieldname: "tally_voucher_no", label: __("Tally Voucher No"), reqd: 1 },
			{ fieldtype: "Data", fieldname: "utr", label: __("UTR / Cheque No") },
			{ fieldtype: "Currency", fieldname: "tds_amount", label: __("TDS Deducted"), default: 0 },
		],
		primary_action_label: __("Record payment"),
		primary_action(values) {
			frappe
				.call({ method: "pepl_os.pepl_purchase.payments.mark_paid", args: { purchase_invoice: invoice, ...values }, freeze: true })
				.then((r) => {
					d.hide();
					frappe.show_alert({ message: __("Payment Entry {0} submitted", [r.message]), indicator: "green" });
					frappe.query_report.refresh();
				});
		},
	});
	d.show();
};

frappe.query_reports["PEPL Vendor Payment Priority"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "as_of", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "action") {
			if (!data || !data.action) return "";
			if (!(frappe.user.has_role("Accounts User") || frappe.user.has_role("Accounts Manager") || frappe.user.has_role("System Manager"))) return "";
			const inv = encodeURIComponent(data.action).replace(/'/g, "%27");
			return `<button class="btn btn-xs btn-primary" onclick="pepl.mark_vendor_paid(decodeURIComponent('${inv}'), ${Number(data.outstanding_amount) || 0})">${__("Mark paid")}</button>`;
		}
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "flag" && data) {
			const colour = { Breach: "red", Overdue: "red", "Due Soon": "orange", "Due Today": "orange", "On Track": "green" }[data.flag] || "gray";
			value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
