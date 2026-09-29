// C2-03 - Supplier list indicator from the PEPL approval state.
// Red: Suspended / Expired / Rejected. Orange: approved but a document expires soon. Green: approved.
frappe.listview_settings["Supplier"] = Object.assign(frappe.listview_settings["Supplier"] || {}, {
	add_fields: ["custom_approval_state", "custom_approval_expiry", "disabled"],
	get_indicator(doc) {
		if (doc.disabled) return [__("Disabled"), "gray", "disabled,=,1"];
		const state = doc.custom_approval_state;
		if (["Suspended", "Expired", "Rejected"].includes(state)) {
			return [__(state), "red", `custom_approval_state,=,${state}`];
		}
		if (["Approved", "Conditionally Approved"].includes(state)) {
			const alertDays = cint(frappe.boot.pepl_supplier_doc_alert_days || 30);
			if (doc.custom_approval_expiry) {
				const days = frappe.datetime.get_day_diff(doc.custom_approval_expiry, frappe.datetime.get_today());
				if (days <= alertDays) return [__("Expiring Soon"), "orange", `custom_approval_state,=,${state}`];
			}
			return [__(state), "green", `custom_approval_state,=,${state}`];
		}
		return [__("Not Approved"), "gray", "custom_approval_state,is,not set"];
	},
});
