"""C2-24 - Purchase and Stores print formats on the official PEPL letterhead."""

import shutil
import unittest
from io import BytesIO

import frappe
from frappe.utils import add_days, today

from pepl_os.common import letterhead as lh
from pepl_os.pepl_stores import scrap
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, set_param

ITEMS = [f"PEPL-T-PF-ITEM-{i}" for i in range(1, 6)]
S1 = "PEPL T PF Supplier One"
S2 = "PEPL T PF Supplier Two"
HAS_WKHTMLTOPDF = bool(shutil.which("wkhtmltopdf"))


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _supplier(name):
	if not frappe.db.exists("Supplier", name):
		make_supplier(name).insert(ignore_permissions=True)
	frappe.db.set_value("Supplier", name, "custom_approval_state", "Approved")
	return name


def _po():
	"""A draft five-line Purchase Order (drafts print too, marked DRAFT)."""
	return frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": S1,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 15),
			"items": [
				{
					"item_code": code,
					"qty": 10 * (i + 1),
					"rate": 125.5,
					"schedule_date": add_days(today(), 15),
					"warehouse": _wh("Bought-Out Stores"),
				}
				for i, code in enumerate(ITEMS)
			],
		}
	).insert(ignore_permissions=True)


def _rfq(suppliers, vendor=None):
	doc = frappe.get_doc(
		{
			"doctype": "Request for Quotation",
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"message_for_supplier": "Please quote your best rates.",
			"vendor": vendor,
			"suppliers": [{"supplier": s} for s in suppliers],
			"items": [
				{
					"item_code": ITEMS[0],
					"qty": 5,
					"uom": "Nos",
					"stock_uom": "Nos",
					"conversion_factor": 1,
					"schedule_date": add_days(today(), 20),
					"warehouse": _wh("Bought-Out Stores"),
				}
			],
		}
	)
	doc.name = "PEPL-T-PF-RFQ"
	return doc


def _two_page_pdf():
	"""Page 1 carries text (the letterhead itself), page 2 is blank."""
	from pypdf import PdfReader, PdfWriter

	writer = PdfWriter()
	with open(lh.letterhead_path(), "rb") as f:
		writer.add_page(PdfReader(BytesIO(f.read())).pages[0])
	writer.add_blank_page(width=595.92, height=841.92)
	out = BytesIO()
	writer.write(out)
	return out.getvalue()


def _pages(pdf):
	from pypdf import PdfReader

	return PdfReader(BytesIO(pdf)).pages


