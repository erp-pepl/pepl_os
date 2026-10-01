"""C2-14 - Delivery letdowns (late / short) and the vendor delivery score."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import add_days, today

from pepl_os.pepl_purchase import letdown as ld
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

ITEM = "PEPL-T-LTD-ITEM"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _supplier(name):
	if not frappe.db.exists("Supplier", name):
		make_supplier(name).insert(ignore_permissions=True)
	frappe.db.set_value("Supplier", name, "custom_approval_state", "Approved")
	return name


def _po(supplier, qty, promised, po_date):
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": supplier,
			"company": TEST_COMPANY,
			"transaction_date": po_date,
			"schedule_date": promised,
			"items": [
				{
					"item_code": ITEM,
					"qty": qty,
					"rate": 10,
					"schedule_date": promised,
					"warehouse": _wh("Bought-Out Stores"),
				}
			],
		}
	).insert(ignore_permissions=True)
	po.submit()
	return po


def _receive(po, qty, on=None):
	pr = make_purchase_receipt(po.name)
	if on:
		pr.set_posting_time = 1
		pr.posting_date = on
	for row in pr.items:
		row.qty = qty
		row.received_qty = qty
	pr.insert(ignore_permissions=True)
	pr.submit()
	return pr


def _letdowns(po, **filters):
	return frappe.get_all(ld.DOCTYPE, filters={"purchase_order": po.name, **filters}, fields=["*"])


class TestLetdowns(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(ITEM, st.BOUGHT_OUT, valuation_rate=10)

	def setUp(self):
		set_param("custom_po_approval_value_threshold", 0)
		set_param("custom_late_grace_days", 0)
		set_param("custom_receipt_short_tolerance_percent", 0)
		set_param("custom_vendor_score_lookback_days", 365)

	def test_late_receipt_creates_letdown_with_days(self):
		s = _supplier("PEPL T LTD Late")
		po = _po(s, 10, add_days(today(), -4), add_days(today(), -10))
		_receive(po, 10)
		rows = _letdowns(po)
		self.assertEqual([(r.letdown_type, r.days_late) for r in rows], [(ld.LATE, 4)])

	def test_on_time_receipt_creates_none(self):
		s = _supplier("PEPL T LTD OnTime")
		po = _po(s, 10, add_days(today(), -4), add_days(today(), -10))
		_receive(po, 10, on=add_days(today(), -4))
		self.assertEqual(_letdowns(po), [])

	def test_grace_days_respected(self):
		set_param("custom_late_grace_days", 5)
		s = _supplier("PEPL T LTD Grace")
		po = _po(s, 10, add_days(today(), -4), add_days(today(), -10))
		_receive(po, 10)
		self.assertEqual(_letdowns(po), [])

	def test_pr_cancel_removes_its_letdowns(self):
		s = _supplier("PEPL T LTD Cancel")
		po = _po(s, 10, add_days(today(), -3), add_days(today(), -10))
		pr = _receive(po, 10)
		self.assertEqual(len(_letdowns(po)), 1)
		pr.cancel()
		self.assertEqual(_letdowns(po), [])

	def test_short_close_creates_short_letdown(self):
		set_param("custom_receipt_short_tolerance_percent", 10)
		s = _supplier("PEPL T LTD Short")
		po = _po(s, 100, add_days(today(), 10), add_days(today(), -2))
		_receive(po, 80)
		frappe.get_doc("Purchase Order", po.name).update_status("Closed")
		rows = _letdowns(po)
		self.assertEqual([(r.letdown_type, r.qty_short) for r in rows], [(ld.SHORT, 20)])
		frappe.get_doc("Purchase Order", po.name).update_status(
			"Submitted"
		)  # re-opened (what the Re-open button sends)
		self.assertEqual(_letdowns(po), [])

	def test_short_within_tolerance_not_logged(self):
		set_param("custom_receipt_short_tolerance_percent", 10)
		s = _supplier("PEPL T LTD Tolerance")
		po = _po(s, 100, add_days(today(), 10), add_days(today(), -2))
		_receive(po, 95)
		frappe.get_doc("Purchase Order", po.name).update_status("Closed")
		self.assertEqual(_letdowns(po), [])

	def test_late_and_short(self):
		s = _supplier("PEPL T LTD LateShort")
		po = _po(s, 10, add_days(today(), -3), add_days(today(), -10))
		_receive(po, 6)
		frappe.get_doc("Purchase Order", po.name).update_status("Closed")
		self.assertEqual(sorted(r.letdown_type for r in _letdowns(po)), [ld.LATE, ld.LATE_SHORT])

	def test_score_three_on_time_one_late_is_75(self):
		s = _supplier("PEPL T LTD Score")
		for days in (20, 15, 10):
			po = _po(s, 5, add_days(today(), -days), add_days(today(), -30))
			_receive(po, 5, on=add_days(today(), -days))
		late = _po(s, 5, add_days(today(), -5), add_days(today(), -30))
		_receive(late, 5)
		self.assertEqual(ld.delivery_score(s), (75.0, 4))
		ld.update_supplier_score(s)
		self.assertEqual(
			frappe.db.get_value("Supplier", s, ["custom_delivery_score", "custom_delivery_scored_lines"]),
			(75.0, 4),
		)

	def test_excused_letdown_not_scored(self):
		s = _supplier("PEPL T LTD Excuse")
		on_time = _po(s, 5, add_days(today(), -10), add_days(today(), -30))
		_receive(on_time, 5, on=add_days(today(), -10))
		late = _po(s, 5, add_days(today(), -5), add_days(today(), -30))
		_receive(late, 5)
		self.assertEqual(ld.delivery_score(s), (50.0, 2))
		name = _letdowns(late)[0].name
		ld.excuse_letdown(name, "Transport strike, not the supplier's fault")
		self.assertEqual(ld.delivery_score(s), (100.0, 1))
		self.assertTrue(
			frappe.db.exists("PEPL Override Log", {"rule_code": ld.EXCUSE_RULE, "reference_name": name})
		)
		self.assertEqual(frappe.db.get_value("Supplier", s, "custom_delivery_score"), 100)

	def test_only_manager_can_excuse(self):
		s = _supplier("PEPL T LTD Rights")
		po = _po(s, 5, add_days(today(), -3), add_days(today(), -10))
		_receive(po, 5)
		frappe.set_user(make_user("pepl.ltd.buyer@example.com", ["Purchase User"]))
		try:
			with self.assertRaises(frappe.PermissionError):
				ld.excuse_letdown(_letdowns(po)[0].name, "Buyer trying to excuse it")
		finally:
			frappe.set_user("Administrator")

	def test_no_lines_due_means_no_score(self):
		s = _supplier("PEPL T LTD Future")
		_po(s, 5, add_days(today(), 10), today())
		self.assertEqual(ld.delivery_score(s), (None, 0))

	def test_daily_job_registered(self):
		self.assertIn(
			"pepl_os.pepl_purchase.letdown.daily_delivery_scores",
			frappe.get_hooks("scheduler_events")["daily"],
		)
