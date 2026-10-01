// C2-13 - Chase list: one "Chase" button per supplier e-mails the vendor chase letter.
frappe.provide("pepl");
pepl.chase_vendor = function (supplier, done) {
	frappe.confirm(__("E-mail {0} the chase letter with all its pending lines?", [supplier.bold()]), () =>
		frappe
			.call({ method: "pepl_os.pepl_purchase.chase.chase_vendor_now", args: { supplier }, freeze: true })
			.then(() => {
				frappe.show_alert({ message: __("Chase letter sent to {0}", [supplier]), indicator: "green" });
				if (done) done();
			})
	);
};

frappe.query_reports["PEPL Chase List"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "buyer", label: __("Buyer"), fieldtype: "Link", options: "User" },
	],
	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "chase") {
			if (!data || !data.chase) return "";
			const s = encodeURIComponent(data.chase).replace(/'/g, "%27");
			return `<button class="btn btn-xs btn-primary" onclick="pepl.chase_vendor(decodeURIComponent('${s}'), () => frappe.query_report.refresh())">${__("Chase")}</button>`;
		}
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "line_status" && data) {
			const colour = { Overdue: "red", "Due Today": "orange", "Due Soon": "yellow" }[data.line_status] || "gray";
			value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
