"""Human override with a mandatory reason, logged for audit.

The standing PEPL rule: the system is the baseline, a human can always
override, and every override is written to PEPL Override Log with its reason.

Pattern for a gate (enforced at submit, when the record has a name):

    # server, e.g. in before_submit
    from pepl_os.common.overrides import require_override
    if supplier_not_approved:
        require_override(doc, "SUP-NOT-APPROVED", "Supplier X is not approved.")

    // client, before calling frm.savesubmit()
    await pepl.override(frm, "SUP-NOT-APPROVED", "Supplier X is not approved.");
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

OVERRIDE_LOG = "PEPL Override Log"
MIN_REASON_LENGTH = 10
RECENT_MINUTES = 30


def _clean_reason(reason):
	reason = (reason or "").strip()
	if len(reason) < MIN_REASON_LENGTH:
		frappe.throw(
			_("Please give a reason of at least {0} characters.").format(MIN_REASON_LENGTH),
			title=_("Reason required"),
		)
	return reason


def log_override(rule_code, reference_doctype, reference_name, message, reason, module=None):
	"""Write one Override Log row. Server-side use; no permission check."""
	if not rule_code:
		frappe.throw(_("Rule code is required for an override."))

	doc = frappe.get_doc(
		{
			"doctype": OVERRIDE_LOG,
			"rule_code": rule_code,
			"module_name": module or frappe.db.get_value("DocType", reference_doctype, "module"),
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"message": message,
			"reason": _clean_reason(reason),
			"user": frappe.session.user,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def record_override(rule_code, reference_doctype, reference_name, message, reason):
	"""Client entry point: only someone who can write the record may override on it."""
	if not frappe.has_permission(reference_doctype, "write", doc=reference_name):
		frappe.throw(
			_("You are not permitted to override rules on {0} {1}.").format(
				_(reference_doctype), reference_name
			),
			frappe.PermissionError,
		)
	return log_override(rule_code, reference_doctype, reference_name, message, reason)


def has_recent_override(rule_code, reference_doctype, reference_name, user=None, minutes=RECENT_MINUTES):
	"""True when this user logged a reason for this rule on this record recently."""
	return bool(
		frappe.db.exists(
			OVERRIDE_LOG,
			{
				"rule_code": rule_code,
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"user": user or frappe.session.user,
				"creation": [">=", add_to_date(now_datetime(), minutes=-minutes)],
			},
		)
	)


def require_override(doc, rule_code, message):
	"""Stop the action unless a reason was logged for this rule on this record.

	The error message starts with the rule code in brackets so client code
	can recognise it, ask for a reason and retry.
	"""
	if has_recent_override(rule_code, doc.doctype, doc.name):
		return
	frappe.throw(
		f"[{rule_code}] " + message + " " + _("A reason is required to continue."),
		title=_("Reason required"),
	)
