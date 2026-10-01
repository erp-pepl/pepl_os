"""C2-15 - Heat numbers at the gate, the Receipt Log and the heat trace.

Two ways an item carries its heat number (decided per item, automatically):
  * Batch = heat: a heat-tracked item with no stock history gets "Has Batch No"
    on when it is created. On a Purchase Receipt (or a Stock Entry receipt) the
    Batch is created or reused from supplier + heat number, and the heat number
    and test certificate (MTC) are copied onto the Batch. Issues then pick the
    Batch, i.e. the heat.
  * Heat field: an item that already has stock transactions cannot be switched
    to batches (ERPNext refuses), so it keeps the heat number in a field on the
    receipt and issue lines.

The gate (PEPL System Parameters, "Heat Number Gate"):
  * Purchase Receipt submit: every heat-tracked line needs a heat number and an MTC.
  * Stock Entry: receipts and issues of heat-tracked items need a heat number.
  Hard Block refuses and lists the lines; Reason Required asks for a reason,
  which is written to the Audit Trail (rule STO-HEAT-MISSING).

Every submitted receipt line is written to the PEPL Receipt Log (never deleted;
a cancelled receipt marks its rows Cancelled). The PEPL Heat Number Trace report
follows a heat number from receipt to issue, Work Order and dispatch.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from pepl_os.common import params
from pepl_os.common.overrides import has_recent_override

HEAT_FIELD = "custom_heat_number"
MTC_FIELD = "custom_test_certificate"
TRACKED_FIELD = "custom_heat_tracked"
GATE_RULE = "STO-HEAT-MISSING"
HARD_BLOCK, REASON_REQUIRED = "Hard Block", "Reason Required"
RECEIPT_LOG = "PEPL Receipt Log"


def gate_mode():
	return params.get("custom_heat_number_gate_mode", HARD_BLOCK) or HARD_BLOCK


def item_flags(item_code):
	"""(heat tracked, has batch no) for an item."""
	values = frappe.get_cached_value("Item", item_code, [TRACKED_FIELD, "has_batch_no"]) or (0, 0)
	return cint(values[0]), cint(values[1])


def has_stock_history(item_code):
	return bool(frappe.db.exists("Stock Ledger Entry", {"item_code": item_code, "is_cancelled": 0}))


# Stock Settings ----------------------------------------------------------------------

BATCH_SWITCH = "enable_serial_and_batch_no_for_item"


def batches_enabled():
	return cint(frappe.db.get_single_value("Stock Settings", BATCH_SWITCH))


def enable_batches():
	"""Install / migrate: ERPNext v16 refuses every Batch until 'Activate Serial / Batch No for Item'
	is on in Stock Settings. Batch = heat needs it, so it is switched on (and never off)."""
	if batches_enabled():
		return False
	frappe.db.set_single_value("Stock Settings", BATCH_SWITCH, 1)
	frappe.db.set_default(BATCH_SWITCH, 1)
	frappe.clear_cache(doctype="Stock Settings")
	return True


# Item -------------------------------------------------------------------------------


def apply_item_heat_defaults(doc, stock_class, heat_classes):
	"""Called from the Item validate (C2-04). New raw material - and, from C2-16, new customer-supplied
	material - is heat-tracked; heat = Batch when possible."""
	if isinstance(heat_classes, str):
		heat_classes = (heat_classes,)
	if doc.is_new():
		doc.set(TRACKED_FIELD, 1 if stock_class in heat_classes else cint(doc.get(TRACKED_FIELD)))
	if cint(doc.get(TRACKED_FIELD)) and doc.is_stock_item and not doc.has_batch_no and batches_enabled():
		if doc.is_new() or not has_stock_history(doc.name):
			doc.has_batch_no = 1
			doc.create_new_batch = 0  # the Batch is made from the heat number at receipt


# Batch --------------------------------------------------------------------------------


def validate_batch(doc, method=None):
	"""doc_events: Batch validate. A heat-tracked item's batch must carry its heat number."""
	tracked, _batch = item_flags(doc.item)
	if tracked and not (doc.get(HEAT_FIELD) or "").strip():
		frappe.throw(
			_("Batch {0}: enter the heat number (item {1} is heat-tracked).").format(
				doc.name or "", doc.item
			),
			title=_("Heat number missing"),
		)


