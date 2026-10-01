"""C2-21 - Consumables issued per day / week / month, and as a % of sales."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, getdate, today

from pepl_os.pepl_stores import consumables as cons
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import PEPLTestCase

OIL = "PEPL-T-CONS-OIL"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _move(purpose, qty, on, s=None, t=None):
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": purpose,
			"purpose": purpose,
			"company": TEST_COMPANY,
			"set_posting_time": 1,
			"posting_date": on,
			"items": [
				{
					"item_code": OIL,
					"qty": qty,
					"s_warehouse": s,
					"t_warehouse": t,
					"basic_rate": 10 if not s else None,
				}
			],
		}
	).insert(ignore_permissions=True)
	entry.submit()


class TestConsumablesIssued(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(OIL, st.CONSUMABLES, valuation_rate=10)

	def _week(self):
		day = getdate(today())
		monday = add_days(day, -day.weekday() - 7)  # last full week
		store = _wh("Consumables Stores")
		_move("Material Receipt", 1000, add_days(monday, -1), t=store)
		for i, qty in enumerate([10, 20, 30, 40, 50, 0, 0]):
			if qty:
				_move("Material Issue", qty, add_days(monday, i), s=store)
		_move("Material Transfer", 70, add_days(monday, 2), s=store, t=_wh("Tool Room"))  # not consumption
		return monday

	def test_period_totals_day_week_month_agree(self):
		monday = self._week()
		f = {"company": TEST_COMPANY, "from_date": monday, "to_date": add_days(monday, 6)}
		days, _p, _m = cons.consumables_issued({**f, "period": cons.DAY})
		weeks, _p, _m = cons.consumables_issued({**f, "period": cons.WEEK})
		mine_days = sum(r.qty for r in days if r.group == OIL)
		mine_week = [r for r in weeks if r.group == OIL]
		self.assertEqual(mine_days, 150)
		self.assertEqual([(r.period, r.qty) for r in mine_week], [(str(monday), 150)])
		months, _p, _m = cons.consumables_issued({**f, "period": cons.MONTH})
		self.assertEqual(sum(r.qty for r in months if r.group == OIL), 150)

	def test_percentage_of_sales(self):
		monday = self._week()
		month = getdate(monday).strftime("%Y-%m")
		f = {"company": TEST_COMPANY, "from_date": monday, "to_date": add_days(monday, 6)}
		with patch.object(cons, "net_sales_by_month", return_value={month: 30000}):
			_rows, _p, months = cons.consumables_issued(f)
		row = next(m for m in months if m.month == month)
		self.assertEqual(round(row.percent_of_sales, 6), round(row.value / 30000 * 100, 6))
		self.assertGreater(row.value, 0)
