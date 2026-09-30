"""C2-10 - Quotation Comparison: every quotation for one RFQ side by side, then the Purchase Orders.

Flow (simple for the buyer):
  1. On a submitted RFQ press "Quotation Comparison". The comparison is created
     with one row per supplier per RFQ line, taken from the submitted Supplier
     Quotations. The lowest rate of each line is marked L1 and gets the whole
     quantity by default.
  2. The buyer may split or move quantities. Any quantity given to a supplier
     who is not L1 needs a reason (when "enforce override reason" is on).
  3. "Send for Approval", then the Purchase Manager submits (= approves).
     Approval creates one draft Purchase Order per supplier, each line promised
     by today + the quoted lead time, with the comparison PDF attached.
     Every non-L1 award is written to the Audit Trail (rule PUR-NON-L1-AWARD).
  4. A submitted comparison is locked.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, fmt_money, getdate, today

from pepl_os.common import params
from pepl_os.common.overrides import MIN_REASON_LENGTH, log_override

DOCTYPE = "PEPL Quotation Comparison"
RFQ = "Request for Quotation"
PO_LINK = "custom_quotation_comparison"
NON_L1_RULE = "PUR-NON-L1-AWARD"
APPROVER_ROLES = ("Purchase Manager", "System Manager")
QTY_PRECISION = 3


# Loading quotations ----------------------------------------------------------


def latest_quotation_lines(rfq):
	"""Submitted Supplier Quotation lines against this RFQ; per supplier and RFQ line only the latest."""
	rows = frappe.db.sql(
		"""
		select sqi.name as sq_item, sqi.parent as supplier_quotation, sq.supplier, sq.currency,
			sq.conversion_rate, sq.transaction_date, sq.creation,
			sqi.request_for_quotation_item as rfq_item, sqi.item_code, sqi.rate, sqi.base_rate,
			sqi.lead_time_days, sqi.uom, sqi.conversion_factor
		from `tabSupplier Quotation Item` sqi
		join `tabSupplier Quotation` sq on sq.name = sqi.parent
		where sqi.request_for_quotation = %s and sq.docstatus = 1
		order by sq.transaction_date desc, sq.creation desc
		""",
		rfq,
		as_dict=True,
	)
	seen, latest = set(), []
	for r in rows:
		key = (r.supplier, r.rfq_item)
		if key in seen:
			continue
		seen.add(key)
		latest.append(r)
	return latest


def last_po_rates(item_code, supplier, exclude_comparison=None, limit=3):
	"""The last three submitted PO rates (company currency) for this item from this supplier, 12 months."""
	rows = frappe.db.sql(
		"""
		select poi.base_rate, po.transaction_date
		from `tabPurchase Order Item` poi
		join `tabPurchase Order` po on po.name = poi.parent
		where po.docstatus = 1 and po.supplier = %(supplier)s and poi.item_code = %(item)s
			and po.transaction_date >= %(since)s
			and ifnull(po.custom_quotation_comparison, '') != %(exclude)s
		order by po.transaction_date desc, po.creation desc
		limit %(limit)s
		""",
		{
			"supplier": supplier,
			"item": item_code,
			"since": add_days(today(), -365),
			"exclude": exclude_comparison or "__none__",
			"limit": limit,
		},
		as_dict=True,
	)
	return rows


def _rates_text(rates):
	return ", ".join(f"{flt(r.base_rate):.2f} ({r.transaction_date})" for r in rates)


def promised_date(lead_time_days, required_by):
	"""Today + quoted lead time; without a lead time, the date the line is needed by."""
	if cint(lead_time_days) > 0:
		return add_days(today(), cint(lead_time_days))
	return max(getdate(required_by or today()), getdate(today()))


def load_rows(doc):
	"""Fill the rows from the submitted Supplier Quotations. Returns the number of rows."""
	rfq = frappe.get_doc(RFQ, doc.request_for_quotation)
	lines = {r.name: r for r in rfq.items}
	doc.set("rows", [])
	for q in latest_quotation_lines(rfq.name):
		line = lines.get(q.rfq_item)
		if not line:
			continue
		supplier = frappe.db.get_value(
			"Supplier",
			q.supplier,
			["payment_terms", "custom_delivery_score", "custom_quality_score"],
			as_dict=True,
		)
		doc.append(
			"rows",
			{
				"rfq_item": line.name,
				"line": line.idx,
				"item_code": line.item_code,
				"item_name": line.item_name,
				"qty_required": line.qty,
				"uom": line.uom,
				"supplier": q.supplier,
				"supplier_quotation": q.supplier_quotation,
				"sq_item": q.sq_item,
				"currency": q.currency,
				"rate": q.rate,
				"base_rate": q.base_rate,
				"lead_time_days": q.lead_time_days,
				"promised_date": promised_date(q.lead_time_days, line.schedule_date),
				"payment_terms": supplier.payment_terms,
				"last_rates": _rates_text(last_po_rates(line.item_code, q.supplier, doc.name)),
				"delivery_score": supplier.custom_delivery_score,
				"quality_score": supplier.custom_quality_score,
				"warehouse": line.warehouse,
				"material_request": line.material_request,
				"material_request_item": line.material_request_item,
				"awarded_qty": 0,
			},
		)
	doc.rows.sort(key=lambda r: (r.line, flt(r.base_rate), r.supplier))
	for i, r in enumerate(doc.rows, start=1):
		r.idx = i
	mark_l1(doc)
	award_to_l1(doc)
	return len(doc.rows)


def _by_line(doc):
	lines = {}
	for r in doc.rows:
		lines.setdefault(r.rfq_item, []).append(r)
	return lines


def mark_l1(doc):
	"""L1 = the lowest rate (company currency) of each RFQ line; ties are all L1."""
	for rows in _by_line(doc).values():
		priced = [r for r in rows if flt(r.base_rate) > 0]
		lowest = min((flt(r.base_rate) for r in priced), default=None)
		for r in rows:
			r.is_l1 = 1 if lowest is not None and flt(r.base_rate) > 0 and flt(r.base_rate) == lowest else 0


def award_to_l1(doc):
	"""Default award: the whole quantity to the L1 with the shortest lead time."""
	for rows in _by_line(doc).values():
		l1 = sorted((r for r in rows if r.is_l1), key=lambda r: (cint(r.lead_time_days), r.idx))
		for r in rows:
			r.awarded_qty = 0
		if l1:
			l1[0].awarded_qty = l1[0].qty_required


# Rules -----------------------------------------------------------------------


def reason_required():
	return params.is_enabled("custom_enforce_override_reason", 1)


def non_l1_awards(doc):
	return [r for r in doc.rows if flt(r.awarded_qty) > 0 and not r.is_l1]


def award_problems(doc):
	"""Everything that stops approval, as plain sentences."""
	problems = []
	if not doc.rows:
		problems.append(
			_("No quotations loaded. Submit the Supplier Quotations, then press Load Quotations.")
		)
	for rows in _by_line(doc).values():
		first = rows[0]
		awarded = flt(sum(flt(r.awarded_qty) for r in rows), QTY_PRECISION)
		if awarded != flt(first.qty_required, QTY_PRECISION):
			problems.append(
				_("Line {0} {1}: awarded {2}, required {3}.").format(
					first.line, first.item_code, awarded, flt(first.qty_required, QTY_PRECISION)
				)
			)
	for r in doc.rows:
		if flt(r.awarded_qty) > 0 and flt(r.base_rate) <= 0:
			problems.append(
				_("Row {0}: {1} has no rate, so nothing can be awarded to it.").format(r.idx, r.supplier)
			)
	if reason_required():
		for r in non_l1_awards(doc):
			if len((r.award_reason or "").strip()) < MIN_REASON_LENGTH:
				problems.append(
					_(
						"Row {0}: {1} is not L1 for line {2}. Give a reason of at least {3} characters."
					).format(r.idx, r.supplier, r.line, MIN_REASON_LENGTH)
				)
	return problems


def summary_lines(doc):
	"""[(text, colour)] for the panel and the Summary field."""
	out = []
	for rows in _by_line(doc).values():
		first = rows[0]
		l1 = [r for r in rows if r.is_l1]
		if not l1:
			out.append((_("Line {0} {1}: no priced quotation.").format(first.line, first.item_code), "red"))
			continue
		l1_rate = flt(l1[0].base_rate)
		chosen_value = sum(flt(r.awarded_qty) * flt(r.base_rate) for r in rows)
		l1_value = flt(first.qty_required) * l1_rate
		extra = chosen_value - l1_value
		text = _("Line {0} {1}: L1 {2} at {3}").format(
			first.line, first.item_code, l1[0].supplier, fmt_money(l1_rate, currency=_company_currency(doc))
		)
		if extra > 0.005:
			text += _("; chosen costs {0} more than L1").format(
				fmt_money(extra, currency=_company_currency(doc))
			)
		last = last_po_rates(first.item_code, l1[0].supplier, doc.name, limit=1)
		if last and flt(last[0].base_rate):
			change = (l1_rate - flt(last[0].base_rate)) / flt(last[0].base_rate) * 100
			text += _("; L1 vs its last PO rate {0:+.1f}%").format(change)
		out.append((text, "orange" if extra > 0.005 else "green"))
	for p in award_problems(doc):
		out.append((p, "red"))
	return out


def _company_currency(doc):
	return frappe.get_cached_value("Company", doc.company, "default_currency") if doc.company else None


def _check_rfq(doc):
	status = frappe.db.get_value(RFQ, doc.request_for_quotation, "docstatus")
	if status != 1:
		frappe.throw(_("Submit the Request for Quotation first."))


# Document events -------------------------------------------------------------


def before_insert(doc):
	_check_rfq(doc)
	doc.prepared_by = frappe.session.user
	doc.status = "Draft"
	if not doc.rows:
		load_rows(doc)


def validate(doc):
	_check_rfq(doc)
	for r in doc.rows:
		if flt(r.awarded_qty) < 0:
			frappe.throw(_("Row {0}: awarded quantity cannot be negative.").format(r.idx))
	mark_l1(doc)
	if doc.docstatus == 0 and doc.status == "Pending Approval":
		problems = award_problems(doc)
		if problems:
			frappe.throw("<br>".join(problems), title=_("Not ready for approval"))
	doc.summary = "\n".join(text for text, _colour in summary_lines(doc))


def before_submit(doc):
	if not set(APPROVER_ROLES) & set(frappe.get_roles()):
		frappe.throw(
			_("Only the Purchase Manager can approve a Quotation Comparison."), frappe.PermissionError
		)
	if doc.status != "Pending Approval":
		frappe.throw(_("Press Send for Approval first."), title=_("Not sent for approval"))
	problems = award_problems(doc)
	if problems:
		frappe.throw("<br>".join(problems), title=_("Cannot approve"))
	doc.status = "Approved"
	doc.approved_by = frappe.session.user
	doc.approval_date = today()


def on_submit(doc):
	for r in non_l1_awards(doc):
		if (r.award_reason or "").strip():
			log_override(
				NON_L1_RULE,
				DOCTYPE,
				doc.name,
				_("Line {0} {1}: {2} awarded to {3}, not L1.").format(
					r.line, r.item_code, r.awarded_qty, r.supplier
				),
				r.award_reason,
			)
	orders = create_purchase_orders(doc)
	doc.db_set("purchase_orders", "\n".join(orders))
	for name in orders:
		attach_comparison_pdf(doc, name)
	frappe.msgprint(
		_("Draft Purchase Orders created: {0}").format(
			", ".join(frappe.utils.get_link_to_form("Purchase Order", n) for n in orders)
		),
		indicator="green",
		alert=True,
	)


def linked_orders(doc):
	return frappe.get_all(
		"Purchase Order", filters={PO_LINK: doc.name, "docstatus": ["<", 2]}, fields=["name", "docstatus"]
	)


def before_cancel(doc):
	open_orders = linked_orders(doc)
	if open_orders:
		frappe.throw(
			_("Cancel or delete these Purchase Orders first: {0}").format(
				", ".join(o.name for o in open_orders)
			),
			title=_("Purchase Orders exist"),
		)


def on_cancel(doc):
	doc.db_set("status", "Cancelled")


# Purchase Orders ---------------------------------------------------------------


def create_purchase_orders(doc):
	"""One draft Purchase Order per supplier (and currency) with the awarded lines."""
	groups = {}
	for r in doc.rows:
		if flt(r.awarded_qty) > 0:
			groups.setdefault((r.supplier, r.currency), []).append(r)
	made = []
	for (supplier, currency), rows in groups.items():
		sq = frappe.db.get_value(
			"Supplier Quotation", rows[0].supplier_quotation, ["conversion_rate"], as_dict=True
		)
		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": supplier,
				"company": doc.company,
				"transaction_date": today(),
				"currency": currency,
				"conversion_rate": flt(sq.conversion_rate) or 1,
				"schedule_date": min(getdate(r.promised_date) for r in rows),
				PO_LINK: doc.name,
				"items": [_po_item(r) for r in rows],
			}
		)
		po.flags.ignore_permissions = True  # approved by the Purchase Manager on the comparison
		po.insert()
		made.append(po.name)
	return made


def _po_item(r):
	sqi = (
		frappe.db.get_value(
			"Supplier Quotation Item",
			r.sq_item,
			["uom", "conversion_factor", "item_name", "description", "project"],
			as_dict=True,
		)
		or frappe._dict()
	)
	mr_so = (
		frappe.db.get_value("Material Request Item", r.material_request_item, "sales_order")
		if r.material_request_item
		else None
	)
	return {
		"item_code": r.item_code,
		"item_name": sqi.item_name or r.item_name,
		"description": sqi.description,
		"qty": r.awarded_qty,
		"uom": sqi.uom or r.uom,
		"conversion_factor": flt(sqi.conversion_factor) or 1,
		"rate": r.rate,
		"schedule_date": r.promised_date,
		"warehouse": r.warehouse,
		"material_request": r.material_request,
		"material_request_item": r.material_request_item,
		"supplier_quotation": r.supplier_quotation,
		"supplier_quotation_item": r.sq_item,
		"sales_order": mr_so,
		"project": sqi.project,
	}


def _attach(purchase_order, file_name, content):
	frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"content": content,
			"attached_to_doctype": "Purchase Order",
			"attached_to_name": purchase_order,
			"is_private": 1,
		}
	).insert(ignore_permissions=True)


def attach_comparison_pdf(doc, purchase_order):
	"""Attach the comparison to the PO: as PDF, or as a printable HTML page when no PDF can be made.

	Never blocks the approval. Returns "pdf", "html" or None.
	"""
	try:
		pdf = frappe.attach_print(DOCTYPE, doc.name, file_name=doc.name, doc=doc)
		_attach(purchase_order, pdf["fname"], pdf["fcontent"])
		return "pdf" if pdf["fname"].endswith(".pdf") else "html"
	except Exception:
		frappe.log_error(title=f"PEPL: comparison PDF not made for {purchase_order}")
	try:
		html = frappe.get_print(DOCTYPE, doc.name, doc=doc, no_letterhead=1)
		_attach(purchase_order, f"{doc.name}.html", html.encode("utf-8"))
		frappe.msgprint(
			_(
				"No PDF could be made (see the Error Log), so the comparison was attached to {0} as a printable page."
			).format(purchase_order),
			indicator="orange",
			alert=True,
		)
		return "html"
	except Exception:
		frappe.log_error(title=f"PEPL: comparison not attached to {purchase_order}")
		frappe.msgprint(
			_("The comparison could not be attached to {0}. See the Error Log.").format(purchase_order),
			indicator="orange",
			alert=True,
		)
		return None


# Buttons -----------------------------------------------------------------------


@frappe.whitelist()
def make_comparison(request_for_quotation):
	"""RFQ button: open the existing comparison for this RFQ, or create it."""
	frappe.has_permission(DOCTYPE, "create", throw=True)
	existing = frappe.db.get_value(
		DOCTYPE, {"request_for_quotation": request_for_quotation, "docstatus": ["<", 2]}, "name"
	)
	if existing:
		return existing
	doc = frappe.get_doc({"doctype": DOCTYPE, "request_for_quotation": request_for_quotation})
	doc.insert()
	return doc.name


def _draft(name):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("This comparison is approved and locked."))
	return doc


@frappe.whitelist()
def reload_quotations(name):
	"""Load Quotations button: read the Supplier Quotations again (awards go back to L1)."""
	doc = _draft(name)
	count = load_rows(doc)
	doc.status = "Draft"
	doc.save()
	return count


@frappe.whitelist()
def send_for_approval(name):
	doc = _draft(name)
	doc.status = "Pending Approval"
	doc.save()  # validate refuses with the list of problems
	return doc.status


@frappe.whitelist()
def back_to_draft(name):
	doc = _draft(name)
	doc.status = "Draft"
	doc.save()
	return doc.status


@frappe.whitelist()
def get_panel(name):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	return [{"text": t, "colour": c} for t, c in summary_lines(doc)]
