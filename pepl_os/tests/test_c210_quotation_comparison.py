"""C2-10 - Quotation Comparison: L1, award rules, approval creates the Purchase Orders."""

from unittest.mock import patch

import frappe
from erpnext.buying.doctype.request_for_quotation.request_for_quotation import (
	make_supplier_quotation_from_rfq,
)
from frappe.utils import add_days, getdate, today

from pepl_os.pepl_purchase import quotation_comparison as qc
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

ITEM_A = "PEPL-T-QC-A"
ITEM_B = "PEPL-T-QC-B"
S1 = "PEPL T QC Supplier One"
S2 = "PEPL T QC Supplier Two"
REASON = "Supplier One delivers faster to the plant"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _supplier(name):
	if not frappe.db.exists("Supplier", name):
		make_supplier(name).insert(ignore_permissions=True)
	frappe.db.set_value("Supplier", name, "custom_approval_state", "Approved")
	return name


def _rfq():
	doc = frappe.get_doc(
		{
			"doctype": "Request for Quotation",
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"message_for_supplier": "Please quote",
			"suppliers": [{"supplier": S1}, {"supplier": S2}],
			"items": [
				{
					"item_code": code,
					"qty": qty,
					"uom": "Nos",
					"stock_uom": "Nos",
					"conversion_factor": 1,
					"schedule_date": add_days(today(), 20),
					"warehouse": _wh("Bought-Out Stores"),
				}
				for code, qty in ((ITEM_A, 10), (ITEM_B, 5))
			],
		}
	).insert(ignore_permissions=True)
	doc.submit()
	return doc


def _quote(rfq, supplier, rates):
	"""rates: {item_code: (rate, lead_time_days)}"""
	sq = make_supplier_quotation_from_rfq(rfq.name, for_supplier=supplier)
	for row in sq.items:
		row.rate, row.lead_time_days = rates[row.item_code]
	sq.insert(ignore_permissions=True)
	sq.submit()
	return sq


def _comparison():
	rfq = _rfq()
	_quote(rfq, S1, {ITEM_A: (100, 5), ITEM_B: (50, 10)})
	_quote(rfq, S2, {ITEM_A: (110, 3), ITEM_B: (45, 7)})
	return frappe.get_doc("PEPL Quotation Comparison", qc.make_comparison(rfq.name))


def _row(doc, item, supplier):
	return next(r for r in doc.rows if r.item_code == item and r.supplier == supplier)


def _approve(doc):
	doc.status = "Pending Approval"
	doc.save()
	doc.submit()
	return doc


