"""C3b-Q1 - Incoming QC Inspection, created with the Purchase Receipt, and the incoming QC gate.

QC Inspection = ERPNext's own Quality Inspection (decided 11 Nov 2026), so ERPNext's checks keep working.

Which items are inspected on receipt:
  * the Item's own tick "Inspection Required before Purchase" (ERPNext's field) decides, line by line;
  * PEPL System Parameters > Quality > "Incoming QC: Stock Classes" sets that tick by stock class: a new item of
    a listed class gets it ticked; adding a class ticks every stock item of that class, removing a class unticks
    them. An item's tick can still be changed by hand afterwards.

On every save of a draft receipt, each line whose item needs inspection gets its own draft QC Inspection
(type Incoming, sample size = the line's received quantity, the item's inspection plan = its Quality Inspection
Template, the heat Batch of the line). A line removed or changed to another item loses its unused draft. An item
without an inspection plan gives the Quality owner a ToDo (QA-NO-QC-PLAN), closed when the plan is set.

The gate (receipt submit), "Incoming QC Gate" in System Parameters:
  * a line whose QC Inspection is not submitted yet, or is Rejected while some quantity is still accepted into
    stores, is a gap;
  * Advisory = warning only; Soft Block = a reason is needed (rule QA-IN-QC, Override Log);
    Hard Block = the receipt is refused.
ERPNext's own "Stop" actions in Stock Settings would refuse before PEPL's gate can ask for a reason, so setup
switches them to "Warn" once (PEPL's gate is the rule); a line with no QC Inspection at all is still refused by
ERPNext itself.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from pepl_os.common import alerts, params
from pepl_os.common.overrides import has_recent_override
from pepl_os.pepl_stores import stock_tree

QI = "Quality Inspection"
PR = "Purchase Receipt"
PR_ITEM = "Purchase Receipt Item"
FLAG = "inspection_required_before_purchase"
TEMPLATE = "quality_inspection_template"
AUTO_FIELD = "custom_auto_created"
SUPPLIER_FIELD = "custom_supplier"
CLASSES_FIELD = "custom_incoming_qc_stock_classes"
MODE_FIELD = "custom_incoming_qc_gate_mode"
OWNER_FIELD = "custom_quality_notification_owner"
ADVISORY, SOFT_BLOCK, HARD_BLOCK = "Advisory", "Soft Block", "Hard Block"
MODES = (ADVISORY, SOFT_BLOCK, HARD_BLOCK)
GATE_RULE = "QA-IN-QC"
NO_PLAN_RULE = "QA-NO-QC-PLAN"
# Capital Equipment is never stock, so it is never received into stores and never inspected here.
ALLOWED_CLASSES = tuple(c for c in stock_tree.STOCK_CLASSES if c != stock_tree.CAPITAL)
STOCK_SETTINGS_FLAG = "pepl_qc_stock_settings_set"
STOCK_SETTINGS_ACTIONS = (
	"action_if_quality_inspection_is_not_submitted",
	"action_if_quality_inspection_is_rejected",
)


# Settings ---------------------------------------------------------------------------------------------------


def gate_mode():
	mode = params.get(MODE_FIELD, SOFT_BLOCK) or SOFT_BLOCK
	return mode if mode in MODES else SOFT_BLOCK


def parse_classes(value):
	"""The stock classes named one per line (or comma-separated), in order, without repeats."""
	names = []
	for part in cstr(value).replace(",", "\n").splitlines():
		part = part.strip()
		if part and part not in names:
			names.append(part)
	return names


def stock_classes(value=None):
	"""The listed stock classes that exist (unknown names are refused when the parameters are saved)."""
	raw = params.get(CLASSES_FIELD, "") if value is None else value
	return [c for c in parse_classes(raw) if c in ALLOWED_CLASSES]


def validate_params(doc):
	"""Called from the System Parameters validation. Returns a list of error messages."""
	errors = []
	unknown = [c for c in parse_classes(doc.get(CLASSES_FIELD)) if c not in ALLOWED_CLASSES]
	if unknown:
		errors.append(
			_("Incoming QC: Stock Classes - unknown class {0}. Use one per line from: {1}.").format(
				", ".join(unknown), ", ".join(ALLOWED_CLASSES)
			)
		)
	mode = doc.get(MODE_FIELD)
	if mode not in (None, "") and mode not in MODES:
		errors.append(_("Incoming QC Gate must be Advisory, Soft Block or Hard Block."))
	return errors


def switch_stock_settings_once():
	"""Install / migrate: ERPNext's "Stop" when a QC Inspection is not submitted or is rejected becomes "Warn",
	once, so PEPL's gate (with its Soft Block reason) decides. If PEPL later sets "Stop" again, it stays."""
	if cint(frappe.db.get_default(STOCK_SETTINGS_FLAG)):
		return False
	changed = False
	for field in STOCK_SETTINGS_ACTIONS:
		if frappe.db.get_single_value("Stock Settings", field) != "Warn":
			frappe.db.set_single_value("Stock Settings", field, "Warn")
			changed = True
	if changed:
		frappe.clear_cache(doctype="Stock Settings")
	frappe.db.set_default(STOCK_SETTINGS_FLAG, 1)
	return changed


