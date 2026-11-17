// C3b-Q2 - QC Inspection: the reason dialog when a reading's instrument is out of calibration and the Calibration
// Gate is Soft Block. (Hard Block refuses on the server; Advisory only warns.)
const PEPL_CALIBRATION = "pepl_os.pepl_quality.calibration";

frappe.ui.form.on("Quality Inspection", {
	async before_submit(frm) {
		const r = await frappe.call(`${PEPL_CALIBRATION}.calibration_gate_check`, { name: frm.doc.name });
		if (r.message) {
			try {
				await pepl.override(frm, r.message.rule_code, r.message.message);
			} catch (e) {
				frappe.validated = false;
				throw e;
			}
		}
	},
});
