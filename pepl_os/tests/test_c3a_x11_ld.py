"""C3a-X11 - The contractual LD clause on the Sales Order, and LD for late delivery."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_production import ld
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, TEST_CUSTOMER, make_delivery_note, make_item, test_warehouse
from pepl_os.tests.utils import PEPLTestCase, set_param

PART = "T-LD-BO-PART"  # bought-out, 100 a piece (no Job Order is drafted for it)


def _order(sector="Railways", qty=10, days_ago=0, due_in=10, submit=True, **terms):
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
	if submit:
		so.submit()
	return so


class TestLiquidatedDamages(PEPLTestCase):
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

	# ---- the clause ----
	def test_railways_order_starts_with_the_standard_clause(self):
		so = _order("Railways", submit=False)
		self.assertEqual(
			(so.get(ld.APPLICABLE), so.get(ld.RATE), so.get(ld.PERIOD), so.get(ld.CAP)), (1, 0.5, ld.WEEK, 10)
		)
		self.assertEqual(so.get(ld.BASIS), ld.LATE_ITEMS)

	def test_private_order_starts_without_ld(self):
		so = _order("Private", submit=False)
		self.assertFalse(so.get(ld.APPLICABLE))

	def test_terms_entered_by_hand_are_kept(self):
		so = _order("Defence", submit=False, **{ld.APPLICABLE: 1, ld.RATE: 1, ld.CAP: 5, ld.PERIOD: ld.DAY})
		self.assertEqual((so.get(ld.RATE), so.get(ld.CAP), so.get(ld.PERIOD)), (1, 5, ld.DAY))

	def test_an_incomplete_clause_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "LD Rate"):
			_order("Private", submit=False, **{ld.APPLICABLE: 1, ld.RATE: 0, ld.CAP: 10})
		with self.assertRaisesRegex(frappe.ValidationError, "LD Cap"):
			_order("Private", submit=False, **{ld.APPLICABLE: 1, ld.RATE: 0.5, ld.CAP: 0})

	def test_the_clause_is_fixed_once_submitted(self):
		so = _order("Railways")
		so.reload()
		so.set(ld.RATE, 2)
		with self.assertRaises(frappe.ValidationError):
			so.save()

	# ---- LD for late delivery ----
	def test_nothing_late_no_ld(self):
		so = _order("Railways", due_in=10)
		self.assertEqual(ld.exposure(so.name)["total"], 0)

	def test_pending_and_late_counts_whole_weeks(self):
		so = _order("Railways", days_ago=30, due_in=-10)  # due 10 days ago: 2 weeks (part of a week counts)
		result = ld.exposure(so.name)
		self.assertEqual(result["total"], 10)  # 1000 x 0.5 % x 2
		line = result["lines"][0]
		self.assertEqual((line.pending, line.late_qty, line.days_late), (10, 10, 10))

	def test_per_day_clause(self):
		so = _order(
			"Private",
			days_ago=30,
			due_in=-10,
			**{ld.APPLICABLE: 1, ld.RATE: 0.1, ld.CAP: 10, ld.PERIOD: ld.DAY},
		)
		self.assertEqual(ld.exposure(so.name)["total"], 10)  # 1000 x 0.1 % x 10 days

	def test_grace_days(self):
		so = _order(
			"Private", days_ago=30, due_in=-10, **{ld.APPLICABLE: 1, ld.RATE: 0.5, ld.CAP: 10, ld.GRACE: 7}
		)
		self.assertEqual(ld.exposure(so.name)["total"], 5)  # 3 days late after grace: 1 week

	def test_cap_on_the_value_delivered_late(self):
		so = _order("Railways", days_ago=200, due_in=-150)  # 22 weeks x 0.5 % = 11 %, capped at 10 %
		result = ld.exposure(so.name)
		self.assertEqual(result["total"], 100)
		self.assertEqual(result["lines"][0].uncapped, 110)

	def test_late_delivery_and_pending_both_count(self):
		so = _order("Railways", days_ago=30, due_in=-20)
		make_delivery_note(so.name, {PART: 4}, submit=True)  # delivered today: 20 days late = 3 weeks
		result = ld.exposure(so.name)
		line = result["lines"][0]
		self.assertEqual((line.delivered, line.pending, line.late_qty), (4, 6, 10))
		self.assertEqual(result["total"], 15)  # (400 + 600) x 0.5 % x 3

	def test_on_time_delivery_costs_nothing(self):
		so = _order("Railways", due_in=5)
		make_delivery_note(so.name, {PART: 10}, submit=True)
		self.assertEqual(ld.exposure(so.name, add_days(today(), 30))["total"], 0)

	def test_as_on_a_later_date(self):
		so = _order("Railways", due_in=5)
		self.assertEqual(ld.exposure(so.name, add_days(today(), 19))["total"], 10)  # 14 days late = 2 weeks

	def test_whole_order_basis(self):
		so = _order(
			"Private",
			days_ago=30,
			due_in=-10,
			**{ld.APPLICABLE: 1, ld.RATE: 0.5, ld.CAP: 10, ld.BASIS: ld.WHOLE_ORDER},
		)
		self.assertEqual(ld.exposure(so.name)["total"], 10)

	def test_form_api(self):
		so = _order("Railways", days_ago=30, due_in=-10)
		result = ld.get_ld_exposure(so.name)
		self.assertEqual((result["total"], result["late_lines"]), (10, 1))
		self.assertEqual(result["terms"]["rate"], 0.5)

	# ---- set-up ----
	def test_defaults_validated(self):
		with self.assertRaises(frappe.ValidationError):
			validate_production_params(frappe._dict({ld.DEFAULT_RATE_FIELD: 150}))

	def test_hook_registered(self):
		events = frappe.get_hooks("doc_events")["Sales Order"]
		self.assertIn("pepl_os.pepl_production.ld.validate_sales_order", events["validate"])