# Which items are inspected -----------------------------------------------------------------------------------


def needs_inspection(item_code):
	return bool(item_code) and bool(cint(frappe.get_cached_value("Item", item_code, FLAG)))


def validate_item(doc, method=None):
	"""doc_events: Item validate (after stock_tree.validate_item, which sets the stock class).

	A new item, or an item moved into a listed class, gets "Inspection Required before Purchase" ticked; an item
	moved out of a listed class into an unlisted one gets it unticked. Otherwise the tick is left as it is.
	"""
	listed = stock_classes()
	new_class = doc.get("custom_stock_class")
	before = None if doc.is_new() else doc.get_doc_before_save()
	old_class = before.get("custom_stock_class") if before else None
	if cint(doc.get("is_stock_item")) and (doc.is_new() or new_class != old_class):
		if new_class in listed:
			doc.set(FLAG, 1)
		elif old_class in listed:
			doc.set(FLAG, 0)
	if doc.get(TEMPLATE) and not doc.is_new():
		alerts.close_one(NO_PLAN_RULE, "Item", doc.name)


def apply_classes(added=(), removed=()):
	"""Tick "Inspection Required before Purchase" on every stock item of the added classes and untick it on
	every item of the removed classes. Returns (ticked, unticked)."""
	ticked = unticked = 0
	for stock_class, value in [(c, 1) for c in added] + [(c, 0) for c in removed]:
		names = frappe.get_all(
			"Item",
			filters={"custom_stock_class": stock_class, "is_stock_item": 1, FLAG: 1 - value},
			pluck="name",
		)
		for name in names:
			frappe.db.set_value("Item", name, FLAG, value, update_modified=False)
			frappe.clear_document_cache("Item", name)
		if value:
			ticked += len(names)
		else:
			unticked += len(names)
	if ticked or unticked:
		frappe.clear_cache(doctype="Item")
	return ticked, unticked


def on_parameters_update(doc, method=None):
	"""doc_events: PEPL System Parameters on_update. A changed class list ticks / unticks the items."""
	before = doc.get_doc_before_save()
	old = set(stock_classes(before.get(CLASSES_FIELD) if before else ""))
	new = set(stock_classes(doc.get(CLASSES_FIELD)))
	if old == new:
		return None
	ticked, unticked = apply_classes(sorted(new - old), sorted(old - new))
	if ticked or unticked:
		frappe.msgprint(
			_("Incoming QC: {0} item(s) now need inspection on receipt, {1} no longer.").format(
				ticked, unticked
			),
			indicator="blue",
			alert=True,
		)
	return ticked, unticked


@frappe.whitelist()
def apply_incoming_qc_classes():
	"""Tick every stock item of the listed classes again (e.g. after items were imported). Nothing is unticked."""
	frappe.only_for(("System Manager", "Quality Manager"))
	ticked, _unticked = apply_classes(stock_classes())
	return {"ticked": ticked, "classes": stock_classes()}


# The QC Inspection of each receipt line ----------------------------------------------------------------------


