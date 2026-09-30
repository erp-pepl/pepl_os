"""C2-11 - PO approval by value (MD above the PO Approval Value) and promised dates."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_purchase import po_approval as pa
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

ITEM = "PEPL-T-POA-ITEM"
SUPPLIER = "PEPL T POA Supplier"
LIMIT = 10000


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _po(rate, qty=1, schedule_date=None):
	return frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": SUPPLIER,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 7),
			"items": [
				{
					"item_code": ITEM,
					"qty": qty,
					"rate": rate,
					"schedule_date": schedule_date or add_days(today(), 7),
					"warehouse": _wh("Bought-Out Stores"),
				}
			],
		}
	).insert(ignore_permissions=True)


class TestPOApproval(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(ITEM, st.BOUGHT_OUT)
		if not frappe.db.exists("Supplier", SUPPLIER):
			make_supplier(SUPPLIER).insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")
		cls.manager = make_user("pepl.poa.manager@example.com", ["Purchase Manager", "Purchase User"])
		cls.buyer = make_user("pepl.poa.buyer@example.com", ["Purchase User"])
		cls.md = make_user("pepl.poa.md@example.com", ["PEPL CEO"])

	def setUp(self):
		set_param(pa.THRESHOLD_FIELD, LIMIT)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _submit_as(self, user, po):
		frappe.set_user(user)
		frappe.get_doc("Purchase Order", po.name).submit()

	def test_needs_md_flag_follows_threshold(self):
		self.assertEqual(_po(rate=50000).custom_needs_md_approval, 1)
		self.assertEqual(_po(rate=100).custom_needs_md_approval, 0)
		set_param(pa.THRESHOLD_FIELD, 0)
		self.assertEqual(_po(rate=50000).custom_needs_md_approval, 0)  # no value set: no MD step

	def test_po_line_before_po_date_refused(self):
		with self.assertRaises(frappe.ValidationError):
			_po(rate=100, schedule_date=add_days(today(), -1))

	def test_manager_cannot_submit_above_threshold(self):
		po = _po(rate=50000)
		with self.assertRaises(frappe.PermissionError):
			self._submit_as(self.manager, po)
		self.assertEqual(frappe.db.get_value("Purchase Order", po.name, "docstatus"), 0)

	def test_md_submits_above_threshold(self):
		po = _po(rate=50000)
		self._submit_as(self.md, po)
		self.assertEqual(frappe.db.get_value("Purchase Order", po.name, "docstatus"), 1)

	def test_manager_submits_below_threshold(self):
		po = _po(rate=100)
		self._submit_as(self.manager, po)
		self.assertEqual(frappe.db.get_value("Purchase Order", po.name, "docstatus"), 1)

	def test_purchase_user_cannot_submit(self):
		po = _po(rate=100)
		with self.assertRaises(frappe.PermissionError):
			self._submit_as(self.buyer, po)

	def test_refusal_messages(self):
		po = _po(rate=50000)
		self.assertIn("MD / CEO", pa.refusal(po, ["Purchase Manager"]))
		self.assertIsNone(pa.refusal(po, ["PEPL CEO"]))
		small = _po(rate=100)
		self.assertIn("Purchase Manager", pa.refusal(small, ["Purchase User"]))
		self.assertIsNone(pa.refusal(small, ["Purchase Manager"]))

	def test_md_todo_raised_and_closed(self):
		set_param("enable_operational_todos", 1)
		set_param("custom_md_approver", self.md)
		po = _po(rate=50000)
		todo = {"reference_type": "Purchase Order", "reference_name": po.name, "status": "Open"}
		self.assertTrue(frappe.db.exists("ToDo", {**todo, "allocated_to": self.md}))
		self._submit_as(self.md, po)
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists("ToDo", todo))
