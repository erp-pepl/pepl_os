"""C3a-P3 - Job-Work outstanding panel on the job worker (Supplier) and on the Stock Entry."""

import frappe
from frappe.utils import add_days, formatdate, today

from pepl_os.pepl_production import job_work as jw
from pepl_os.pepl_production import job_work_panel as jwp
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier, test_warehouse
from pepl_os.tests.utils import PEPLTestCase, set_param

WORKER = "T-JWP Heat Treaters"
OTHER = "T-JWP Ordinary Supplier"
STORE_NAME = "T-JWP Heat Treaters Store"
ROD = "T-JWP-ROD"
PIN = "T-JWP-PIN"


def _entry(rows, days_ago=0, movement=None, purpose="Material Transfer"):
	doc = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": purpose,
			"purpose": purpose,
			"company": TEST_COMPANY,
			"set_posting_time": 1,
			"posting_date": add_days(today(), -days_ago),
			"items": [
				{
					"item_code": item,
					"qty": qty,
					"s_warehouse": source,
					"t_warehouse": target,
					"basic_rate": 10,
				}
				for item, qty, source, target in rows
			],
		}
	)
	if movement:
		doc.set(jw.MOVEMENT_FIELD, movement)
	return doc


def _texts(rows):
	return " | ".join(r["text"] for r in rows)