def before_validate_receipt(doc, method=None):
	"""doc_events: Purchase Receipt before_validate. A line keeps a QC Inspection only if it is this receipt's,
	for this item (a copied or amended receipt, or a line changed to another item, drops the old link)."""
	if doc.get("is_return"):
		return
	for row in doc.items:
		name = row.get("quality_inspection")
		if not name:
			continue
		qi = frappe.db.get_value(
			QI, name, ["reference_type", "reference_name", "item_code", AUTO_FIELD], as_dict=True
		)
		if not qi:
			row.quality_inspection = None
		elif (qi.reference_type, qi.reference_name) != (doc.doctype, doc.name):
			row.quality_inspection = None
		elif qi.item_code != row.item_code and cint(qi.get(AUTO_FIELD)):
			row.quality_inspection = None


def _make_inspection(doc, row):
	qi = frappe.get_doc(
		{
			"doctype": QI,
			"inspection_type": "Incoming",
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"child_row_reference": row.name,
			"item_code": row.item_code,
			"description": row.get("description"),
			"batch_no": row.get("batch_no") or None,
			"sample_size": flt(row.get("received_qty")) or flt(row.qty) or 1,
			"report_date": doc.posting_date,
			"inspected_by": frappe.session.user,
			"company": doc.company,
			"remarks": _("Created with {0}, line {1}.").format(doc.name, row.idx),
			AUTO_FIELD: 1,
			SUPPLIER_FIELD: doc.supplier,
		}
	)
	qi.flags.ignore_permissions = True
	qi.insert()
	return qi


def _flag_missing_plan(qi):
	if frappe.get_cached_value("Item", qi.item_code, TEMPLATE):
		return
	alerts.raise_todo(
		NO_PLAN_RULE,
		"Item",
		qi.item_code,
		_(
			"Item {0} is inspected on receipt but has no inspection plan (Quality Inspection Template), so QC "
			"Inspection {1} has no characteristics to measure. Set the item's Quality Inspection Template."
		).format(qi.item_code, qi.name),
		owner_field=OWNER_FIELD,
	)


def _remove_unused_drafts(doc):
	"""Delete this receipt's auto-made draft inspections that no line uses any more."""
	used = {row.quality_inspection for row in doc.items if row.get("quality_inspection")}
	removed = 0
	for name in frappe.get_all(
		QI,
		filters={"reference_type": doc.doctype, "reference_name": doc.name, "docstatus": 0, AUTO_FIELD: 1},
		pluck="name",
	):
		if name not in used:
			frappe.delete_doc(QI, name, ignore_permissions=True, force=True)
			removed += 1
	return removed


def sync_inspections(doc, method=None):
	"""doc_events: Purchase Receipt on_update (draft). One draft QC Inspection per line that needs inspection."""
	if doc.docstatus != 0 or doc.get("is_return"):
		return []
	made = []
	for row in doc.items:
		if not needs_inspection(row.item_code):
			continue
		current = row.get("quality_inspection")
		if current and frappe.db.get_value(QI, current, "docstatus") in (0, 1):
			continue
		qi = _make_inspection(doc, row)
		frappe.db.set_value(PR_ITEM, row.name, "quality_inspection", qi.name, update_modified=False)
		row.quality_inspection = qi.name
		made.append(qi)
	removed = _remove_unused_drafts(doc)
	if made or removed:
		# ERPNext stamps the receipt's modified time when an inspection is linked or deleted; keep the form in step.
		doc.modified = frappe.db.get_value(doc.doctype, doc.name, "modified")
	for qi in made:
		_flag_missing_plan(qi)
	if made:
		_drop_required_messages()
	return [qi.name for qi in made]


def _drop_required_messages():
	"""ERPNext said "Quality Inspection is required" while validating; the inspection now exists, so the
	storekeeper is not shown a message that is no longer true."""
	log = getattr(frappe.local, "message_log", None)
	if not log:
		return
	frappe.local.message_log = [
		m
		for m in log
		if "Quality Inspection is required" not in cstr(m.get("message") if isinstance(m, dict) else m)
	]


def on_trash_receipt(doc, method=None):
	"""doc_events: Purchase Receipt on_trash. A deleted draft receipt takes its unused draft inspections along."""
	for name in frappe.get_all(
		QI,
		filters={"reference_type": doc.doctype, "reference_name": doc.name, "docstatus": 0, AUTO_FIELD: 1},
		pluck="name",
	):
		frappe.delete_doc(QI, name, ignore_permissions=True, force=True)


