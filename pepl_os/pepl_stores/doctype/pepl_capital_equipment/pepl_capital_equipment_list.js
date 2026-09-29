frappe.listview_settings["PEPL Capital Equipment"] = {
	add_fields: ["document_status", "status"],
	get_indicator(doc) {
		if (doc.status === "Disposed") return [__("Disposed"), "gray", "status,=,Disposed"];
		if (doc.document_status === "Missing") return [__("Documents missing"), "red", "document_status,=,Missing"];
		return [__(doc.status), "green", `status,=,${doc.status}`];
	},
};