class TestQuotationComparison(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(ITEM_A, st.BOUGHT_OUT)
		make_item(ITEM_B, st.BOUGHT_OUT)
		_supplier(S1)
		_supplier(S2)
		set_param("custom_enforce_override_reason", 1)

	def test_l1_marked_per_item(self):
		doc = _comparison()
		self.assertEqual(len(doc.rows), 4)
		self.assertTrue(_row(doc, ITEM_A, S1).is_l1)
		self.assertFalse(_row(doc, ITEM_A, S2).is_l1)
		self.assertTrue(_row(doc, ITEM_B, S2).is_l1)
		self.assertFalse(_row(doc, ITEM_B, S1).is_l1)

	def test_default_award_goes_to_l1(self):
		doc = _comparison()
		self.assertEqual(_row(doc, ITEM_A, S1).awarded_qty, 10)
		self.assertEqual(_row(doc, ITEM_A, S2).awarded_qty, 0)
		self.assertEqual(_row(doc, ITEM_B, S2).awarded_qty, 5)
		self.assertEqual(qc.award_problems(doc), [])

	def test_award_qty_must_match(self):
		doc = _comparison()
		_row(doc, ITEM_A, S1).awarded_qty = 8
		doc.status = "Pending Approval"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_non_l1_award_requires_reason(self):
		doc = _comparison()
		_row(doc, ITEM_B, S2).awarded_qty = 3
		_row(doc, ITEM_B, S1).awarded_qty = 2  # 60 / 40 split, S1 is not L1 for B
		doc.status = "Pending Approval"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		_row(doc, ITEM_B, S1).award_reason = REASON
		doc.save()
		self.assertEqual(doc.status, "Pending Approval")

	def test_submit_needs_send_for_approval(self):
		doc = _comparison()
		with self.assertRaises(frappe.ValidationError):
			doc.submit()

	def test_only_manager_can_approve(self):
		doc = _comparison()
		doc.status = "Pending Approval"
		doc.save()
		frappe.set_user(make_user("pepl.qc.buyer@example.com", ["Purchase User"]))
		try:
			with self.assertRaises(frappe.PermissionError):
				qc.before_submit(frappe.get_doc(doc.doctype, doc.name))
		finally:
			frappe.set_user("Administrator")

	def test_submit_creates_po_per_supplier_with_dates(self):
		doc = _comparison()
		_row(doc, ITEM_B, S2).awarded_qty = 3
		_row(doc, ITEM_B, S1).awarded_qty = 2
		_row(doc, ITEM_B, S1).award_reason = REASON
		with patch.object(qc, "attach_comparison_pdf", return_value=True):
			_approve(doc)
		doc.reload()
		self.assertEqual(doc.status, "Approved")
		orders = frappe.get_all(
			"Purchase Order", filters={qc.PO_LINK: doc.name}, fields=["name", "supplier", "docstatus"]
		)
		self.assertEqual(sorted(o.supplier for o in orders), [S1, S2])
		self.assertTrue(all(o.docstatus == 0 for o in orders))
		s1 = frappe.get_doc("Purchase Order", next(o.name for o in orders if o.supplier == S1))
		lines = {(r.item_code, r.qty, r.rate, getdate(r.schedule_date)) for r in s1.items}
		self.assertEqual(
			lines,
			{
				(ITEM_A, 10, 100, getdate(add_days(today(), 5))),
				(ITEM_B, 2, 50, getdate(add_days(today(), 10))),
			},
		)
		self.assertTrue(all(r.supplier_quotation for r in s1.items))
		self.assertTrue(
			frappe.db.exists(
				"PEPL Override Log",
				{"rule_code": qc.NON_L1_RULE, "reference_name": doc.name, "reason": REASON},
			)
		)
		self.assertEqual(sorted(doc.purchase_orders.split("\n")), sorted(o.name for o in orders))

	def test_comparison_pdf_attached_to_po(self):
		doc = _comparison()
		with patch.object(qc, "attach_comparison_pdf", return_value=True):
			_approve(doc)
		po = frappe.get_all("Purchase Order", filters={qc.PO_LINK: doc.name}, pluck="name")[0]
		fake = {"fname": f"{doc.name}.pdf", "fcontent": b"%PDF-1.4 test"}
		with patch("frappe.attach_print", return_value=fake):
			self.assertEqual(qc.attach_comparison_pdf(doc, po), "pdf")
		self.assertTrue(
			frappe.db.exists("File", {"attached_to_doctype": "Purchase Order", "attached_to_name": po})
		)

	def test_pdf_failure_does_not_block(self):
		doc = _comparison()
		with patch("frappe.attach_print", side_effect=RuntimeError("no pdf engine")):
			_approve(doc)
		self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "docstatus"), 1)
		for po in frappe.get_all("Purchase Order", filters={qc.PO_LINK: doc.name}, pluck="name"):
			files = frappe.get_all(
				"File",
				filters={"attached_to_doctype": "Purchase Order", "attached_to_name": po},
				pluck="file_name",
			)
			self.assertEqual(files, [f"{doc.name}.html"])  # printable page instead of the PDF

	def test_submitted_comparison_is_locked(self):
		doc = _comparison()
		with patch.object(qc, "attach_comparison_pdf", return_value=True):
			_approve(doc)
		with self.assertRaises(frappe.ValidationError):
			qc.reload_quotations(doc.name)
		with self.assertRaises(frappe.ValidationError):  # draft POs exist
			frappe.get_doc(doc.doctype, doc.name).cancel()

	def test_one_comparison_per_rfq(self):
		doc = _comparison()
		self.assertEqual(qc.make_comparison(doc.request_for_quotation), doc.name)
