"""C3a-B5 - LD-exposure report: late days x contractual LD rate per open Sales Order, now and in the look-ahead."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_production import ld, ld_exposure
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, TEST_CUSTOMER, make_delivery_note, make_item, test_warehouse
from pepl_os.tests.utils import PEPLTestCase, set_param

PART = "T-B5-BO-PART"  # bought-out, 100 a piece
SYSTEM_PARAMETERS = "PEPL System Parameters"


def _order(sector="Railways", qty=10, days_ago=30, due_in=-10, **terms):
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": TEST_CUSTOMER,
			"company": TEST_COMPANY,
			"transaction_date": add_days(today(), -days_ago),
			"delivery_date": add_days(today(), due_in),
			"custom_sector": sector,
			"items": [
				{
					"item_code": PART,
					"qty": qty,
					"rate": 100,
					"warehouse": test_warehouse("Bought-Out Stores"),
					"delivery_date": add_days(today(), due_in),
				}
			],
			**terms,
		}
	).insert(ignore_permissions=True)
	so.submit()
	return so


class TestLDExposure(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(PART, st.BOUGHT_OUT, valuation_rate=50)
		receipt = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"purpose": "Material Receipt",
				"company": TEST_COMPANY,
				"set_posting_time": 1,
				"posting_date": add_days(today(), -60),
				"items": [
					{
						"item_code": PART,
						"qty": 500,
						"t_warehouse": test_warehouse("Bought-Out Stores"),
						"basic_rate": 50,
					}
				],
			}
		).insert(ignore_permissions=True)
		receipt.submit()

	def setUp(self):
		set_param(ld.DEFAULT_SECTORS_FIELD, "Railways\nDefence")
		set_param(ld.DEFAULT_RATE_FIELD, 0.5)
		set_param(ld.DEFAULT_PERIOD_FIELD, ld.WEEK)
		set_param(ld.DEFAULT_CAP_FIELD, 10)
		set_param(ld_exposure.LOOK_AHEAD_FIELD, 7)

	def _one(self, so, **filters):
		orders, lines = ld_exposure.order_rows({"sales_order": so.name, **filters})
		return (orders[0] if orders else None), lines

	def test_late_order_now_and_in_seven_days(self):
		so = _order(due_in=-10)  # 10 days late = 2 weeks (part of a week counts)
		row, lines = self._one(so)
		self.assertEqual(
			(row["ld_now"], row["ld_ahead"], row["ld_added"]), (10, 15, 5)
		)  # 17 days in 7 = 3 weeks
		self.assertEqual((row["days_late"], row["late_lines"], row["pending_qty"]), (10, 1, 10))
		self.assertEqual((row["cap_amount"], row["cap_used"], row["colour"]), (100, 10, "red"))
		self.assertEqual(row["terms"], "0.5% per week, cap 10%")  # Regression (CI #52): never "cap 10.0%"
		self.assertEqual(len(lines), 1)
		self.assertEqual((lines[0]["days_late"], lines[0]["late_qty"], lines[0]["ld_now"]), (10, 10, 10))

	def test_ld_that_starts_within_the_look_ahead_is_orange(self):
		so = _order(days_ago=5, due_in=3)  # due in 3 days: late 4 days in 7 = 1 week
		row, lines = self._one(so)
		self.assertEqual((row["ld_now"], row["ld_ahead"], row["colour"]), (0, 5, "orange"))
		self.assertEqual(lines[0]["colour"], "orange")
		set_param(ld_exposure.LOOK_AHEAD_FIELD, 2)  # not late within 2 days
		row, lines = self._one(so)
		self.assertEqual((row["ld_ahead"], row["colour"]), (0, "green"))

	def test_on_time_order_is_green_and_has_no_lines(self):
		row, lines = self._one(_order(days_ago=5, due_in=30))
		self.assertEqual((row["ld_now"], row["ld_ahead"], row["colour"]), (0, 0, "green"))
		self.assertEqual(lines, [])

	def test_orders_without_ld_only_when_asked(self):
		so = _order("Private", due_in=-10)
		self.assertIsNone(self._one(so)[0])
		row, _lines = self._one(so, only_ld=0)
		self.assertEqual((row["terms"], row["ld_now"], row["colour"]), ("no LD clause", 0, "gray"))

	def test_completed_orders_are_left_out(self):
		so = _order(days_ago=5, due_in=3)
		make_delivery_note(so.name, {PART: 10}, submit=True)
		self.assertIsNone(self._one(so)[0])

	def test_delivered_late_still_counts_while_the_order_is_open(self):
		so = _order(due_in=-10)
		make_delivery_note(so.name, {PART: 4}, submit=True)  # 4 delivered today (late), 6 still pending
		row, _lines = self._one(so)
		self.assertEqual((row["ld_now"], row["pending_qty"]), (10, 6))  # 400 + 600, each 2 weeks: 4 + 6
		self.assertEqual(row["ld_ahead"], 13)  # delivered part stays 4; pending 600 x 3 weeks = 9

	def test_summary_and_report(self):
		from pepl_os.pepl_production.report.pepl_ld_exposure import pepl_ld_exposure as report

		so = _order(due_in=-10)
		columns, data, message = report.execute({"sales_order": so.name})
		self.assertIn("ld_ahead", [c["fieldname"] for c in columns])
		self.assertIn("LD in 7 Days", [c["label"] for c in columns])
		self.assertEqual(len(data), 1)
		self.assertIn("on 1 order(s)", message)
		self.assertIn("in 7 days", message)
		columns, data, message = report.execute({"sales_order": so.name, "show": "Lines"})
		self.assertIn("item_code", [c["fieldname"] for c in columns])
		self.assertEqual(data[0]["item_code"], PART)
		self.assertTrue(frappe.db.exists("Report", "PEPL LD Exposure"))

	def test_look_ahead_setting(self):
		doc = frappe.get_doc(SYSTEM_PARAMETERS)
		for bad in (-1, 400):
			doc.set(ld_exposure.LOOK_AHEAD_FIELD, bad)
			with self.assertRaisesRegex(frappe.ValidationError, "LD: Look-Ahead Days"):
				validate_production_params(doc)
		field = frappe.get_meta(SYSTEM_PARAMETERS).get_field(ld_exposure.LOOK_AHEAD_FIELD)
		self.assertEqual((field.fieldtype, str(field.default)), ("Int", "7"))
