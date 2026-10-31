"""C3a-B6 - Shift-entry rejections go to the Scrap Register (C2-18) by themselves.

When a Shift Production Entry is submitted, the pieces it rejected become a Scrap Weighment with source
"Rejection", linked to the entry:
- Scrap item: the made item's "Scrap Item when Rejected" (Item, Inventory section); else "Rejection Scrap Item"
  in System Parameters. If the Job Order's BOM uses customer-supplied material, the CSM twin of that scrap item
  (CSM-<code>, under CSM Scrap) against the Job Order's Sales Order - CSM scrap never mixes with PEPL scrap.
- Weight: rejected pieces x the made item's Weight Per Unit (Kg or Gram).
- The weighment is submitted at once: it posts the scrap into Scrap Yard at the scrap rate of the day (CSM:
  into CSM Scrap at zero), exactly as a weighment typed by Stores.
- When the scrap item, the weight per unit or the scrap rate is missing, nothing is posted: Stores gets one
  ToDo on the entry ("weigh N rejected pieces of ... and enter a Scrap Weighment, source Rejection").
Cancelling the entry cancels its weighments and closes the ToDo. A failure never stops the shift entry (Error
Log + ToDo). Setting: "Rejections to Scrap Register" (on by default).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pepl_os.common import alerts, params
from pepl_os.pepl_production.job_order_panel import qty_text
from pepl_os.pepl_stores import scrap, stock_tree

SPR = "PEPL Shift Production Entry"
ENABLE_FIELD = "custom_rejections_to_scrap"
FALLBACK_FIELD = "custom_rejection_scrap_item"
ITEM_FIELD = "custom_rejection_scrap_item"
LINK_FIELD = "shift_production_entry"
RULE = "PRD-REJECT-SCRAP"
OWNER_FIELD = "custom_stores_notification_owner"
KG_UOMS = {
	"kg": 1.0,
	"kgs": 1.0,
	"kilogram": 1.0,
	"kilograms": 1.0,
	"gram": 0.001,
	"grams": 0.001,
	"gm": 0.001,
	"g": 0.001,
}


def enabled():
	return params.is_enabled(ENABLE_FIELD, 1)


def kg_per_piece(item_code):
	"""Weight Per Unit of the item in kg, or None when it is not set in Kg or Gram."""
	values = frappe.db.get_value("Item", item_code, ["weight_per_unit", "weight_uom"], as_dict=True)
	if not values or flt(values.weight_per_unit) <= 0:
		return None
	factor = KG_UOMS.get((values.weight_uom or "Kg").strip().lower())
	return flt(values.weight_per_unit) * factor if factor else None


def _uses_csm(bom_no):
	if not bom_no:
		return False
	return any(
		scrap.is_csm_scrap_item(code) or stock_tree._is_csm_item(code)
		for code in frappe.get_all(
			"BOM Item", filters={"parent": bom_no, "parenttype": "BOM"}, pluck="item_code"
		)
	)


def plan(doc):
	"""What the entry's rejections become: one dict per (scrap item, source, sales order)."""
	groups = {}
	for row in doc.get("production") or []:
		if flt(row.rejected_qty) <= 0 or not row.job_card:
			continue
		card = frappe.db.get_value(
			"Job Card", row.job_card, ["production_item", "work_order", "bom_no"], as_dict=True
		)
		if not card:
			continue
		item = card.production_item
		scrap_item = frappe.db.get_value("Item", item, ITEM_FIELD) or params.get(FALLBACK_FIELD)
		source, sales_order = scrap.REJECTION, None
		if scrap_item and _uses_csm(card.bom_no):
			twin = "CSM-" + scrap_item
			scrap_item = twin if frappe.db.exists("Item", twin) else None
			source = scrap.SOURCE_CSM
			sales_order = frappe.db.get_value("Work Order", card.work_order, "sales_order")
		per = kg_per_piece(item)
		key = (scrap_item, source, sales_order)
		g = groups.setdefault(
			key,
			{
				"scrap_item": scrap_item,
				"source": source,
				"sales_order": sales_order,
				"pieces": 0.0,
				"kg": 0.0,
				"items": [],
				"missing": [],
			},
		)
		g["pieces"] += flt(row.rejected_qty)
		if item not in g["items"]:
			g["items"].append(item)
		if per:
			g["kg"] += flt(row.rejected_qty) * per
		elif _("weight per unit of {0}").format(item) not in g["missing"]:
			g["missing"].append(_("weight per unit of {0}").format(item))
	for g in groups.values():
		if not g["scrap_item"]:
			g["missing"].insert(0, _("scrap item (Item: Scrap Item when Rejected, or System Parameters)"))
		elif g["source"] == scrap.SOURCE_CSM and not g["sales_order"]:
			g["missing"].append(_("Sales Order of the Job Order (CSM scrap)"))
		elif g["source"] != scrap.SOURCE_CSM and not scrap.rate_on(g["scrap_item"], doc.posting_date):
			g["missing"].append(_("scrap rate of {0}").format(g["scrap_item"]))
	return list(groups.values())


