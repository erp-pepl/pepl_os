"""Cycle 2 health check (brief Phase 1 on live data) and the Receipt Log heat panel."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import add_days, today

from pepl_os.pepl_stores import health_check as hc
from pepl_os.pepl_stores import heat
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_file, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, set_param

ROD = "PEPL-T-HC-ROD"
SUPPLIER = "PEPL T HC Mill"
SINCE = add_days(today(), -400)


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _po(qty=10):
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": SUPPLIER,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 5),
			"items": [
				{
					"item_code": ROD,
					"qty": qty,
					"rate": 50,
					"schedule_date": add_days(today(), 5),
					"warehouse": _wh("RM Stores"),
				}
			],
		}
	).insert(ignore_permissions=True)
	po.submit()
	return po


def _receipt(po, heat_number="H-HC-1"):
	pr = make_purchase_receipt(po.name)
	for row in pr.items:
		row.custom_heat_number = heat_number
		row.custom_test_certificate = make_file(f"mtc-{heat_number}.pdf")
	pr.insert(ignore_permissions=True)
	pr.submit()
	return pr


def _rows(check, sheet, text):
	return [r for r in check[sheet] if text in " ".join(str(v) for v in r.values())]


class TestCycle2HealthCheck(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(ROD, st.RAW_MATERIAL, valuation_rate=50)
		if not frappe.db.exists("Supplier", SUPPLIER):
			make_supplier(SUPPLIER).insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")

	def setUp(self):
		set_param("custom_po_approval_value_threshold", 0)
		set_param("custom_heat_number_gate_mode", heat.HARD_BLOCK)

	def test_every_sheet_builds_and_downloads(self):
		check = hc.build_health_check(SINCE, TEST_COMPANY)
		self.assertEqual(list(check), [title for title, _cols in hc.SHEETS])
		self.assertTrue(set(hc.findings(check)) == set(check))
		from pepl_os.pepl_stores.audit import to_xlsx

		self.assertTrue(to_xlsx(check, hc.SHEETS)[:2] == b"PK")  # an xlsx is a zip

	def test_po_without_tracker_found(self):
		po = _po()
		self.assertFalse(_rows(hc.build_health_check(SINCE, TEST_COMPANY), "1 Purchase Trackers", po.name))
		frappe.db.delete("PEPL Purchase Tracker", {"purchase_order": po.name})
		found = _rows(hc.build_health_check(SINCE, TEST_COMPANY), "1 Purchase Trackers", po.name)
		self.assertEqual([r["check"] for r in found], ["Submitted PO without a Purchase Tracker"])

	def test_tracker_quantity_drift_found(self):
		po = _po(10)
		frappe.db.sql(
			"""update `tabPEPL Purchase Tracker Line` l join `tabPEPL Purchase Tracker` t on t.name = l.parent
			set l.ordered_qty = 7 where t.purchase_order = %s""",
			po.name,
		)
		found = _rows(hc.build_health_check(SINCE, TEST_COMPANY), "1 Purchase Trackers", po.name)
		self.assertIn("Tracker quantity differs from the PO", [r["check"] for r in found])

	def test_receipt_without_log_found(self):
		pr = _receipt(_po())
		check = hc.build_health_check(SINCE, TEST_COMPANY)
		self.assertFalse(_rows(check, "2 Receipt Log and heat", pr.name))
		frappe.db.delete("PEPL Receipt Log", {"purchase_receipt": pr.name})
		found = _rows(hc.build_health_check(SINCE, TEST_COMPANY), "2 Receipt Log and heat", pr.name)
		self.assertEqual([r["check"] for r in found], ["Receipt line without a Receipt Log row"])

	def test_unapproved_supplier_on_po_found(self):
		_po()
		frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Expired")
		try:
			found = _rows(hc.build_health_check(SINCE, TEST_COMPANY), "3 Supplier approval", SUPPLIER)
			self.assertEqual([r["check"] for r in found], ["Supplier on submitted POs is not approved"])
		finally:
			frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")

	def test_receipt_log_panel(self):
		pr = _receipt(_po(), heat_number="H-HC-PANEL")
		log = frappe.get_all("PEPL Receipt Log", filters={"purchase_receipt": pr.name}, pluck="name")[0]
		panel = heat.get_receipt_log_panel(log)
		texts = [r["text"] for r in panel["rows"]]
		self.assertIn("Heat number H-HC-PANEL", texts)
		self.assertIn("Test certificate attached", texts)
		self.assertEqual(panel["heat_number"], "H-HC-PANEL")
		self.assertEqual(panel["purchase_receipt"], pr.name)
