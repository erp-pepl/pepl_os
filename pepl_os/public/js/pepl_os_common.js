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

// C2-22 - One consistent helper panel at the top of a form.
// pepl.panel(frm, { title, rows, actions })
//   rows:    [{ text: "3 lines overdue", colour: "green" | "orange" | "red" | "gray" }]
//            (old names still accepted: yellow -> orange, blue -> gray)
//   actions: [{ label, handler }] - the first is the one primary button; any others are plain buttons.
//            `action: { label, handler }` (a single action) is still accepted.
// Several panels may sit on one form (e.g. Supplier: approval + payment priority); each has its own
// title, they are shown together and in the order they were added, and a form refresh clears them.
pepl.PANEL_COLOURS = { green: "green", orange: "orange", red: "red", gray: "gray", grey: "gray", yellow: "orange", blue: "gray" };
pepl.panel = function (frm, { title, rows = [], actions, action } = {}) {
	const esc = frappe.utils.escape_html;
	// The form clears its message area on every refresh; an empty area means start a fresh set of panels.
	const area = frm.layout && frm.layout.message;
	if (!frm.__pepl_panels || !area || !area.find(".pepl-panel").length) frm.__pepl_panels = {};
	const key = title || "";
	frm.__pepl_panels[key] = (rows || []).map((r) => ({ text: r.text, colour: pepl.PANEL_COLOURS[r.colour] || "gray" }));
	const html = Object.entries(frm.__pepl_panels)
		.map(([t, lines]) => {
			const body = lines
				.map((r) => `<div class="pepl-panel-row"><span class="indicator ${r.colour}">${esc(r.text)}</span></div>`)
				.join("");
			return `<div class="pepl-panel" style="margin-bottom: 6px;"><div class="pepl-panel-title"><b>${esc(t)}</b></div>${body}</div>`;
		})
		.join("");
	frm.dashboard.set_headline_alert(html);
	const list = actions || (action ? [action] : []);
	list.filter((a) => a && a.label && a.handler).forEach((a, idx) => {
		const btn = frm.add_custom_button(a.label, a.handler);
		if (idx === 0 && btn) btn.addClass("btn-primary");
	});
};

// C2-24: the Print button on the print page prints the PDF on the PEPL letterhead -------------------
// For the PEPL letterhead formats (frappe.boot.pepl_letterhead_formats) the black Print button no longer
// prints the plain web page: it fetches the letterhead PDF (the same one the PDF button gives) and opens
// the browser's print dialog on it. Every other print format prints exactly as before.
pepl.print_letterhead_pdf = function (doctype, name, format, lang) {
	const query = new URLSearchParams({ doctype, name, format, no_letterhead: 1 });
	if (lang) query.set("_lang", lang);
	const url = frappe.urllib.get_full_url("/api/method/frappe.utils.print_format.download_pdf?" + query.toString());
	frappe.show_alert({ message: __("Preparing {0} on the PEPL letterhead...", [name]), indicator: "blue" }, 4);
	fetch(url, { credentials: "same-origin" })
		.then((r) => {
			if (!r.ok) throw new Error(r.statusText);
			return r.blob();
		})
		.then((blob) => {
			const blob_url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
			const frame = document.createElement("iframe");
			frame.setAttribute("style", "visibility: hidden; height: 0; width: 0; position: absolute; border: 0;");
			frame.onload = () => {
				try {
					frame.contentWindow.focus();
					frame.contentWindow.print();
				} catch (e) {
					window.open(blob_url); // the browser opens the PDF; print it from there
				}
			};
			frame.src = blob_url;
			document.body.appendChild(frame);
			setTimeout(() => {
				frame.remove();
				URL.revokeObjectURL(blob_url);
			}, 10 * 60 * 1000);
		})
		.catch(() => {
			if (!window.open(url)) frappe.msgprint(__("Please enable pop-ups"));
		});
};

pepl.patch_print_view = function () {
	const PrintView = frappe.ui.form && frappe.ui.form.PrintView;
	if (!PrintView) return false; // the print page has not loaded yet
	if (PrintView.prototype.__pepl_letterhead) return true;
	const original = PrintView.prototype.printit;
	PrintView.prototype.printit = function () {
		const format = this.selected_format && this.selected_format();
		if ((frappe.boot.pepl_letterhead_formats || []).includes(format) && this.frm && this.frm.doc) {
			return pepl.print_letterhead_pdf(this.frm.doc.doctype, this.frm.doc.name, format, this.lang_code);
		}
		return original.apply(this, arguments);
	};
	PrintView.prototype.__pepl_letterhead = true;
	return true;
};

$(document).on("page-change", () => {
	if (frappe.get_route()[0] !== "print") return;
	let tries = 0;
	const attempt = () => !pepl.patch_print_view() && ++tries < 25 && setTimeout(attempt, 200);
	attempt();
});
pepl.patch_print_view();
