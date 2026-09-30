"""C2-11 - Purchase Order approval by value, and a promised date on every line.

  * Grand total (company currency) above "PO Approval Value (MD above)" in PEPL
    System Parameters: the PO is flagged "Needs MD Approval" and only the MD / CEO
    (role PEPL CEO) can submit it. The MD gets a ToDo for each such PO; it closes
    itself when the PO is submitted, cancelled or falls back under the value.
  * At or below the value: the Purchase Manager submits it (the Purchase User
    prepares, but does not submit).
  * No value set: no MD step; the Purchase Manager submits every PO.
  * Every line needs a Required By (promised) date, not earlier than the PO date.

The System Manager can always submit (administration and data corrections).
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, getdate

from pepl_os.common import alerts, params

THRESHOLD_FIELD = "custom_po_approval_value_threshold"
FLAG_FIELD = "custom_needs_md_approval"
MD_ROLE = "PEPL CEO"
MANAGER_ROLES = ("Purchase Manager", MD_ROLE, "System Manager")
MD_ROLES = (MD_ROLE, "System Manager")
TODO_RULE = "PUR-PO-MD-APPROVAL"


def threshold():
	return flt(params.get_float(THRESHOLD_FIELD, 0))


def needs_md(doc):
	limit = threshold()
	return bool(limit > 0 and flt(doc.base_grand_total) > limit)


def _money(doc, value):
	currency = frappe.get_cached_value("Company", doc.company, "default_currency") if doc.company else None
	return fmt_money(value, currency=currency)


def validate_schedule_dates(doc):
	po_date = getdate(doc.transaction_date)
	for row in doc.items:
		if not row.schedule_date:
			frappe.throw(
				_("Row {0} {1}: enter the Required By date the supplier promised.").format(
					row.idx, row.item_code
				),
				title=_("Promised date missing"),
			)
		if getdate(row.schedule_date) < po_date:
			frappe.throw(
				_("Row {0} {1}: the Required By date {2} is before the PO date {3}.").format(
					row.idx,
					row.item_code,
					frappe.format(row.schedule_date, "Date"),
					frappe.format(doc.transaction_date, "Date"),
				),
				title=_("Promised date too early"),
			)


def validate(doc, method=None):
	"""doc_events: Purchase Order validate."""
	validate_schedule_dates(doc)
	doc.set(FLAG_FIELD, 1 if needs_md(doc) else 0)


def refusal(doc, roles):
	"""Why these roles may not submit this PO, or None when they may."""
	roles = set(roles)
	if doc.get(FLAG_FIELD) or needs_md(doc):
		if not roles & set(MD_ROLES):
			return _(
				"This Purchase Order ({0}) is above the PO Approval Value ({1}). Only the MD / CEO can "
				"submit it. It is waiting in the MD's approval list."
			).format(_money(doc, doc.base_grand_total), _money(doc, threshold()))
		return None
	if not roles & set(MANAGER_ROLES):
		return _(
			"Only the Purchase Manager can submit a Purchase Order. Save it and ask the Purchase Manager."
		)
	return None


def before_submit(doc, method=None):
	"""doc_events: Purchase Order before_submit."""
	doc.set(FLAG_FIELD, 1 if needs_md(doc) else 0)
	message = refusal(doc, frappe.get_roles())
	if message:
		frappe.throw(message, frappe.PermissionError, title=_("Approval needed"))


def waiting_for_md():
	return frappe.get_all("Purchase Order", filters={"docstatus": 0, FLAG_FIELD: 1}, pluck="name")


def sync_md_todos(doc=None):
	"""Raise the MD's ToDo for this PO when it waits; close ToDos of POs that no longer wait."""
	try:
		if doc and doc.docstatus == 0 and doc.get(FLAG_FIELD):
			alerts.raise_todo(
				TODO_RULE,
				"Purchase Order",
				doc.name,
				_(
					"Purchase Order {0} for {1}, {2}, is above the PO Approval Value: approve (submit) it."
				).format(doc.name, doc.supplier_name or doc.supplier, _money(doc, doc.base_grand_total)),
				owner_field="custom_md_approver",
				priority="High",
			)
		alerts.close_resolved(TODO_RULE, "Purchase Order", waiting_for_md())
	except Exception:
		# A missing notification owner must never stop a Purchase Order.
		frappe.log_error(title="PEPL: MD approval ToDo not updated")


def on_update(doc, method=None):
	"""doc_events: Purchase Order on_update / on_submit / on_cancel."""
	sync_md_todos(doc)


@frappe.whitelist()
def po_approval_info(purchase_order, user=None):
	"""For the form panel (and the System Manager checking who may approve)."""
	doc = frappe.get_doc("Purchase Order", purchase_order)
	doc.check_permission("read")
	if user and user != frappe.session.user:
		frappe.only_for("System Manager")
	roles = frappe.get_roles(user or frappe.session.user)
	limit = threshold()
	return {
		"needs_md": needs_md(doc),
		"threshold": limit,
		"threshold_text": _money(doc, limit) if limit else "",
		"total_text": _money(doc, doc.base_grand_total),
		"refusal": refusal(doc, roles),
	}
