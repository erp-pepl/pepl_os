"""C3b-Q5 - The dispatch gate on the Delivery Note: final inspection accepted, no open NCR on what is shipped.

Final inspection (QC Inspection of type Outgoing):
  * an item with ERPNext's "Inspection Required before Delivery" ticked is inspected before it leaves;
  * on every save of a draft Delivery Note each such line gets its own draft QC Inspection (Outgoing, sample size =
    the line's quantity, the item's inspection plan, the line's batch); a line removed or changed to another item
    loses its unused draft; a deleted draft Delivery Note takes its drafts along (same rules as the incoming QC, C3b-Q1).

The gate (Delivery Note submit, not on returns), "Dispatch Gate" in System Parameters:
  * a line whose final inspection is not submitted or not Accepted, and
  * a line whose item has an open NCR (Open / Under Review; when the NCR names a batch, only that batch)
  are gaps. Advisory = warning; Soft Block = a reason is needed (rule QA-DISPATCH, Override Log); Hard Block = the
  delivery is refused. A rejected final inspection raises its NCR by itself (C3b-Q3), so it also blocks until closed.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pepl_os.common import params
from pepl_os.common.overrides import has_recent_override
from pepl_os.pepl_production.job_order_panel import qty_text
from pepl_os.pepl_quality import incoming_qc

QI = "Quality Inspection"
DN = "Delivery Note"
DN_ITEM = "Delivery Note Item"
NCR = "PEPL NCR"
FLAG = "inspection_required_before_delivery"
MODE_FIELD = "custom_dispatch_gate_mode"
ADVISORY, SOFT_BLOCK, HARD_BLOCK = "Advisory", "Soft Block", "Hard Block"
MODES = (ADVISORY, SOFT_BLOCK, HARD_BLOCK)
GATE_RULE = "QA-DISPATCH"
OPEN_NCR_STATES = ("Open", "Under Review")


def gate_mode():
	mode = params.get(MODE_FIELD, SOFT_BLOCK) or SOFT_BLOCK
	return mode if mode in MODES else SOFT_BLOCK


def validate_params(doc):
	mode = doc.get(MODE_FIELD)
	if mode not in (None, "") and mode not in MODES:
		return [_("Dispatch Gate must be Advisory, Soft Block or Hard Block.")]
	return []


def needs_final_inspection(item_code):
	return bool(item_code) and bool(cint(frappe.get_cached_value("Item", item_code, FLAG)))


# The final inspection of each line ------------------------------------------------------------------------------


def before_validate_delivery(doc, method=None):
	"""doc_events: Delivery Note before_validate. A line keeps only this delivery's own inspection."""
	incoming_qc.before_validate_receipt(doc)


def _make_inspection(doc, row):
	qi = frappe.get_doc(
		{
			"doctype": QI,
			"inspection_type": "Outgoing",
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"child_row_reference": row.name,
			"item_code": row.item_code,
			"description": row.get("description"),
			"batch_no": row.get("batch_no") or None,
			"sample_size": flt(row.qty) or 1,
			"report_date": doc.posting_date,
			"inspected_by": frappe.session.user,
			"company": doc.company,
			"remarks": _("Final inspection for {0}, line {1}.").format(doc.name, row.idx),
			incoming_qc.AUTO_FIELD: 1,
		}
	)
	qi.flags.ignore_permissions = True
	qi.insert()
	return qi


def sync_final_inspections(doc, method=None):
	"""doc_events: Delivery Note on_update (draft). One draft final inspection per line that needs one."""
	if doc.docstatus != 0 or cint(doc.get("is_return")):
		return []
	made = []
	for row in doc.items:
		if not needs_final_inspection(row.item_code):
			continue
		current = row.get("quality_inspection")
		if current and frappe.db.get_value(QI, current, "docstatus") in (0, 1):
			continue
		qi = _make_inspection(doc, row)
		frappe.db.set_value(DN_ITEM, row.name, "quality_inspection", qi.name, update_modified=False)
		row.quality_inspection = qi.name
		made.append(qi)
	removed = incoming_qc._remove_unused_drafts(doc)
	if made or removed:
		doc.modified = frappe.db.get_value(doc.doctype, doc.name, "modified")
	if made:
		incoming_qc._drop_required_messages()
	return [qi.name for qi in made]


def on_trash_delivery(doc, method=None):
	"""doc_events: Delivery Note on_trash."""
	incoming_qc.on_trash_receipt(doc)


# The gate ---------------------------------------------------------------------------------------------------------


