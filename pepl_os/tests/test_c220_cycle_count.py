"""C2-20 - Cycle count: ABC split, due items, reasons, HOD approval, Stock Reconciliation."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_stores import cycle_count as cc
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import PEPLTestCase, make_user, reopen, set_param

ITEM = "PEPL-T-CC-OIL"
FRESH = "PEPL-T-CC-FRESH"
COUNTER = "pepl.t.counter@example.com"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _receipt(item, qty):
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"purpose": "Material Receipt",
			"company": TEST_COMPANY,
			"items": [
				{"item_code": item, "qty": qty, "t_warehouse": _wh("Consumables Stores"), "basic_rate": 10}
			],
		}
	).insert(ignore_permissions=True)
	entry.submit()


def _count():
	doc = frappe.get_doc(
		{
			"doctype": cc.COUNT,
			"company": TEST_COMPANY,
			"warehouse": _wh("Consumables Stores"),
			"count_date": today(),
		}
	).insert(ignore_permissions=True)
	cc.generate_count_sheet(doc.name)
	return frappe.get_doc(cc.COUNT, doc.name)


class TestCycleCount(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(ITEM, st.CONSUMABLES, valuation_rate=10)
		make_item(FRESH, st.CONSUMABLES, valuation_rate=10)

	def setUp(self):
		set_param("custom_count_frequency_c_days", 180)
		set_param("custom_count_variance_approval_percent", 2)

	def test_abc_split_by_value(self):
		split = cc.abc_split({"a": 700, "b": 200, "c": 60, "d": 40, "e": 0}, 80, 15)
		self.assertEqual(split, {"a": "A", "b": "A", "c": "B", "d": "C", "e": "C"})

	def test_sheet_picks_only_due_items(self):
		_receipt(ITEM, 100)
		_receipt(FRESH, 100)
		frappe.db.set_value("Item", FRESH, {cc.CLASS_FIELD: "C", cc.COUNTED_FIELD: add_days(today(), -10)})
		frappe.db.set_value("Item", ITEM, {cc.CLASS_FIELD: "C", cc.COUNTED_FIELD: add_days(today(), -200)})
		codes = [r.item_code for r in _count().items]
		self.assertIn(ITEM, codes)
		self.assertNotIn(FRESH, codes)

	def test_variance_requires_reason(self):
		_receipt(ITEM, 100)
		frappe.db.set_value("Item", ITEM, cc.COUNTED_FIELD, None)
		doc = _count()
		for row in doc.items:
			row.counted_qty = row.system_qty
			row.counted = 1
		row = next(r for r in doc.items if r.item_code == ITEM)
		row.counted_qty = row.system_qty - 5
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		reopen(doc)
		row.reason = "Damage"
		doc.save()

	def test_high_variance_needs_hod(self):
		_receipt(ITEM, 100)
		frappe.db.set_value("Item", ITEM, cc.COUNTED_FIELD, None)
		make_user(COUNTER, ["Stock User"])
		doc = _count()
		for row in doc.items:
			row.counted_qty, row.counted = row.system_qty, 1
			if row.item_code == ITEM:
				row.counted_qty, row.reason = row.system_qty - 50, "Suspected loss"
		doc.save()
		self.assertTrue(doc.needs_hod_approval)
		frappe.set_user(COUNTER)
		try:
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc(cc.COUNT, doc.name).submit()
		finally:
			frappe.set_user("Administrator")
		frappe.get_doc(cc.COUNT, doc.name).submit()

	def test_submit_creates_stock_reconciliation_for_variance_only(self):
		_receipt(ITEM, 100)
		_receipt(FRESH, 100)
		frappe.db.set_value("Item", ITEM, cc.COUNTED_FIELD, None)
		frappe.db.set_value("Item", FRESH, cc.COUNTED_FIELD, None)
		set_param("custom_count_variance_approval_percent", 0)
		doc = _count()
		for row in doc.items:
			row.counted_qty, row.counted = row.system_qty, 1
			if row.item_code == ITEM:
				row.counted_qty, row.reason = row.system_qty - 5, "Measurement"
		doc.save()
		before = frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": doc.warehouse}, "actual_qty")
		doc.submit()
		reco = frappe.get_doc("Stock Reconciliation", doc.stock_reconciliation)
		self.assertEqual([r.item_code for r in reco.items], [ITEM])
		self.assertEqual(
			frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": doc.warehouse}, "actual_qty"),
			before - 5,
		)
		self.assertEqual(str(frappe.db.get_value("Item", FRESH, cc.COUNTED_FIELD)), today())
		log = [r for r in cc.variance_log({"warehouse": doc.warehouse}) if r.reason == "Measurement"]
		self.assertEqual(
			(log[0].line_count, log[0].variance_qty), (1, -5)
		)  # regression: 'lines' is reserved in MariaDB
