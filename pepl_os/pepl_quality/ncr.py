"""C3b-Q3 - Non-Conformance Report (PEPL NCR): sign-off by severity, closing rules, and the auto-raise rules.

An NCR records one non-conformance: source (Incoming / In-Process / Customer / Dispatch / Other), severity (Minor /
Major / Critical), the item and quantity affected, what is wrong, the documents it came from, the disposition (Use As
Is / Rework / Scrap / Return to Supplier / Concession / Regrade) and its cost.

Status: Open → Under Review (first sign-off) → Closed, or Cancelled (raised in error, with a reason).
  * Severity sign-off matrix (System Parameters > Quality, one role per line for each severity): every role listed for
    the NCR's severity signs once ("Sign off" button, by a user holding that role). Signatures cannot be removed.
  * Closing needs a disposition and every required signature. A Closed or Cancelled NCR cannot be changed; a Quality
    Manager reopens a Closed one by setting it back to Under Review.

Raised by the system (QA-NCR-*), one per event, with the severity "NCR: Severity When Raised by the System":
  * QA-NCR-QI: a QC Inspection submitted as Rejected (Incoming → source Incoming with the supplier and receipt;
    In Process → In-Process; Outgoing → Dispatch). Cancelling the inspection cancels the NCR while nobody has signed.
  * QA-NCR-RETURN: a customer return (Delivery Note return), one NCR per item, source Customer. Switch: "NCR: Raise
    on Customer Return".
  * QA-NCR-RATE: an item's rejection rate on one day's submitted shift entries above "NCR: Rejection Rate Threshold
    %" with at least "NCR: Minimum Pieces" made (good + rejected), source In-Process. Re-checked on every shift-entry
    submit / cancel of that item and day; when the rate drops back below, an unsigned Open NCR is cancelled.
Each system-raised NCR gives the Quality Notification Owner a ToDo (QA-NCR-OPEN), closed when the NCR is closed or
cancelled. Raising an NCR never stops the document that triggered it.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, now_datetime

from pepl_os.common import alerts, params
from pepl_os.pepl_production.job_order_panel import qty_text

NCR = "PEPL NCR"
QI = "Quality Inspection"
SPR = "PEPL Shift Production Entry"
SPR_ROW = "PEPL SPR Production"
OWNER_FIELD = "custom_quality_notification_owner"

OPEN, UNDER_REVIEW, CLOSED, CANCELLED = "Open", "Under Review", "Closed", "Cancelled"
MINOR, MAJOR, CRITICAL = "Minor", "Major", "Critical"
SEVERITIES = (MINOR, MAJOR, CRITICAL)
INCOMING, IN_PROCESS, CUSTOMER, DISPATCH = "Incoming", "In-Process", "Customer", "Dispatch"
SOURCE_BY_INSPECTION = {"Incoming": INCOMING, "In Process": IN_PROCESS, "Outgoing": DISPATCH}

RULE_QI, RULE_RETURN, RULE_RATE = "QA-NCR-QI", "QA-NCR-RETURN", "QA-NCR-RATE"
OPEN_RULE = "QA-NCR-OPEN"

SIGNOFF_FIELDS = {
	MINOR: "custom_ncr_signoff_minor",
	MAJOR: "custom_ncr_signoff_major",
	CRITICAL: "custom_ncr_signoff_critical",
}
SIGNOFF_DEFAULTS = {
	MINOR: "Quality Manager",
	MAJOR: "Quality Manager\nManufacturing Manager",
	CRITICAL: "Quality Manager\nManufacturing Manager\nPEPL CEO",
}
AUTO_SEVERITY_FIELD = "custom_ncr_auto_severity"
RETURN_FIELD = "custom_ncr_on_customer_return"
RATE_FIELD = "custom_ncr_rejection_rate_percent"
MIN_PIECES_FIELD = "custom_ncr_rejection_min_pieces"
REOPEN_ROLES = ("Quality Manager", "System Manager")
LOCKED_FIELDS = (
	"source",
	"severity",
	"item",
	"qty_affected",
	"defect_description",
	"disposition",
	"disposition_remarks",
	"estimated_cost",
)


# Settings ---------------------------------------------------------------------------------------------------


def roles_in(value):
	names = []
	for part in cstr(value).replace(",", "\n").splitlines():
		part = part.strip()
		if part and part not in names:
			names.append(part)
	return names


def required_roles(severity):
	field = SIGNOFF_FIELDS.get(severity or MAJOR, SIGNOFF_FIELDS[MAJOR])
	return roles_in(params.get(field, SIGNOFF_DEFAULTS[severity or MAJOR]))


def auto_severity():
	value = params.get(AUTO_SEVERITY_FIELD, MAJOR) or MAJOR
	return value if value in SEVERITIES else MAJOR


def validate_params(doc):
	errors = []
	for severity, field in SIGNOFF_FIELDS.items():
		value = doc.get(field)
		if value in (None, ""):
			continue
		roles = roles_in(value)
		unknown = [r for r in roles if not frappe.db.exists("Role", r)]
		if unknown:
			errors.append(_("NCR sign-off ({0}): unknown role {1}.").format(_(severity), ", ".join(unknown)))
	severity = doc.get(AUTO_SEVERITY_FIELD)
	if severity not in (None, "") and severity not in SEVERITIES:
		errors.append(_("NCR: Severity When Raised by the System must be Minor, Major or Critical."))
	rate = doc.get(RATE_FIELD)
	if rate not in (None, "") and not 0 <= flt(rate) <= 100:
		errors.append(_("NCR: Rejection Rate Threshold % must be between 0 and 100 (0 = off)."))
	pieces = doc.get(MIN_PIECES_FIELD)
	if pieces not in (None, "") and cint(pieces) < 1:
		errors.append(_("NCR: Minimum Pieces must be at least 1."))
	return errors


# Sign-off and status ---------------------------------------------------------------------------------------------


def signed_roles(doc):
	return {row.role for row in doc.get("sign_offs") or []}


def missing_signatures(doc):
	done = signed_roles(doc)
	return [role for role in required_roles(doc.severity) if role not in done]


def validate_ncr(doc):
	"""PEPL NCR validate."""
	before = None if doc.is_new() else doc.get_doc_before_save()
	old_status = before.status if before else None
	if before and old_status in (CLOSED, CANCELLED) and doc.status == old_status:
		changed = [f for f in LOCKED_FIELDS if cstr(before.get(f)) != cstr(doc.get(f))]
		if changed or len(doc.get("sign_offs") or []) != len(before.get("sign_offs") or []):
			frappe.throw(
				_(
					"A {0} NCR cannot be changed. A Quality Manager can reopen a closed NCR (status Under Review)."
				).format(_(old_status))
			)
	if before and old_status == CLOSED and doc.status != CLOSED:
		if doc.status != UNDER_REVIEW or not set(REOPEN_ROLES) & set(frappe.get_roles()):
			frappe.throw(_("Only a Quality Manager can reopen a closed NCR, by setting it to Under Review."))
		doc.closed_on = None
		doc.closed_by = None
	if before and old_status == CANCELLED and doc.status != CANCELLED:
		frappe.throw(_("A cancelled NCR stays cancelled. Raise a new one."))
	_check_signatures(doc, before)
	doc.required_sign_offs = ", ".join(required_roles(doc.severity))
	if doc.status == CLOSED and old_status != CLOSED:
		if not doc.disposition:
			frappe.throw(_("Choose the disposition (what is done with the material) before closing the NCR."))
		missing = missing_signatures(doc)
		if missing:
			frappe.throw(
				_("This {0} NCR still needs the sign-off of: {1}.").format(
					_(doc.severity), ", ".join(missing)
				)
			)
		doc.closed_on = now_datetime()
		doc.closed_by = frappe.session.user
	if doc.status == CANCELLED and old_status != CANCELLED and len((doc.cancel_reason or "").strip()) < 10:
		frappe.throw(_("Give the reason for cancelling the NCR (at least 10 characters)."))


def _check_signatures(doc, before):
	old = {r.name for r in (before.get("sign_offs") or [])} if before else set()
	seen = set()
	for row in doc.get("sign_offs") or []:
		if row.role in seen:
			frappe.throw(_("{0} has already signed this NCR.").format(row.role))
		seen.add(row.role)
		if row.name not in old and (not row.user or row.role not in frappe.get_roles(row.user)):
			frappe.throw(_("{0} does not hold the role {1}.").format(row.user or _("Nobody"), row.role))
	kept = {r.name for r in doc.get("sign_offs") or []}
	if any(name not in kept for name in old):
		frappe.throw(_("A signature on an NCR cannot be removed."))


def on_update_ncr(doc):
	"""PEPL NCR on_update: the Quality ToDo of a system-raised NCR follows its status."""
	if doc.status in (CLOSED, CANCELLED):
		alerts.close_one(OPEN_RULE, NCR, doc.name)
	elif cint(doc.raised_by_system):
		alerts.raise_todo(
			OPEN_RULE,
			NCR,
			doc.name,
			_("{0} NCR ({1}) on {2}: {3}").format(
				_(doc.severity), _(doc.source), doc.item, (doc.defect_description or "")[:200]
			),
			owner_field=OWNER_FIELD,
			priority="High" if doc.severity == CRITICAL else "Medium",
		)


@frappe.whitelist()
def sign_off(ncr, remarks=None):
	"""The current user signs the NCR for every required role they hold that has not signed yet."""
	doc = frappe.get_doc(NCR, ncr)
	doc.check_permission("read")
	if doc.status in (CLOSED, CANCELLED):
		frappe.throw(_("A {0} NCR takes no more sign-offs.").format(_(doc.status)))
	mine = set(frappe.get_roles())
	roles = [role for role in missing_signatures(doc) if role in mine]
	if not roles:
		still = missing_signatures(doc)
		frappe.throw(
			_("You hold none of the roles still to sign ({0}).").format(
				", ".join(still) or _("none: all signed")
			)
		)
	for role in roles:
		doc.append(
			"sign_offs",
			{"role": role, "user": frappe.session.user, "signed_on": now_datetime(), "remarks": remarks},
		)
	if doc.status == OPEN:
		doc.status = UNDER_REVIEW
	doc.flags.ignore_permissions = True  # e.g. the CEO signs a Critical NCR with view-only access
	doc.save()
	return {"signed": roles, "missing": missing_signatures(doc), "status": doc.status}


@frappe.whitelist()
def get_sign_off_state(ncr):
	"""For the form: required roles, who signed, what is missing, and whether this user can sign now."""
	doc = frappe.get_doc(NCR, ncr)
	doc.check_permission("read")
	mine = set(frappe.get_roles())
	missing = missing_signatures(doc)
	return {
		"required": required_roles(doc.severity),
		"signed": [
			{"role": r.role, "user": r.user, "signed_on": r.signed_on} for r in doc.get("sign_offs") or []
		],
		"missing": missing,
		"can_sign": doc.status not in (CLOSED, CANCELLED) and any(r in mine for r in missing),
	}


# Raising -----------------------------------------------------------------------------------------------------------


def _exists(key):
	return frappe.db.get_value(NCR, {**key, "status": ["!=", CANCELLED]}, "name")


def raise_ncr(rule, key, values):
	"""Create the system NCR for this event unless one (not cancelled) exists. Returns its name."""
	existing = _exists({**key, "raise_rule": rule})
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": NCR,
			"status": OPEN,
			"severity": auto_severity(),
			"raised_by_system": 1,
			"raise_rule": rule,
			"raised_on": frappe.utils.today(),
			**key,
			**values,
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True  # every link comes from the document that raised it
	doc.insert()
	return doc.name


def cancel_auto(rule, key, reason):
	"""Cancel the unsigned Open system NCRs of this event (the event was cancelled or no longer applies)."""
	cancelled = []
	for name in frappe.get_all(
		NCR, filters={**key, "raise_rule": rule, "status": OPEN, "raised_by_system": 1}, pluck="name"
	):
		doc = frappe.get_doc(NCR, name)
		if doc.get("sign_offs"):
			continue
		doc.status = CANCELLED
		doc.cancel_reason = reason
		doc.flags.ignore_permissions = True
		# 0.64.1: the system only changes the status here; a linked record renamed or removed since the NCR was
		# raised must not stop it (CI #69: the cancel was refused on a missing customer and the NCR stayed Open)
		doc.flags.ignore_links = True
		doc.save()
		cancelled.append(name)
	return cancelled


def _safely(label, fn, *args):
	"""Run a raise / cancel without ever stopping the triggering document."""
	frappe.db.savepoint("pepl_ncr")
	try:
		return fn(*args)
	except Exception:
		frappe.db.rollback(save_point="pepl_ncr")
		frappe.log_error(title=f"PEPL: NCR not raised ({label})")
		return None


# QA-NCR-QI: a rejected QC Inspection ------------------------------------------------------------------------------


def _inspection_values(qi):
	values = {
		"source": SOURCE_BY_INSPECTION.get(qi.inspection_type, "Other"),
		"item": qi.item_code,
		"batch_no": qi.get("batch_no"),
		"supplier": qi.get("custom_supplier"),
		"qty_affected": flt(qi.sample_size),
		"defect_description": _("QC Inspection {0} Rejected: {1}").format(
			qi.name,
			", ".join(r.specification for r in qi.get("readings") or [] if r.status == "Rejected")
			or (qi.get("remarks") or _("see the inspection")),
		)[:1000],
	}
	if qi.reference_type == "Purchase Receipt":
		values["purchase_receipt"] = qi.reference_name
		if qi.get("child_row_reference"):
			received = frappe.db.get_value("Purchase Receipt Item", qi.child_row_reference, "received_qty")
			values["qty_affected"] = flt(received) or values["qty_affected"]
	elif qi.reference_type == "Job Card":
		values["work_order"], values["workstation"] = frappe.db.get_value(
			"Job Card", qi.reference_name, ["work_order", "workstation"]
		) or (None, None)
	elif qi.reference_type == "Delivery Note":
		values["delivery_note"] = qi.reference_name
		values["customer"] = frappe.db.get_value("Delivery Note", qi.reference_name, "customer")
	return values


def on_inspection_submit(doc, method=None):
	"""doc_events: Quality Inspection on_submit."""
	if doc.status == "Accepted":
		return None
	return _safely(doc.name, raise_ncr, RULE_QI, {"quality_inspection": doc.name}, _inspection_values(doc))


def on_inspection_cancel(doc, method=None):
	"""doc_events: Quality Inspection on_cancel."""
	return _safely(
		doc.name,
		cancel_auto,
		RULE_QI,
		{"quality_inspection": doc.name},
		_("QC Inspection {0} was cancelled.").format(doc.name),
	)


# QA-NCR-RETURN: a customer return ----------------------------------------------------------------------------------


def _return_lines(dn):
	lines = {}
	for row in dn.get("items") or []:
		line = lines.setdefault(
			row.item_code,
			{"qty": 0, "sales_order": row.get("against_sales_order"), "batch_no": row.get("batch_no")},
		)
		line["qty"] += abs(flt(row.get("stock_qty") or row.get("qty")))
	return lines


def _raise_returns(dn):
	made = []
	for item, line in _return_lines(dn).items():
		made.append(
			raise_ncr(
				RULE_RETURN,
				{"delivery_note": dn.name, "item": item},
				{
					"source": CUSTOMER,
					"customer": dn.customer,
					"against_delivery_note": dn.get("return_against"),
					"sales_order": line["sales_order"],
					"batch_no": line["batch_no"],
					"qty_affected": line["qty"],
					"defect_description": _("Customer {0} returned {1} {2} (return {3} against {4}).").format(
						dn.customer, qty_text(line["qty"]), item, dn.name, dn.get("return_against") or "-"
					),
				},
			)
		)
	return made


def on_delivery_note_submit(doc, method=None):
	"""doc_events: Delivery Note on_submit. A customer return raises its NCRs."""
	if not cint(doc.get("is_return")) or not params.is_enabled(RETURN_FIELD, 1):
		return None
	return _safely(doc.name, _raise_returns, doc)


def on_delivery_note_cancel(doc, method=None):
	"""doc_events: Delivery Note on_cancel."""
	if not cint(doc.get("is_return")):
		return None
	return _safely(
		doc.name,
		cancel_auto,
		RULE_RETURN,
		{"delivery_note": doc.name},
		_("Customer return {0} was cancelled.").format(doc.name),
	)


# QA-NCR-RATE: rejection rate on the shift entries of a day ---------------------------------------------------------


def day_figures(item, on_date):
	"""(good, rejected) of an item on the submitted shift entries of one day."""
	row = frappe.db.sql(
		f"""select coalesce(sum(p.good_qty), 0), coalesce(sum(p.rejected_qty), 0)
		from `tab{SPR_ROW}` p join `tab{SPR}` s on s.name = p.parent
		where s.docstatus = 1 and s.posting_date = %s and p.production_item = %s""",
		(on_date, item),
	)
	return flt(row[0][0]), flt(row[0][1])


def check_rate(item, on_date):
	"""Raise (or cancel) the QA-NCR-RATE NCR of one item and day. Returns the NCR name or None."""
	threshold = params.get_float(RATE_FIELD, 5)
	minimum = params.get_int(MIN_PIECES_FIELD, 20) or 1
	good, rejected = day_figures(item, on_date)
	made = good + rejected
	rate = 100.0 * rejected / made if made else 0
	key = {"item": item, "rate_date": on_date}
	if threshold <= 0 or made < minimum or rate <= threshold:
		cancel_auto(
			RULE_RATE,
			key,
			_("The rejection rate of {0} on {1} is no longer above the threshold.").format(item, on_date),
		)
		return None
	values = {
		"source": IN_PROCESS,
		"pieces_made": made,
		"pieces_rejected": rejected,
		"rejection_rate": round(rate, 2),
		"qty_affected": rejected,
		"defect_description": _(
			"{0} pieces of {1} rejected out of {2} made on {3} ({4}%, threshold {5}%)."
		).format(
			qty_text(rejected),
			item,
			qty_text(made),
			frappe.utils.formatdate(on_date),
			qty_text(round(rate, 1)),
			qty_text(threshold),
		),
	}
	name = raise_ncr(RULE_RATE, key, values)
	if frappe.db.get_value(NCR, name, "status") == OPEN:
		frappe.db.set_value(
			NCR, name, {k: values[k] for k in ("pieces_made", "pieces_rejected", "rejection_rate")}
		)
	return name


def on_entry_change(doc):
	"""Called from the shift entry's on_submit and on_cancel. Never stops the entry."""
	items = sorted({row.production_item for row in doc.get("production") or [] if row.get("production_item")})
	return [_safely(doc.name, check_rate, item, doc.posting_date) for item in items]