class TestPrintFormats(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		for code in ITEMS:
			make_item(code, st.BOUGHT_OUT, valuation_rate=10)
		_supplier(S1)
		_supplier(S2)

	def setUp(self):
		set_param("custom_po_approval_value_threshold", 0)

	def test_formats_installed_with_letterhead_margins(self):
		for name in lh.LETTERHEAD_FORMATS:
			with self.subTest(print_format=name):
				pf = frappe.get_doc("Print Format", name)
				self.assertEqual(pf.print_format_type, "Jinja")
				self.assertFalse(pf.disabled)
				self.assertIn("margin-top: 60mm; margin-bottom: 34mm", pf.html)
				self.assertIn("@media print { .print-format { margin: 0 !important", pf.html)
				self.assertIn(
					'<style class="hidden-pdf">', pf.html
				)  # the screen preview is left out of the PDF
				self.assertNotIn("<!DOCTYPE", pf.html)  # a template, not a rendered page
				self.assertTrue("{{ doc." in pf.html or "pepl_chase_lines" in pf.html)

	def test_po_and_rfq_formats_are_default(self):
		frappe.db.set_default(lh.DEFAULTS_FLAG, 0)  # as on the first migrate after v0.21.1
		lh.ensure_default_print_formats()
		self.assertEqual(frappe.get_meta("Purchase Order").default_print_format, "PEPL Purchase Order")
		self.assertEqual(
			frappe.get_meta("Request for Quotation").default_print_format, "PEPL RFQ Cover Letter"
		)
		self.assertEqual(
			frappe.get_meta("Request for Quotation").get_field("send_document_print").default, "1"
		)

	def test_print_formats_render_without_error(self):
		po = _po()
		weighment = frappe.get_doc(
			{
				"doctype": scrap.WEIGHMENT,
				"company": TEST_COMPANY,
				"weighment_date": today(),
				"source": scrap.PROCESS,
				"scrap_item": ITEMS[0],
				"gross_kg": 150,
				"tare_kg": 30,
				"net_kg": 120,
			}
		)
		weighment.name = "PEPL-T-PF-WEIGH"
		sale = frappe.get_doc(
			{
				"doctype": scrap.SALE,
				"company": TEST_COMPANY,
				"sale_date": today(),
				"vehicle_number": "WB 01 A 1234",
				"items": [{"scrap_item": ITEMS[0], "kg": 50, "rate": 30, "amount": 1500}],
			}
		)
		sale.name = "PEPL-T-PF-SALE"
		count = frappe.get_doc(
			{
				"doctype": "PEPL Cycle Count",
				"company": TEST_COMPANY,
				"warehouse": _wh("Consumables Stores"),
				"count_date": today(),
				"items": [{"item_code": ITEMS[0], "system_qty": 98765}],
			}
		)
		count.name = "PEPL-T-PF-COUNT"
		challan = frappe.get_doc(
			{"doctype": "Stock Entry", "company": TEST_COMPANY, "posting_date": today(), "items": []}
		)
		challan.name = "PEPL-T-PF-CHALLAN"
		cases = [
			("PEPL Purchase Order", po, [po.name, "PURCHASE ORDER", "DRAFT", ITEMS[4]]),
			("PEPL RFQ Cover Letter", _rfq([S1]), ["PEPL-T-PF-RFQ", S1, ITEMS[0]]),
			("PEPL Vendor Chase Letter", frappe.get_doc("Supplier", S1), [S1]),
			("PEPL Scrap Weighment Slip", weighment, ["SCRAP WEIGHMENT SLIP", "PEPL-T-PF-WEIGH"]),
			("PEPL Scrap Gate Pass", sale, ["SCRAP GATE PASS", "WB 01 A 1234"]),
			("PEPL Blind Count Sheet", count, ["BLIND COUNT SHEET", ITEMS[0]]),
			("PEPL CSM Return Challan", challan, ["PEPL-T-PF-CHALLAN"]),
		]
		self.assertEqual(sorted(c[0] for c in cases), sorted(lh.LETTERHEAD_FORMATS))
		for print_format, doc, expected in cases:
			with self.subTest(print_format=print_format):
				html = frappe.get_print(doc.doctype, doc.name, print_format, doc=doc, no_letterhead=1)
				for text in expected:
					self.assertIn(text, html)
		self.assertNotIn(
			"98765", frappe.get_print(count.doctype, count.name, "PEPL Blind Count Sheet", doc=count)
		)

	def test_rfq_letter_addressee(self):
		self.assertEqual(lh.pepl_rfq_letter(_rfq([S1])).supplier, S1)
		self.assertIsNone(lh.pepl_rfq_letter(_rfq([S1, S2])).supplier)  # "Our approved suppliers"
		self.assertEqual(lh.pepl_rfq_letter(_rfq([S1, S2], vendor=S2)).supplier, S2)  # the one being sent to
		self.assertIsNone(lh.pepl_rfq_letter(_rfq([S1, S2], vendor="Someone Else")).supplier)

	def test_stamp_drops_blank_trailing_page(self):
		self.assertTrue(lh.letterhead_path().endswith("PEPL_Letterhead_Plain.pdf"))
		pages = _pages(lh.stamp(_two_page_pdf()))
		self.assertEqual(len(pages), 1)
		self.assertIn("PARASRAMKA", pages[0].extract_text())

	def test_non_pepl_attachment_left_alone(self):
		po = _po()
		other = {"fname": "Something-else.pdf", "fcontent": b"x"}
		self.assertEqual(lh.swap_print_attachment(po, [other, "FILE-0001"]), [other, "FILE-0001"])

	@unittest.skipUnless(HAS_WKHTMLTOPDF, "wkhtmltopdf is not installed here")
	def test_five_line_po_is_one_page_on_the_letterhead(self):
		po = _po()
		pages = _pages(lh.render("Purchase Order", po.name, "PEPL Purchase Order"))
		self.assertEqual(len(pages), 1)
		text = pages[0].extract_text()
		self.assertIn(po.name, text)
		self.assertIn("PARASRAMKA", text)  # the letterhead is behind the content
		swapped = lh.swap_print_attachment(po, [{"fname": f"{po.name}.pdf", "fcontent": b"plain"}])
		self.assertEqual(swapped[0]["fname"], lh.file_name(po.name))
		self.assertTrue(swapped[0]["fcontent"].startswith(b"%PDF"))

	@unittest.skipUnless(HAS_WKHTMLTOPDF, "wkhtmltopdf is not installed here")
	def test_pdf_button_only_changes_pepl_formats(self):
		po = _po()
		lh.download_pdf("Purchase Order", po.name, format="PEPL Purchase Order")
		self.assertIn("PARASRAMKA", _pages(frappe.local.response.filecontent)[0].extract_text())
		lh.download_pdf("Purchase Order", po.name, format="Standard")
		self.assertNotIn("PARASRAMKA", _pages(frappe.local.response.filecontent)[0].extract_text() or "")

	def test_print_button_knows_the_letterhead_formats(self):
		from pepl_os.boot import boot_session

		bootinfo = frappe._dict()
		boot_session(bootinfo)
		self.assertEqual(sorted(bootinfo.pepl_letterhead_formats), sorted(lh.LETTERHEAD_FORMATS))
