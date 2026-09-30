// PEPL OS shared client helpers, loaded on every Desk page (hooks.app_include_js).
frappe.provide("pepl");

pepl.MIN_REASON_LENGTH = 10;

// Ask the user for a reason. Resolves with the trimmed reason, rejects if closed.
pepl.ask_reason = function (title, message) {
	return new Promise((resolve, reject) => {
		let done = false;
		const dialog = new frappe.ui.Dialog({
			title: title || __("Reason required"),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "message_html",
					options: `<p>${frappe.utils.escape_html(message || "")}</p>`,
				},
				{
					fieldtype: "Small Text",
					fieldname: "reason",
					label: __("Reason"),
					reqd: 1,
					description: __("At least {0} characters. This is recorded with your name.", [
						pepl.MIN_REASON_LENGTH,
					]),
				},
			],
			primary_action_label: __("Continue"),
			primary_action(values) {
				const reason = (values.reason || "").trim();
				if (reason.length < pepl.MIN_REASON_LENGTH) {
					frappe.msgprint(__("Please write at least {0} characters.", [pepl.MIN_REASON_LENGTH]));
					return;
				}
				done = true;
				dialog.hide();
				resolve(reason);
			},
		});
		dialog.onhide = () => {
			if (!done) reject(new Error("cancelled"));
		};
		dialog.show();
	});
};

// Write one PEPL Override Log row for the record open in the form.
pepl.record_override = function ({ rule_code, reference_doctype, reference_name, message, reason }) {
	return frappe.call({
		method: "pepl_os.common.overrides.record_override",
		args: { rule_code, reference_doctype, reference_name, message, reason },
	});
};

// Ask for a reason and log it against this form's record. Use before the
// action whose server gate calls require_override(doc, rule_code, message).
pepl.override = async function (frm, rule_code, message) {
	const reason = await pepl.ask_reason(__("Reason required"), message);
	await pepl.record_override({
		rule_code,
		reference_doctype: frm.doctype,
		reference_name: frm.doc.name,
		message,
		reason,
	});
	return reason;
};

// One consistent helper panel at the top of a form.
// rows: [{ text: "3 lines overdue", colour: "red" | "orange" | "green" | "gray" | "blue" }]
// action: { label: "Chase vendor", handler: () => {...} }  (at most one primary action)
pepl.panel = function (frm, { title, rows = [], action } = {}) {
	const esc = frappe.utils.escape_html;
	const allowed = ["green", "orange", "yellow", "red", "gray", "blue"];
	const lines = rows
		.map((r) => {
			const colour = allowed.includes(r.colour) ? r.colour : "gray";
			return `<div class="pepl-panel-row"><span class="indicator ${colour}">${esc(r.text)}</span></div>`;
		})
		.join("");
	frm.dashboard.set_headline_alert(
		`<div class="pepl-panel"><div class="pepl-panel-title"><b>${esc(title || "")}</b></div>${lines}</div>`
	);
	if (action && action.label && action.handler) {
		frm.add_custom_button(action.label, action.handler).addClass("btn-primary");
	}
};
