"""C2-09 - Request for Quotation filled in by RM group from a submitted Material Request.

"RFQ by RM Group" on the Material Request opens a dialog:
  * the request's lines, grouped by the RM group of each item;
  * for each group, every supplier that is Approved or Conditionally Approved
    for that group is ticked already, with its delivery and quality score;
  * the buyer may untick a supplier or add another one. A supplier that is not
    approved for the group is allowed, but submitting that RFQ asks for a
    reason (the C2-08 gate, rule SUP-NOT-APPROVED).
"Create" makes one draft Request for Quotation per group, linked to the request.
Lines already on an open RFQ are left out, so pressing it twice does not
send the same lines twice. The standard RFQ e-mail and supplier portal are
used unchanged.
"""

import json

import frappe
from erpnext.buying.doctype.request_for_quotation.request_for_quotation import RequestforQuotation
from frappe import _
from frappe.utils import getdate, today

from pepl_os.pepl_purchase.material_request import rm_group_of
from pepl_os.pepl_purchase.supplier_approval import APPROVED_STATES

RFQ = "Request for Quotation"
NO_GROUP = ""  # lines whose item has no RM group


def approved_suppliers(rm_group):
	"""Enabled suppliers Approved / Conditionally Approved for this RM group, by name."""
	if not rm_group:
		return []
	covered = frappe.get_all(
		"PEPL Supplier RM Group",
		filters={"parenttype": "Supplier", "parentfield": "custom_rm_groups", "rm_group": rm_group},
		pluck="parent",
	)
	if not covered:
		return []
	return frappe.get_all(
		"Supplier",
		filters={
			"name": ["in", covered],
			"disabled": 0,
			"custom_approval_state": ["in", list(APPROVED_STATES)],
		},
		order_by="supplier_name asc",
		pluck="name",
	)


def supplier_card(supplier):
	s = frappe.db.get_value(
		"Supplier",
		supplier,
		[
			"name",
			"supplier_name",
			"email_id",
			"custom_approval_state",
			"custom_delivery_score",
			"custom_delivery_scored_lines",
			"custom_quality_score",
		],
		as_dict=True,
	)
	return {
		"supplier": s.name,
		"supplier_name": s.supplier_name,
		"state": s.custom_approval_state or "Not Approved",
		"delivery_score": s.custom_delivery_score if s.custom_delivery_scored_lines else None,
		"quality_score": s.custom_quality_score or None,  # quality scoring arrives with the Quality cycle
		"has_email": bool(s.email_id),
	}


def lines_on_open_rfq(material_request):
	"""{Material Request Item name: RFQ name} for lines already on a draft or submitted RFQ."""
	rows = frappe.get_all(
		"Request for Quotation Item",
		filters={"material_request": material_request, "docstatus": ["<", 2]},
		fields=["material_request_item", "parent"],
	)
	return {r.material_request_item: r.parent for r in rows if r.material_request_item}


def _open_request(material_request):
	mr = frappe.get_doc("Material Request", material_request)
	if mr.docstatus != 1:
		frappe.throw(_("Submit the Material Request first."))
	if mr.material_request_type != "Purchase":
		frappe.throw(_("Only a Purchase request can go out for quotation."))
	if mr.status in ("Stopped", "Cancelled"):
		frappe.throw(_("This Material Request is {0}.").format(_(mr.status)))
	return mr


def plan(material_request):
	"""The groups the dialog shows: lines and pre-ticked suppliers per RM group."""
	mr = _open_request(material_request)
	done = lines_on_open_rfq(mr.name)
	groups = {}
	skipped = []
	for row in mr.items:
		if row.name in done:
			skipped.append({"idx": row.idx, "item_code": row.item_code, "rfq": done[row.name]})
			continue
		rm_group = rm_group_of(row.item_code) or NO_GROUP
		group = groups.setdefault(rm_group, {"rm_group": rm_group, "lines": [], "suppliers": []})
		group["lines"].append(
			{
				"name": row.name,
				"idx": row.idx,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": row.qty,
				"uom": row.uom,
			}
		)
	for group in groups.values():
		group["suppliers"] = [supplier_card(s) for s in approved_suppliers(group["rm_group"])]
	ordered = sorted(groups.values(), key=lambda g: (g["rm_group"] == NO_GROUP, g["rm_group"]))
	return {"groups": ordered, "skipped": skipped}