def find_batch(item_code, supplier, heat):
	filters = {"item": item_code, HEAT_FIELD: heat}
	if supplier:
		filters["supplier"] = supplier
	return frappe.db.get_value("Batch", filters, "name")


def _new_batch_id(heat):
	base = "".join(c if c.isalnum() or c in "-_." else "-" for c in heat.strip())[:120] or "HEAT"
	candidate, n = f"H-{base}", 1
	while frappe.db.exists("Batch", candidate):
		n += 1
		candidate = f"H-{base}-{n}"
	return candidate


def ensure_batch(item_code, supplier, heat, certificate=None, reference=None):
	"""The Batch for this item, supplier and heat number: reused if it exists, else created."""
	heat = heat.strip()
	name = find_batch(item_code, supplier, heat)
	if name:
		current = frappe.db.get_value("Batch", name, [MTC_FIELD, "reference_name"], as_dict=True)
		updates = {}
		if certificate and not current.get(MTC_FIELD):
			updates[MTC_FIELD] = certificate
		if reference and not current.reference_name and frappe.db.exists(*reference):
			updates.update({"reference_doctype": reference[0], "reference_name": reference[1]})
		if updates:
			frappe.db.set_value("Batch", name, updates, update_modified=False)
		return name
	if reference and not frappe.db.exists(*reference):
		# The receipt is being saved for the first time and is not in the database yet:
		# create the Batch without the link; the next save / submit fills it in (above).
		reference = None
	batch = frappe.get_doc(
		{
			"doctype": "Batch",
			"batch_id": _new_batch_id(heat),
			"item": item_code,
			"supplier": supplier,
			HEAT_FIELD: heat,
			MTC_FIELD: certificate,
			"reference_doctype": reference[0] if reference else None,
			"reference_name": reference[1] if reference else None,
		}
	)
	batch.flags.ignore_permissions = True
	batch.insert()
	return batch.name


def _sync_row_with_batch(row, item_code, supplier, reference):
	"""For a Batch = heat line: heat number -> Batch, or Batch -> heat number."""
	heat = (row.get(HEAT_FIELD) or "").strip()
	if heat:
		batch = ensure_batch(item_code, supplier, heat, row.get(MTC_FIELD), reference)
		if row.batch_no != batch:
			row.batch_no = batch
			row.use_serial_batch_fields = 1
	elif row.batch_no:
		row.set(HEAT_FIELD, frappe.db.get_value("Batch", row.batch_no, HEAT_FIELD))
	if row.batch_no and not row.get(MTC_FIELD):
		row.set(MTC_FIELD, frappe.db.get_value("Batch", row.batch_no, MTC_FIELD))


# Purchase Receipt -----------------------------------------------------------------------


def before_validate_receipt(doc, method=None):
	"""doc_events: Purchase Receipt before_validate. Create / reuse the heat Batch for each line."""
	if doc.get("is_return"):
		return
	for row in doc.items:
		tracked, batched = item_flags(row.item_code)
		if tracked and batched:
			_sync_row_with_batch(row, row.item_code, doc.supplier, ("Purchase Receipt", doc.name))


def receipt_gaps(doc):
	"""[(row, what is missing)] for heat-tracked lines without a heat number or MTC."""
	gaps = []
	if doc.get("is_return"):
		return gaps
	for row in doc.items:
		tracked, _batched = item_flags(row.item_code)
		if not tracked:
			continue
		missing = []
		if not (row.get(HEAT_FIELD) or "").strip():
			missing.append(_("heat number"))
		if not row.get(MTC_FIELD):
			missing.append(_("test certificate (MTC)"))
		if missing:
			gaps.append((row, " + ".join(missing)))
	return gaps


def gap_message(gaps):
	return "<br>".join(_("Row {0} {1}: no {2}").format(row.idx, row.item_code, what) for row, what in gaps)


