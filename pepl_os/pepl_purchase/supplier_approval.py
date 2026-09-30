"""C2-08 - PEPL Supplier Approval: the document checklist per supplier and the purchase gate.

* The checklist comes from PEPL Supplier Document Requirement (PEPL's 11
  documents, entered as master data; no code change when they arrive).
* Row status is computed from the file and dates (common.expiry.health).
* Approved / Conditionally Approved need every mandatory document in date,
  and only a Purchase Manager (or System Manager) may set them.
* The approval's state, earliest expiry and RM groups are copied onto the
  Supplier, where the list colour and later steps (RFQ, comparison) read them.
* Submitting a Request for Quotation or Purchase Order to a supplier who is
  not approved needs a typed reason (PEPL Override Log, rule SUP-NOT-APPROVED).
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from pepl_os.common import alerts, expiry, params
from pepl_os.common.jobs import tracked_job
from pepl_os.common.overrides import has_recent_override

DOCTYPE = "PEPL Supplier Approval"
REQUIREMENT = "PEPL Supplier Document Requirement"
APPROVED_STATES = ("Approved", "Conditionally Approved")
MANAGER_STATES = ("Approved", "Conditionally Approved", "Suspended", "Rejected")
MANAGER_ROLES = ("Purchase Manager", "System Manager")
REMARK_STATES = ("Conditionally Approved", "Suspended", "Rejected")
GATE_RULE = "SUP-NOT-APPROVED"
EXPIRY_RULE = "SUP-DOC-EXPIRY"
OWNER_FIELD = "custom_purchase_notification_owner"

PENDING, AVAILABLE, EXPIRING, EXPIRED, NOT_APPLICABLE = (
	"Pending",
	"Available",
	"Expiring",
	"Expired",
	"Not Applicable",
)


def alert_days():
	return params.get_int("custom_supplier_doc_expiry_alert_days", 30)


# Checklist -----------------------------------------------------------------


def active_requirements():
	return frappe.get_all(
		REQUIREMENT,
		filters={"active": 1},
		fields=["name", "mandatory", "expires"],
		order_by="sequence asc, name asc",
	)


def sync_checklist(doc):
	"""Add every active requirement not yet on the approval. Never removes a row. Returns rows added."""
	have = {row.requirement for row in doc.get("documents") or []}
	added = 0
	for req in active_requirements():
		if req.name in have:
			continue
		doc.append(
			"documents",
			{"requirement": req.name, "mandatory": req.mandatory, "expires": req.expires, "status": PENDING},
		)
		added += 1
	return added


def row_status(row, as_of=None):
	if cint(row.get("not_applicable")):
		return NOT_APPLICABLE
	if not row.get("file"):
		return PENDING
	if cint(row.get("expires")):
		if not row.get("expiry_date"):
			return PENDING  # an expiring document is not complete without its expiry date
		health = expiry.health(row.expiry_date, alert_days(), as_of)["status"]
		return {expiry.EXPIRED: EXPIRED, expiry.EXPIRING_SOON: EXPIRING}.get(health, AVAILABLE)
	return AVAILABLE


def refresh_rows(doc, as_of=None):
	for row in doc.get("documents") or []:
		req = (
			frappe.get_cached_value(REQUIREMENT, row.requirement, ["mandatory", "expires"])
			if row.requirement
			else None
		)
		if req:
			row.mandatory, row.expires = req
		row.status = row_status(row, as_of)


def mandatory_gaps(doc):
	"""Mandatory rows that are not usable: [(requirement, status)]."""
	return [
		(row.requirement, row.status)
		for row in doc.get("documents") or []
		if cint(row.mandatory) and row.status not in (AVAILABLE, EXPIRING, NOT_APPLICABLE)
	]


def earliest_expiry(doc):
	dates = [
		getdate(row.expiry_date)
		for row in doc.get("documents") or []
		if cint(row.mandatory) and cint(row.expires) and row.expiry_date and row.status != NOT_APPLICABLE
	]
	return min(dates) if dates else None


def summary(doc):
	counts = {}
	for row in doc.get("documents") or []:
		counts[row.status] = counts.get(row.status, 0) + 1
	return ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "No documents"


# Validation ----------------------------------------------------------------


def validate_approval(doc):
	if doc.is_new():
		sync_checklist(doc)
	refresh_rows(doc)

	for row in doc.get("documents") or []:
		if cint(row.not_applicable) and not (row.remarks or "").strip():
			frappe.throw(
				_("Row {0}: say why {1} does not apply to this supplier (Remarks).").format(
					row.idx, row.requirement
				)
			)

	state_changed = doc.is_new() or doc.has_value_changed("state")
	if state_changed and doc.state in MANAGER_STATES and not set(MANAGER_ROLES) & set(frappe.get_roles()):
		frappe.throw(
			_("Only a Purchase Manager can set a supplier to {0}.").format(frappe.bold(doc.state)),
			frappe.PermissionError,
		)

	if doc.state in REMARK_STATES and not (doc.remarks or "").strip():
		frappe.throw(_("Remarks are required when the state is {0}.").format(frappe.bold(doc.state)))

	if doc.state in APPROVED_STATES:
		gaps = mandatory_gaps(doc)
		if gaps and doc.state == "Approved":
			frappe.throw(
				_("Cannot approve: these mandatory documents are not in order:<br>{0}").format(
					"<br>".join(f"{req} ({status})" for req, status in gaps)
				),
				title=_("Supplier approval"),
			)
		if doc.state == "Conditionally Approved" and not doc.next_review_date:
			frappe.throw(_("Set the Next Review Date for a conditional approval."))
		if state_changed:
			doc.approved_by = frappe.session.user
			doc.approval_date = today()

	doc.earliest_expiry = earliest_expiry(doc)
	doc.document_summary = summary(doc)


def mirror_to_supplier(doc):
	"""Copy state, earliest expiry and RM groups onto the Supplier."""
	supplier = frappe.get_doc("Supplier", doc.supplier)
	supplier.custom_approval_state = doc.state
	supplier.custom_approval_expiry = doc.earliest_expiry
	supplier.set("custom_rm_groups", [{"rm_group": row.rm_group} for row in doc.get("rm_groups") or []])
	supplier.flags.ignore_permissions = True
	supplier.save()


# Daily job -------------------------------------------------------------------


def refresh_supplier_approvals(as_of=None):
	"""Recompute every approval; expire suppliers whose mandatory documents lapsed; raise / close ToDos."""
	flagged = []
	expired_now = 0
	for name in frappe.get_all(DOCTYPE, filters={"state": ["!=", "Rejected"]}, pluck="name"):
		doc = frappe.get_doc(DOCTYPE, name)
		refresh_rows(doc, as_of)
		lapsed = [row for row in doc.documents if cint(row.mandatory) and row.status == EXPIRED]
		due = [row for row in doc.documents if cint(row.mandatory) and row.status in (EXPIRED, EXPIRING)]
		if lapsed and doc.state in APPROVED_STATES:
			doc.state = "Expired"
			doc.remarks = (
				(doc.remarks or "")
				+ f"\nExpired automatically on {today()}: "
				+ ", ".join(r.requirement for r in lapsed)
			).strip()
			expired_now += 1
		doc.flags.ignore_permissions = True
		doc.flags.from_daily_job = True
		doc.save()
		if due:
			flagged.append(name)
			lines = "; ".join(
				f"{r.requirement} {'expired' if r.status == EXPIRED else 'expires'} on {r.expiry_date}"
				for r in due
			)
			alerts.raise_todo(
				EXPIRY_RULE,
				DOCTYPE,
				name,
				f"{doc.supplier_name or doc.supplier}: {lines}. Collect the renewed document and update the approval.",
				owner_field=OWNER_FIELD,
				priority="High" if lapsed else "Medium",
			)
	closed = alerts.close_resolved(EXPIRY_RULE, DOCTYPE, flagged)
	return {
		"records_touched": len(flagged) + closed,
		"message": f"{len(flagged)} with documents due, {expired_now} expired today, {closed} ToDos closed",
	}


@tracked_job("Supplier approval documents: expiry and state")
def daily_supplier_approvals():
	return refresh_supplier_approvals()


# Gate ------------------------------------------------------------------------


def supplier_state(supplier):
	return frappe.db.get_value("Supplier", supplier, "custom_approval_state") or "Not Approved"


def unapproved_suppliers(doc):
	"""[(supplier, state)] for suppliers not approved, or (C2-09) approved but not for the RFQ's RM group."""
	rm_group = None
	if doc.doctype == "Request for Quotation":
		suppliers = [row.supplier for row in doc.get("suppliers") or [] if row.supplier]
		rm_group = doc.get("custom_rm_group")
	else:
		suppliers = [doc.supplier] if doc.get("supplier") else []
	pairs = []
	for s in dict.fromkeys(suppliers):
		state = supplier_state(s)
		if state not in APPROVED_STATES:
			pairs.append((s, state))
		elif rm_group and not _covers(s, rm_group):
			pairs.append((s, _("{0}, not for {1}").format(_(state), rm_group)))
	return pairs