@frappe.whitelist()
def get_rfq_plan(material_request):
	frappe.has_permission(RFQ, "create", throw=True)
	frappe.has_permission("Material Request", "read", doc=material_request, throw=True)
	return plan(material_request)


def _rfq_supplier(supplier):
	"""The supplier row, with its primary contact and e-mail so the standard RFQ mail can go out."""
	contact, email = frappe.db.get_value("Supplier", supplier, ["supplier_primary_contact", "email_id"])
	return {"supplier": supplier, "contact": contact, "email_id": email}


def _rfq_item(row):
	return {
		"item_code": row.item_code,
		"item_name": row.item_name,
		"description": row.description,
		"qty": row.qty,
		"uom": row.uom,
		"stock_uom": row.stock_uom,
		"conversion_factor": row.conversion_factor or 1,
		"warehouse": row.warehouse,
		"schedule_date": max(getdate(row.schedule_date or today()), getdate(today())),
		"project_name": row.project,
		"material_request": row.parent,
		"material_request_item": row.name,
	}


def create(material_request, groups):
	"""Make one draft RFQ per group. `groups`: [{rm_group, lines: [MR item names], suppliers: [names]}]."""
	mr = _open_request(material_request)
	rows = {row.name: row for row in mr.items}
	done = lines_on_open_rfq(mr.name)
	used = set()
	made = []
	for group in groups:
		lines = [rows[n] for n in group.get("lines") or [] if n in rows and n not in done and n not in used]
		suppliers = list(dict.fromkeys(s for s in group.get("suppliers") or [] if s))
		if not lines:
			continue
		if not suppliers:
			frappe.throw(
				_("Choose at least one supplier for {0}.").format(
					frappe.bold(group.get("rm_group") or _("items without an RM group"))
				)
			)
		for r in lines:
			if (rm_group_of(r.item_code) or NO_GROUP) != (group.get("rm_group") or NO_GROUP):
				frappe.throw(
					_("Row {0} {1} does not belong to RM group {2}.").format(
						r.idx, frappe.bold(r.item_code), frappe.bold(group.get("rm_group") or "-")
					)
				)
		for s in suppliers:
			if not frappe.db.exists("Supplier", s):
				frappe.throw(_("Supplier {0} not found.").format(frappe.bold(s)))
		rfq = frappe.get_doc(
			{
				"doctype": RFQ,
				"company": mr.company,
				"transaction_date": today(),
				"schedule_date": min(_rfq_item(r)["schedule_date"] for r in lines),
				"custom_rm_group": group.get("rm_group") or None,
				"custom_material_request": mr.name,
				"suppliers": [_rfq_supplier(s) for s in suppliers],
				"items": [_rfq_item(r) for r in lines],
			}
		)
		rfq.insert()
		used.update(r.name for r in lines)
		made.append(rfq.name)
	if not made:
		frappe.throw(_("Nothing to send: every line is already on an open RFQ."))
	return made


@frappe.whitelist()
def create_rfqs(material_request, groups):
	frappe.has_permission(RFQ, "create", throw=True)
	frappe.has_permission("Material Request", "read", doc=material_request, throw=True)
	if isinstance(groups, str):
		groups = json.loads(groups)
	return create(material_request, groups)


# C2-24: the RFQ e-mailed to each supplier carries the cover letter on the PEPL letterhead -------


class PEPLRequestforQuotation(RequestforQuotation):
	def send_email(self, data, sender, subject, message, attachments):
		from pepl_os.common.letterhead import swap_print_attachment

		return super().send_email(data, sender, subject, message, swap_print_attachment(self, attachments))