class TestJobWorkPanel(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		for name in (WORKER, OTHER):
			if not frappe.db.exists("Supplier", name):
				make_supplier(name).insert(ignore_permissions=True)
		parent = frappe.db.get_value("Warehouse", test_warehouse("RM Stores"), "parent_warehouse")
		cls.store = frappe.db.get_value("Warehouse", {"warehouse_name": STORE_NAME, "company": TEST_COMPANY})
		if not cls.store:
			cls.store = (
				frappe.get_doc(
					{
						"doctype": "Warehouse",
						"warehouse_name": STORE_NAME,
						"company": TEST_COMPANY,
						"parent_warehouse": parent,
						jw.JOB_WORKER_FIELD: WORKER,
					}
				)
				.insert(ignore_permissions=True)
				.name
			)
		cls.rm = test_warehouse("RM Stores")
		for code in (ROD, PIN):
			make_item(code, st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10)
		receipt = _entry(
			[(ROD, 500, None, cls.rm), (PIN, 500, None, cls.rm)], 400, purpose="Material Receipt"
		)
		receipt.insert(ignore_permissions=True)
		receipt.submit()

	def setUp(self):
		set_param(jw.RETURN_DAYS_FIELD, 30)
		set_param(jw.GST_WARNING_FIELD, 30)

	def _send(self, item, qty, days_ago):
		doc = _entry([(item, qty, self.rm, self.store)], days_ago)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def _back(self, item, qty, days_ago, movement=jw.RECEIVED, submit=True):
		doc = _entry([(item, qty, self.store, self.rm)], days_ago, movement)
		doc.insert(ignore_permissions=True)
		if submit:
			doc.submit()
		return doc

	# ---- Supplier ----
	def test_a_supplier_that_is_not_a_job_worker_gets_no_panel(self):
		self.assertIsNone(jwp.supplier_rows(OTHER))
		self.assertFalse(jwp.get_supplier_job_work_panel(OTHER)["job_worker"])

	def test_nothing_outside(self):
		rows = jwp.supplier_rows(WORKER)
		self.assertEqual((len(rows), rows[0]["colour"]), (1, "green"))
		self.assertIn("Nothing outside", rows[0]["text"])

	def test_within_the_return_days(self):
		self._send(ROD, 40, 10)
		self._back(ROD, 15, 2)
		rows = jwp.supplier_rows(WORKER)
		self.assertIn("1 item(s) outside", rows[0]["text"])
		self.assertEqual(rows[0]["colour"], "green")
		line = rows[1]
		self.assertIn(
			f"{ROD}: 25 Nos outside since {formatdate(add_days(today(), -10))} (10 days)", line["text"]
		)
		self.assertIn(f"due back by {formatdate(add_days(today(), 20))}", line["text"])
		self.assertEqual(line["colour"], "green")

	def test_sent_today(self):
		self._send(ROD, 5, 0)
		self.assertIn("(sent today)", _texts(jwp.supplier_rows(WORKER)))

	def test_overdue_comes_first_and_colours_the_headline(self):
		self._send(ROD, 10, 5)
		self._send(PIN, 10, 40)
		rows = jwp.supplier_rows(WORKER)
		self.assertEqual(rows[0]["colour"], "orange")
		self.assertIn("1 overdue or near the GST limit", rows[0]["text"])
		self.assertTrue(rows[1]["text"].startswith(PIN))
		self.assertIn("10 days overdue", rows[1]["text"])
		self.assertEqual(rows[1]["colour"], "orange")

	def test_gst_limit_near_and_passed(self):
		self._send(PIN, 10, 340)
		line = jwp.supplier_rows(WORKER)[1]
		self.assertIn("GST one-year limit on", line["text"])
		self.assertIn("25 days left", line["text"])
		self.assertEqual(line["colour"], "red")
		self._send(ROD, 10, 370)
		rows = jwp.supplier_rows(WORKER)
		self.assertTrue(rows[1]["text"].startswith(ROD))
		self.assertIn("GST one-year limit passed on", rows[1]["text"])

	def test_value_in_the_headline(self):
		self._send(ROD, 30, 3)
		self.assertIn("300", jwp.supplier_rows(WORKER)[0]["text"])  # 30 x valuation 10

	# ---- Stock Entry ----
	def test_entry_not_touching_a_job_worker_has_no_panel(self):
		doc = _entry([(ROD, 2, self.rm, test_warehouse("WIP Main Workshop"))])
		doc.insert(ignore_permissions=True)
		self.assertEqual(jwp.stock_entry_rows(doc), [])

	def test_entry_bringing_back_shows_what_is_outside_before_it(self):
		self._send(ROD, 20, 12)
		self._send(PIN, 20, 12)
		draft = self._back(ROD, 5, 0, submit=False)
		rows = jwp.stock_entry_rows(draft)
		text = _texts(rows)
		self.assertIn(f"At job worker {WORKER} now (before this entry): 1 of these item(s) outside", text)
		self.assertIn(f"{ROD}: 20 Nos outside", text)
		self.assertNotIn(PIN, text)  # only the items of the entry
		self.assertNotIn("but only", text)

	def test_entry_bringing_back_more_than_is_outside_is_flagged(self):
		self._send(ROD, 4, 12)
		draft = self._back(ROD, 4, 0, submit=False)
		draft.items[0].qty = 6
		draft.items[0].transfer_qty = 6
		rows = jwp.stock_entry_rows(draft)
		flag = [r for r in rows if "but only" in r["text"]]
		self.assertEqual(len(flag), 1)
		self.assertIn("brings back 6 Nos", flag[0]["text"])
		self.assertIn("only 4 is outside", flag[0]["text"])
		self.assertEqual(flag[0]["colour"], "red")

	def test_submitted_entry_shows_after(self):
		self._send(ROD, 20, 12)
		done = self._back(ROD, 20, 0)
		self.assertIn(
			"(after this entry): none of these items is outside", _texts(jwp.stock_entry_rows(done))
		)

	# ---- set-up ----
	def test_form_apis(self):
		self._send(ROD, 5, 1)
		self.assertTrue(jwp.get_supplier_job_work_panel(WORKER)["rows"])
		sent = self._send(PIN, 5, 1)
		self.assertTrue(jwp.get_stock_entry_job_work_panel(sent.name)["rows"])

	def test_panels_hooked_on_the_forms(self):
		hooks = frappe.get_hooks("doctype_js")
		self.assertIn("public/js/supplier_payments.js", str(hooks.get("Supplier")))
		self.assertIn("public/js/stock_entry.js", str(hooks.get("Stock Entry")))
