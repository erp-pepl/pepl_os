"""C2-19 - Reorder engine: consumption, level formula, review, low-stock ToDo."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_stores import reorder
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import PEPLTestCase, set_param

OIL = "PEPL-T-REORDER-OIL"
NEW = "PEPL-T-REORDER-NEW"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _wip():
	return frappe.db.get_value(
		"Warehouse", {"company": TEST_COMPANY, "warehouse_name": ["like", "WIP %"], "is_group": 0}, "name"
	)


def _move(purpose, item, qty, days_ago, s=None, t=None):
	entry = frappe.get_doc(
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
					"s_warehouse": s,
					"t_warehouse": t,
					"basic_rate": 10 if not s else None,
				}
			],
		}
	).insert(ignore_permissions=True)
	entry.submit()
	return entry


class TestReorder(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(OIL, st.CONSUMABLES, valuation_rate=10, lead_time_days=7)
		make_item(NEW, st.CONSUMABLES, valuation_rate=10, lead_time_days=7)

	def setUp(self):
		set_param("custom_reorder_lookback_days", 90)
		set_param("custom_reorder_safety_days", 3)
		set_param("enable_operational_todos", 1)
		self.store = _wh("Consumables Stores")

	def _history(self):
		_move("Material Receipt", OIL, 2000, 95, t=self.store)
		_move("Material Issue", OIL, 300, 80, s=self.store)
		_move("Material Issue", OIL, 300, 40, s=self.store)
		_move("Material Transfer", OIL, 300, 20, s=self.store, t=_wip())  # to WIP: consumption
		_move("Material Transfer", OIL, 50, 10, s=self.store, t=_wh("Tool Room"))  # store to store: not

	def test_consumption_excludes_store_transfers(self):
		self._history()
		self.assertEqual(reorder.consumption(OIL, self.store, today(), 90), 900)

	def test_level_formula(self):
		self._history()
		s = reorder.suggest_reorder(OIL, self.store)
		self.assertEqual((s.daily_consumption, s.lead_time_days), (10, 7))
		self.assertEqual((s.suggested_level, s.suggested_qty), (100, 300))
		self.assertFalse(s.insufficient_history)

	def test_insufficient_history_flagged(self):
		_move("Material Receipt", NEW, 100, 10, t=self.store)
		_move("Material Issue", NEW, 20, 5, s=self.store)
		s = reorder.suggest_reorder(NEW, self.store)
		self.assertTrue(s.insufficient_history)
		self.assertIn("Insufficient history", s.basis)

	def _review(self):
		doc = frappe.get_doc(
			{"doctype": reorder.REVIEW, "company": TEST_COMPANY, "review_date": today()}
		).insert(ignore_permissions=True)
		reorder.compute_suggestions(doc.name)
		return frappe.get_doc(reorder.REVIEW, doc.name)

	def test_review_submit_writes_item_reorder(self):
		self._history()
		doc = self._review()
		row = next(r for r in doc.items if r.item_code == OIL)
		self.assertEqual((row.suggested_level, row.accept), (100, 1))
		for r in doc.items:
			if r.item_code != OIL:
				r.accept = 0
		doc.save()
		doc.submit()
		self.assertEqual(
			frappe.db.get_value(
				"Item Reorder",
				{"parent": OIL, "warehouse": self.store},
				["warehouse_reorder_level", "warehouse_reorder_qty"],
			),
			(100, 300),
		)

	def test_reorder_todo_opens_and_closes(self):
		self.test_review_submit_writes_item_reorder()  # stock 1050 left, level 100
		_move("Material Issue", OIL, 1000, 0, s=self.store)  # 50 left
		reorder.sync_reorder_todos()
		todo = {"reference_type": "Item", "reference_name": OIL, "status": "Open"}
		self.assertTrue(frappe.db.exists("ToDo", todo))
		mr = reorder.make_reorder_mr(OIL, self.store)
		self.assertEqual(frappe.db.get_value("Material Request", mr, "docstatus"), 0)
		_move("Material Receipt", OIL, 200, 0, t=self.store)  # 250
		reorder.sync_reorder_todos()
		self.assertFalse(frappe.db.exists("ToDo", todo))