def _gate(doc, gaps):
	if not gaps:
		return
	message = gap_message(gaps)
	if gate_mode() == REASON_REQUIRED:
		if has_recent_override(GATE_RULE, doc.doctype, doc.name):
			return
		frappe.throw(
			f"[{GATE_RULE}] " + message + "<br>" + _("A reason is required to continue."),
			title=_("Reason required"),
		)
	frappe.throw(
		_("Heat numbers and test certificates are mandatory for raw material:") + "<br>" + message,
		title=_("Heat number missing"),
	)


def before_submit_receipt(doc, method=None):
	"""doc_events: Purchase Receipt before_submit. The heat number gate."""
	_gate(doc, receipt_gaps(doc))


# Stock Entry --------------------------------------------------------------------------


def _is_receipt_row(row):
	return row.t_warehouse and not row.s_warehouse


def before_validate_stock_entry(doc, method=None):
	"""doc_events: Stock Entry before_validate. Heat -> Batch on receipts; Batch -> heat on issues."""
	for row in doc.items:
		tracked, batched = item_flags(row.item_code)
		if not (tracked and batched):
			continue
		if _is_receipt_row(row):
			_sync_row_with_batch(row, row.item_code, doc.get("supplier"), ("Stock Entry", doc.name))
		elif row.batch_no and not row.get(HEAT_FIELD):
			row.set(HEAT_FIELD, frappe.db.get_value("Batch", row.batch_no, HEAT_FIELD))


def stock_entry_gaps(doc):
	gaps = []
	for row in doc.items:
		tracked, batched = item_flags(row.item_code)
		if not tracked or (row.get(HEAT_FIELD) or "").strip():
			continue
		if batched and row.batch_no:
			continue
		if row.s_warehouse or row.t_warehouse:
			gaps.append((row, _("heat number")))
	return gaps


def before_submit_stock_entry(doc, method=None):
	"""doc_events: Stock Entry before_submit. Receipts and issues of heat-tracked items name the heat."""
	_gate(doc, stock_entry_gaps(doc))


@frappe.whitelist()
def heat_gate_check(doctype, name):
	"""For the form: the reason dialog message, or None when nothing is needed."""
	if doctype not in ("Purchase Receipt", "Stock Entry"):
		frappe.throw(_("Not supported"))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	gaps = receipt_gaps(doc) if doctype == "Purchase Receipt" else stock_entry_gaps(doc)
	if not gaps or gate_mode() != REASON_REQUIRED or has_recent_override(GATE_RULE, doctype, name):
		return None
	return {
		"rule_code": GATE_RULE,
		"message": frappe.utils.strip_html(gap_message(gaps).replace("<br>", "; ")),
	}


# Receipt Log ---------------------------------------------------------------------------------


def on_submit_receipt(doc, method=None):
	"""doc_events: Purchase Receipt on_submit. One Receipt Log row per line."""
	if doc.get("is_return"):
		return
	from pepl_os.pepl_stores.stock_tree import stock_class_of

	for row in doc.items:
		if frappe.db.exists(RECEIPT_LOG, {"pr_item": row.name}):
			continue
		frappe.get_doc(
			{
				"doctype": RECEIPT_LOG,
				"purchase_receipt": doc.name,
				"pr_item": row.name,
				"purchase_order": row.purchase_order,
				"supplier": doc.supplier,
				"supplier_name": doc.supplier_name,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"stock_class": stock_class_of(frappe.get_cached_value("Item", row.item_code, "item_group")),
				"heat_number": row.get(HEAT_FIELD),
				"batch_no": row.batch_no or _bundle_batch(row),
				"qty": row.qty,
				"uom": row.uom,
				"warehouse": row.warehouse,
				"test_certificate": row.get(MTC_FIELD),
				"received_by": doc.owner,
				"received_on": now_datetime(),
				"qc_status": "Pending",
				"status": "Active",
			}
		).insert(ignore_permissions=True)


def _bundle_batch(row):
	if not row.get("serial_and_batch_bundle"):
		return None
	return frappe.db.get_value("Serial and Batch Entry", {"parent": row.serial_and_batch_bundle}, "batch_no")


