"""C2-13 - Chase list, vendor chase letter, PUR-CHASE ToDos and Open PO Ageing."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_purchase import chase
from pepl_os.pepl_purchase import tracker as trk
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

ITEM = "PEPL-T-CHS-ITEM"
CRITICAL = "PEPL T CHS Critical"
ROUTINE = "PEPL T CHS Routine"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _supplier(name, criticality):
	if not frappe.db.exists("Supplier", name):
		make_supplier(name, custom_vendor_criticality=criticality).insert(ignore_permissions=True)
	frappe.db.set_value(
		"Supplier",
		name,
		{"custom_approval_state": "Approved", "email_id": f"{name.lower().replace(' ', '.')}@example.com"},
	)
	return name


def _po(supplier, lines, po_date=None):
	"""lines: [(qty, promised_date, rate)]"""
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": supplier,
			"company": TEST_COMPANY,
			"transaction_date": po_date or today(),
			"schedule_date": min(d for _q, d, _r in lines),
			"items": [
				{
					"item_code": ITEM,
					"qty": qty,
					"rate": rate,
					"schedule_date": promised,
					"warehouse": _wh("Bought-Out Stores"),
				}
				for qty, promised, rate in lines
			],
		}
	).insert(ignore_permissions=True)
	po.submit()
	return po


class TestChase(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(ITEM, st.BOUGHT_OUT, valuation_rate=10)
		_supplier(CRITICAL, "Critical")
		_supplier(ROUTINE, "Routine")

	def setUp(self):
		set_param("custom_po_approval_value_threshold", 0)
		set_param("custom_late_grace_days", 0)
		set_param("custom_delivery_alert_lead_days", 3)

	def _rows(self, supplier):
		return [r for r in chase.chase_list({"supplier": supplier})]

	def test_chase_list_includes_only_due_and_overdue(self):
		po = _po(
			ROUTINE,
			[(5, add_days(today(), -2), 10), (5, add_days(today(), 2), 10), (5, add_days(today(), 30), 10)],
			po_date=add_days(today(), -10),
		)
		statuses = sorted(r.line_status for r in self._rows(ROUTINE) if r.purchase_order == po.name)
		self.assertEqual(statuses, [trk.DUE_SOON, trk.OVERDUE])  # the line due in 30 days is left out

	def test_chase_list_order_criticality_then_days(self):
		routine = _po(ROUTINE, [(5, add_days(today(), -9), 10)], po_date=add_days(today(), -20))
		critical = _po(CRITICAL, [(5, add_days(today(), -1), 10)], po_date=add_days(today(), -20))
		critical_late = _po(CRITICAL, [(5, add_days(today(), -4), 10)], po_date=add_days(today(), -20))
		mine = {routine.name, critical.name, critical_late.name}
		order = [r.purchase_order for r in chase.chase_list() if r.purchase_order in mine]
		# Critical supplier first (worst line first), then the Routine one, although it is later.
		self.assertEqual(order, [critical_late.name, critical.name, routine.name])

	def test_chase_stamps_last_chased(self):
		po = _po(CRITICAL, [(5, add_days(today(), -3), 10)], po_date=add_days(today(), -10))
		name = trk.tracker_of(po.name)
		before = frappe.db.get_value(trk.DOCTYPE, name, "chase_count") or 0
		stamped = chase.chase_vendor(CRITICAL)
		self.assertIn(name, stamped)
		after = frappe.db.get_value(trk.DOCTYPE, name, ["chase_count", "last_chased_on"], as_dict=True)
		self.assertEqual(after.chase_count, before + 1)
		self.assertTrue(after.last_chased_on)
		self.assertTrue(
			frappe.db.exists(
				"Communication",
				{"reference_doctype": "Supplier", "reference_name": CRITICAL, "sent_or_received": "Sent"},
			)
		)

	def test_chase_letter_lists_all_pending_lines(self):
		po = _po(
			ROUTINE,
			[(5, add_days(today(), -2), 10), (7, add_days(today(), 40), 10)],
			po_date=add_days(today(), -5),
		)
		lines = [line for line in chase.pepl_chase_lines(ROUTINE) if line.purchase_order == po.name]
		self.assertEqual(sorted(line.pending_qty for line in lines), [5, 7])  # not only the due ones
		html = frappe.get_print("Supplier", ROUTINE, print_format=chase.LETTER_FORMAT)
		self.assertIn(po.name, html)

	def test_supplier_without_email_refused(self):
		name = "PEPL T CHS No Mail"
		if not frappe.db.exists("Supplier", name):
			make_supplier(name).insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", name, {"custom_approval_state": "Approved", "email_id": None})
		_po(name, [(1, add_days(today(), -1), 10)], po_date=add_days(today(), -3))
		with self.assertRaises(frappe.ValidationError):
			chase.chase_vendor(name)

	def test_pur_chase_todo_opens_and_closes(self):
		set_param("enable_operational_todos", 1)
		set_param(
			"custom_purchase_notification_owner", make_user("pepl.chs.buyer@example.com", ["Purchase User"])
		)
		po = _po(ROUTINE, [(5, add_days(today(), -2), 10)], po_date=add_days(today(), -10))
		name = trk.tracker_of(po.name)
		chase.sync_chase_todos()
		todo = {"reference_type": trk.DOCTYPE, "reference_name": name, "status": "Open"}
		self.assertTrue(frappe.db.exists("ToDo", todo))
		frappe.get_doc("Purchase Order", po.name).update_status("Closed")  # no longer overdue
		chase.sync_chase_todos()
		self.assertFalse(frappe.db.exists("ToDo", todo))

	def test_open_po_ageing_buckets(self):
		name = "PEPL T CHS Ageing"
		if not frappe.db.exists("Supplier", name):
			make_supplier(name, custom_vendor_criticality="Important").insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", name, "custom_approval_state", "Approved")
		# PO 45 days old: one line 10 x 10 = 100 overdue 40 days, one line 5 x 10 = 50 not due yet.
		_po(
			name,
			[(10, add_days(today(), -40), 10), (5, add_days(today(), 20), 10)],
			po_date=add_days(today(), -45),
		)
		row = next(r for r in chase.open_po_ageing({"supplier": name}))
		self.assertEqual(row.open_orders, 1)
		self.assertEqual(row.open_value, 150)
		self.assertEqual((row.age_31_60, row.age_0_30), (150, 0))
		self.assertEqual((row.overdue_31_60, row.not_overdue), (100, 50))
		later = next(r for r in chase.open_po_ageing({"supplier": name, "as_of": add_days(today(), 30)}))
		self.assertEqual((later.age_61_90, later.overdue_61_90, later.overdue_1_30), (150, 100, 50))