def validate_inspection(doc, method=None):
	"""doc_events: Quality Inspection validate. An incoming inspection names its supplier (for the scorecard)."""
	if doc.reference_type in (PR, "Purchase Invoice") and doc.reference_name and not doc.get(SUPPLIER_FIELD):
		doc.set(SUPPLIER_FIELD, frappe.db.get_value(doc.reference_type, doc.reference_name, "supplier"))


# The gate -----------------------------------------------------------------------------------------------------


def receipt_gaps(doc):
	"""[(row, what is wrong)] for lines that need inspection and are not cleared by it."""
	gaps = []
	if doc.get("is_return"):
		return gaps
	for row in doc.items:
		if not needs_inspection(row.item_code):
			continue
		name = row.get("quality_inspection")
		qi = name and frappe.db.get_value(QI, name, ["docstatus", "status"], as_dict=True)
		if not qi or qi.docstatus == 2:
			gaps.append((row, _("no QC Inspection")))
		elif qi.docstatus == 0:
			gaps.append((row, _("QC Inspection {0} is not finished (not submitted)").format(name)))
		elif qi.status != "Accepted" and flt(row.qty) > 0:
			gaps.append(
				(
					row,
					_("QC Inspection {0} is {1} but {2} is accepted into stores").format(
						name, _(qi.status), flt(row.qty)
					),
				)
			)
	return gaps


def gap_message(gaps):
	return "<br>".join(_("Row {0} {1}: {2}").format(row.idx, row.item_code, what) for row, what in gaps)


def before_submit_receipt(doc, method=None):
	"""doc_events: Purchase Receipt before_submit. The incoming QC gate."""
	gaps = receipt_gaps(doc)
	if not gaps:
		return
	message = gap_message(gaps)
	mode = gate_mode()
	if mode == ADVISORY:
		frappe.msgprint(message, title=_("Incoming QC not cleared"), indicator="orange")
		return
	if mode == SOFT_BLOCK:
		if has_recent_override(GATE_RULE, doc.doctype, doc.name):
			return
		frappe.throw(
			f"[{GATE_RULE}] " + message + "<br>" + _("A reason is required to continue."),
			title=_("Reason required"),
		)
	frappe.throw(_("Incoming inspection is not cleared:") + "<br>" + message, title=_("Incoming QC"))


@frappe.whitelist()
def qc_gate_check(name):
	"""For the form: the reason dialog message (Soft Block), or None when nothing is needed."""
	doc = frappe.get_doc(PR, name)
	doc.check_permission("read")
	gaps = receipt_gaps(doc)
	if not gaps or gate_mode() != SOFT_BLOCK or has_recent_override(GATE_RULE, PR, name):
		return None
	return {
		"rule_code": GATE_RULE,
		"message": frappe.utils.strip_html(gap_message(gaps).replace("<br>", "; ")),
	}


@frappe.whitelist()
def get_receipt_qc_panel(purchase_receipt):
	"""Rows for the "Incoming QC" panel on the receipt; None when no line needs inspection."""
	doc = frappe.get_doc(PR, purchase_receipt)
	doc.check_permission("read")
	rows = []
	for row in doc.items:
		if doc.get("is_return") or not needs_inspection(row.item_code):
			continue
		name = row.get("quality_inspection")
		qi = name and frappe.db.get_value(
			QI, name, ["docstatus", "status", "quality_inspection_template"], as_dict=True
		)
		label = _("Line {0} {1}").format(row.idx, row.item_code)
		if not qi or qi.docstatus == 2:
			rows.append(
				{"text": _("{0}: no QC Inspection yet - save the receipt").format(label), "colour": "red"}
			)
			continue
		plan = "" if qi.quality_inspection_template else " " + _("(no inspection plan)")
		if qi.docstatus == 0:
			rows.append(
				{"text": _("{0}: {1} to be inspected{2}").format(label, name, plan), "colour": "orange"}
			)
		elif qi.status == "Accepted":
			rows.append({"text": _("{0}: {1} Accepted").format(label, name), "colour": "green"})
		else:
			rows.append(
				{
					"text": _("{0}: {1} {2} - accepted qty {3}, rejected qty {4}").format(
						label, name, _(qi.status), flt(row.qty), flt(row.get("rejected_qty"))
					),
					"colour": "red",
				}
			)
	if not rows:
		return None
	if doc.docstatus == 0:
		rows.append({"text": _("Incoming QC gate: {0}").format(_(gate_mode())), "colour": "gray"})
	return rows