def _covers(supplier, rm_group):
	return bool(
		frappe.db.exists(
			"PEPL Supplier RM Group",
			{
				"parenttype": "Supplier",
				"parentfield": "custom_rm_groups",
				"parent": supplier,
				"rm_group": rm_group,
			},
		)
	)


def gate_message(pairs):
	return _("Not an approved supplier: {0}.").format(", ".join(f"{s} ({state})" for s, state in pairs))


def before_submit_gate(doc, method=None):
	"""doc_events: Request for Quotation / Purchase Order before_submit."""
	pairs = unapproved_suppliers(doc)
	if not pairs:
		return
	message = gate_message(pairs)
	if not params.is_enabled("custom_enforce_override_reason", 1):
		frappe.msgprint(message, indicator="orange", alert=True)
		return
	if has_recent_override(GATE_RULE, doc.doctype, doc.name):
		return
	frappe.throw(
		f"[{GATE_RULE}] " + message + " " + _("A reason is required to continue."), title=_("Reason required")
	)


@frappe.whitelist()
def gate_check(doctype, name):
	"""For the form: the message to show before submit, or None when nothing is needed."""
	if doctype not in ("Request for Quotation", "Purchase Order"):
		frappe.throw(_("Not supported"))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	pairs = unapproved_suppliers(doc)
	if not pairs or not params.is_enabled("custom_enforce_override_reason", 1):
		return None
	if has_recent_override(GATE_RULE, doctype, name):
		return None
	return {"rule_code": GATE_RULE, "message": gate_message(pairs)}


@frappe.whitelist()
def sync_now(name):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	added = sync_checklist(doc)
	doc.save()
	return added