def _todo(doc, pending):
	text = "; ".join(
		_("{0} rejected piece(s) of {1} - missing: {2}").format(
			qty_text(g["pieces"]), ", ".join(g["items"]), ", ".join(g["missing"])
		)
		for g in pending
	)
	alerts.raise_todo(
		RULE,
		SPR,
		doc.name,
		_(
			"Shift entry {0} ({1}, {2}): weigh the rejected pieces and enter a Scrap Weighment (source Rejection). {3}"
		).format(doc.name, doc.workstation, doc.posting_date, text),
		owner_field=OWNER_FIELD,
	)


def on_submit(doc):
	"""SPR on_submit: post the rejections to the Scrap Register (never stops the entry)."""
	if not enabled():
		return
	groups = plan(doc)
	if not groups:
		return
	pending = []
	for g in groups:
		if g["missing"] or g["kg"] <= 0:
			pending.append(g)
			continue
		frappe.db.savepoint("pepl_rejection_scrap")
		try:
			weighment = frappe.get_doc(
				{
					"doctype": scrap.WEIGHMENT,
					"company": doc.company,
					"weighment_date": doc.posting_date,
					"machine_group": doc.get("workstation_type")
					or frappe.db.get_value("Workstation", doc.workstation, "workstation_type"),
					"source": g["source"],
					"scrap_item": g["scrap_item"],
					"sales_order": g["sales_order"],
					"gross_kg": round(g["kg"], 3),
					"tare_kg": 0,
					LINK_FIELD: doc.name,
					"rejected_pieces": g["pieces"],
				}
			)
			weighment.flags.ignore_permissions = True
			weighment.insert()
			weighment.submit()
		except Exception:
			frappe.db.rollback(save_point="pepl_rejection_scrap")
			frappe.log_error(title=f"PEPL rejection scrap not posted for {doc.name}")
			g["missing"].append(_("the weighment could not be posted (see Error Log)"))
			pending.append(g)
	if pending:
		_todo(doc, pending)


def on_cancel(doc):
	"""SPR on_cancel: cancel its rejection weighments and close the ToDo."""
	for name in frappe.get_all(scrap.WEIGHMENT, filters={LINK_FIELD: doc.name, "docstatus": 1}, pluck="name"):
		weighment = frappe.get_doc(scrap.WEIGHMENT, name)
		weighment.flags.ignore_permissions = True
		weighment.cancel()
	for name in frappe.get_all(
		"ToDo",
		filters={
			"reference_type": SPR,
			"reference_name": doc.name,
			"status": "Open",
			"description": ["like", f"%{RULE}%"],
		},
		pluck="name",
	):
		frappe.db.set_value("ToDo", name, "status", "Cancelled")


def panel_rows(doc):
	"""Shift panel rows of a submitted entry: where its rejections went."""
	if cint(doc.docstatus) != 1 or not flt(doc.get("total_rejected_qty")):
		return []
	rows = []
	for w in frappe.get_all(
		scrap.WEIGHMENT,
		filters={LINK_FIELD: doc.name, "docstatus": 1},
		fields=["name", "scrap_item", "net_kg", "rejected_pieces", "amount"],
	):
		rows.append(
			{
				"text": _("{0} rejected piece(s) → Scrap Weighment {1}: {2} kg {3}").format(
					qty_text(w.rejected_pieces), w.name, qty_text(w.net_kg), w.scrap_item
				),
				"colour": "gray",
			}
		)
	if frappe.db.exists(
		"ToDo",
		{
			"reference_type": SPR,
			"reference_name": doc.name,
			"status": "Open",
			"description": ["like", f"%{RULE}%"],
		},
	):
		rows.append({"text": _("Rejected pieces waiting for Stores to weigh (ToDo)"), "colour": "orange"})
	return rows