def open_ncrs(item_code, batch_no=None):
	"""Open / Under Review NCRs of the item that concern this line (an NCR naming a batch only concerns that batch)."""
	rows = frappe.get_all(
		NCR,
		filters={"item": item_code, "status": ["in", OPEN_NCR_STATES]},
		fields=["name", "batch_no", "severity"],
		order_by="creation asc",
	)
	return [r for r in rows if not r.batch_no or not batch_no or r.batch_no == batch_no]


def delivery_gaps(doc):
	"""[(row, what is wrong)] for every line that may not be dispatched."""
	gaps = []
	if cint(doc.get("is_return")):
		return gaps
	for row in doc.items:
		if needs_final_inspection(row.item_code):
			name = row.get("quality_inspection")
			qi = name and frappe.db.get_value(QI, name, ["docstatus", "status"], as_dict=True)
			if not qi or qi.docstatus == 2:
				gaps.append((row, _("no final inspection")))
			elif qi.docstatus == 0:
				gaps.append((row, _("final inspection {0} is not finished (not submitted)").format(name)))
			elif qi.status != "Accepted":
				gaps.append((row, _("final inspection {0} is {1}").format(name, _(qi.status))))
		ncrs = open_ncrs(row.item_code, row.get("batch_no"))
		if ncrs:
			shown = ", ".join(f"{n.name} ({_(n.severity)})" for n in ncrs[:3])
			more = _(" and {0} more").format(len(ncrs) - 3) if len(ncrs) > 3 else ""
			gaps.append((row, _("open NCR {0}{1}").format(shown, more)))
	return gaps


def gap_message(gaps):
	return "<br>".join(
		_("Row {0} {1} ({2}): {3}").format(row.idx, row.item_code, qty_text(row.qty), what)
		for row, what in gaps
	)


def before_submit_delivery(doc, method=None):
	"""doc_events: Delivery Note before_submit. The dispatch gate."""
	gaps = delivery_gaps(doc)
	if not gaps:
		return
	message = gap_message(gaps)
	mode = gate_mode()
	if mode == ADVISORY:
		frappe.msgprint(message, title=_("Dispatch: quality not cleared"), indicator="orange")
		return
	if mode == SOFT_BLOCK:
		if has_recent_override(GATE_RULE, doc.doctype, doc.name):
			return
		frappe.throw(
			f"[{GATE_RULE}] " + message + "<br>" + _("A reason is required to continue."),
			title=_("Reason required"),
		)
	frappe.throw(_("Quality has not cleared this dispatch:") + "<br>" + message, title=_("Dispatch gate"))


@frappe.whitelist()
def dispatch_gate_check(name):
	"""For the form: the reason dialog message (Soft Block), or None."""
	doc = frappe.get_doc(DN, name)
	doc.check_permission("read")
	gaps = delivery_gaps(doc)
	if not gaps or gate_mode() != SOFT_BLOCK or has_recent_override(GATE_RULE, DN, name):
		return None
	return {
		"rule_code": GATE_RULE,
		"message": frappe.utils.strip_html(gap_message(gaps).replace("<br>", "; ")),
	}


@frappe.whitelist()
def get_dispatch_panel(delivery_note):
	"""Rows for the "Dispatch QC" panel; None when nothing on the delivery concerns Quality."""
	doc = frappe.get_doc(DN, delivery_note)
	doc.check_permission("read")
	if cint(doc.get("is_return")):
		return None
	rows = []
	for row in doc.items:
		label = _("Line {0} {1}").format(row.idx, row.item_code)
		if needs_final_inspection(row.item_code):
			name = row.get("quality_inspection")
			qi = name and frappe.db.get_value(QI, name, ["docstatus", "status"], as_dict=True)
			if not qi or qi.docstatus == 2:
				rows.append(
					{
						"text": _("{0}: no final inspection yet - save the delivery").format(label),
						"colour": "red",
					}
				)
			elif qi.docstatus == 0:
				rows.append({"text": _("{0}: {1} to be inspected").format(label, name), "colour": "orange"})
			elif qi.status == "Accepted":
				rows.append({"text": _("{0}: {1} Accepted").format(label, name), "colour": "green"})
			else:
				rows.append({"text": _("{0}: {1} {2}").format(label, name, _(qi.status)), "colour": "red"})
		for n in open_ncrs(row.item_code, row.get("batch_no")):
			rows.append(
				{"text": _("{0}: open {1} NCR {2}").format(label, _(n.severity), n.name), "colour": "red"}
			)
	if not rows:
		return None
	if doc.docstatus == 0:
		rows.append({"text": _("Dispatch gate: {0}").format(_(gate_mode())), "colour": "gray"})
	return rows