def on_cancel_receipt(doc, method=None):
	"""doc_events: Purchase Receipt on_cancel. Its Receipt Log rows are marked Cancelled, never deleted."""
	for name in frappe.get_all(RECEIPT_LOG, filters={"purchase_receipt": doc.name}, pluck="name"):
		frappe.db.set_value(RECEIPT_LOG, name, "status", "Cancelled", update_modified=False)


# Split by heat ---------------------------------------------------------------------------------


def split_line(doc, row_name, splits):
	"""Replace one receipt line with one line per heat; total quantity must stay the same."""
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft receipt can be split."))
	row = next((r for r in doc.items if r.name == row_name), None)
	if not row:
		frappe.throw(_("Line not found."))
	splits = [s for s in splits if (s.get("heat_number") or "").strip() and flt(s.get("qty")) > 0]
	if len(splits) < 2:
		frappe.throw(_("Give at least two heat numbers with a quantity each."))
	if len({s["heat_number"].strip() for s in splits}) != len(splits):
		frappe.throw(_("Each heat number may appear only once."))
	total = flt(sum(flt(s["qty"]) for s in splits), 3)
	if total != flt(row.qty, 3):
		frappe.throw(_("The heats add up to {0}, but the line is {1}.").format(total, flt(row.qty, 3)))
	base = row.as_dict(no_default_fields=True)
	for key in ("name", "idx", "batch_no", "serial_and_batch_bundle", HEAT_FIELD, MTC_FIELD):
		base.pop(key, None)
	position = doc.items.index(row)
	new_rows = []
	for s in splits:
		values = dict(base)
		ratio = flt(s["qty"]) / flt(row.qty)
		values.update(
			{
				"qty": flt(s["qty"]),
				"received_qty": flt(s["qty"]) + flt(row.rejected_qty) * ratio,
				"rejected_qty": flt(row.rejected_qty) * ratio,
				HEAT_FIELD: s["heat_number"].strip(),
				MTC_FIELD: s.get("test_certificate"),
			}
		)
		new_rows.append(values)
	items = list(doc.items)
	items.pop(position)
	doc.set("items", [])
	for r in items[:position] + [None] * len(new_rows) + items[position:]:
		if r is None:
			doc.append("items", new_rows.pop(0))
		else:
			doc.append("items", r)
	doc.save()
	return doc


@frappe.whitelist()
def split_by_heat(purchase_receipt, row_name, splits):
	doc = frappe.get_doc("Purchase Receipt", purchase_receipt)
	doc.check_permission("write")
	if isinstance(splits, str):
		splits = json.loads(splits)
	split_line(doc, row_name, splits)
	return len(doc.items)


# Panel ---------------------------------------------------------------------------------------------


@frappe.whitelist()
def get_receipt_panel(purchase_receipt):
	doc = frappe.get_doc("Purchase Receipt", purchase_receipt)
	doc.check_permission("read")
	rows = [{"text": _("Heat number gate: {0}").format(_(gate_mode())), "colour": "blue"}]
	tracked_rows = 0
	for row in doc.items:
		tracked, batched = item_flags(row.item_code)
		if not tracked:
			continue
		tracked_rows += 1
		heat = (row.get(HEAT_FIELD) or "").strip()
		if not heat:
			rows.append(
				{
					"text": _("Row {0} {1}: heat number missing").format(row.idx, row.item_code),
					"colour": "red",
				}
			)
		elif not row.get(MTC_FIELD):
			rows.append(
				{
					"text": _("Row {0} {1}: heat {2}, MTC missing").format(row.idx, row.item_code, heat),
					"colour": "red",
				}
			)
		else:
			text = _("Row {0} {1}: heat {2}, MTC attached").format(row.idx, row.item_code, heat)
			if batched and row.batch_no:
				text += _(", batch {0}").format(row.batch_no)
			rows.append({"text": text, "colour": "green"})
	if not tracked_rows:
		rows.append({"text": _("No heat-tracked items on this receipt."), "colour": "gray"})
	return rows
