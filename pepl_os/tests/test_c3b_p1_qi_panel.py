"""C3b-P1 - QC Inspection panel: characteristic, tolerance, readings in / out, instrument calibration inline."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import add_days, today

from pepl_os.pepl_quality import calibration as cal
from pepl_os.pepl_quality import incoming_qc as qc
from pepl_os.pepl_quality import qi_panel
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, set_param

PIN = "PEPL-T-P1-PIN"
BARE = "PEPL-T-P1-BARE"  # inspected, no plan
SUPPLIER = "PEPL T P1 Pins"
DIAMETER = "PEPL-T-P1 Diameter"
FINISH = "PEPL-T-P1 Finish"
TEMPLATE = "PEPL-T-P1 Pin Plan"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _inspection(item=PIN):
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": SUPPLIER,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 5),
			"items": [
				{
					"item_code": item,
					"qty": 10,
					"rate": 10,
					"schedule_date": add_days(today(), 5),
					"warehouse": _wh("Bought-Out Stores"),
				}
			],
		}
	).insert(ignore_permissions=True)
	po.submit()
	pr = make_purchase_receipt(po.name)
	pr.insert(ignore_permissions=True)
	return frappe.get_doc(qc.QI, pr.items[0].quality_inspection)


def _instrument(code, days_ago=None):
	if frappe.db.exists(cal.INSTRUMENT, code):
		frappe.delete_doc(cal.INSTRUMENT, code, force=True)
	frappe.get_doc(
		{
			"doctype": cal.INSTRUMENT,
			"instrument_id": code,
			"instrument_name": code,
			"calibration_frequency_days": 30,
		}
	).insert(ignore_permissions=True)
	if days_ago is not None:
		rec = frappe.get_doc(
			{
				"doctype": cal.RECORD,
				"instrument": code,
				"calibration_date": add_days(today(), -days_ago),
				"result": cal.PASS,
				"certificate_no": f"C-{code}",
			}
		).insert(ignore_permissions=True)
		rec.submit()
	return code


def _texts(qi):
	return [r["text"] for r in qi_panel.get_inspection_panel(qi.name)]


def _rows(qi):
	return qi_panel.get_inspection_panel(qi.name)


class TestQIPanel(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(PIN, st.BOUGHT_OUT, valuation_rate=10)
		make_item(BARE, st.BOUGHT_OUT, valuation_rate=10)
		for param in (DIAMETER, FINISH):
			if not frappe.db.exists("Quality Inspection Parameter", param):
				frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": param}).insert(
					ignore_permissions=True
				)
		if not frappe.db.exists("Quality Inspection Template", TEMPLATE):
			frappe.get_doc(
				{
					"doctype": "Quality Inspection Template",
					"quality_inspection_template_name": TEMPLATE,
					"item_quality_inspection_parameter": [
						{"specification": DIAMETER, "numeric": 1, "min_value": 9.9, "max_value": 10.1},
						{"specification": FINISH, "numeric": 0, "value": "Smooth"},
					],
				}
			).insert(ignore_permissions=True)
		frappe.db.set_value("Item", PIN, {qc.FLAG: 1, qc.TEMPLATE: TEMPLATE})
		frappe.db.set_value("Item", BARE, {qc.FLAG: 1, qc.TEMPLATE: None})
		if not frappe.db.exists("Supplier", SUPPLIER):
			make_supplier(SUPPLIER).insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")
		qc.switch_stock_settings_once()

	def setUp(self):
		set_param("custom_po_approval_value_threshold", 0)
		set_param(qc.MODE_FIELD, qc.ADVISORY)
		set_param(cal.GATE_FIELD, cal.HARD_BLOCK)
		set_param(cal.ALERT_FIELD, 15)

	def test_not_measured_yet(self):
		qi = _inspection()
		rows = _rows(qi)
		self.assertTrue(
			rows[0]["text"].startswith(f"Incoming inspection of {PIN}: sample 10 · Purchase Receipt ")
		)
		self.assertTrue(rows[0]["text"].endswith(f" from {SUPPLIER}"))
		self.assertEqual(rows[1]["text"], f"{DIAMETER} 9.9 - 10.1: not measured yet · no instrument named")
		self.assertEqual((rows[1]["colour"], rows[2]["colour"]), ("orange", "orange"))
		self.assertEqual(rows[2]["text"], f"{FINISH} expected Smooth: not measured yet · no instrument named")
		self.assertEqual(rows[3]["text"], "2 characteristic(s) still to measure")
		self.assertEqual(rows[-1]["text"], "Calibration gate: Hard Block")

	def test_in_tolerance_with_calibrated_instrument(self):
		vc = _instrument("PEPL-T-P1-VC", days_ago=1)  # due in 29 days: Valid
		qi = _inspection()
		qi.readings[0].reading_1 = "10"
		qi.readings[0].reading_2 = "10.05"
		qi.readings[0].custom_instrument = vc
		qi.readings[1].reading_value = "Smooth"
		qi.save()
		rows = _rows(qi)
		self.assertTrue(
			rows[1]["text"].startswith(
				f"{DIAMETER} 9.9 - 10.1: 10, 10.05 (2 readings) - in tolerance · {vc} is calibrated until "
			)
		)
		self.assertEqual(rows[1]["colour"], "green")
		self.assertEqual(
			rows[2]["text"], f"{FINISH} expected Smooth: Smooth - Accepted · no instrument named"
		)
		self.assertEqual(rows[3], {"text": "Result on submit: Accepted", "colour": "green"})

	def test_out_of_tolerance_and_overdue_instrument(self):
		late = _instrument("PEPL-T-P1-DIAL", days_ago=40)  # due 10 days ago
		qi = _inspection()
		qi.readings[0].reading_1 = "10.0"
		qi.readings[0].reading_2 = "10.2"
		qi.readings[0].custom_instrument = late
		qi.readings[1].reading_value = "Rough"
		qi.save()
		rows = _rows(qi)
		self.assertIn("10, 10.2 (2 readings) - OUT: 10.2", rows[1]["text"])
		self.assertIn(f"{late} is overdue for calibration", rows[1]["text"])
		self.assertEqual(rows[1]["colour"], "red")
		self.assertIn("Rough - Rejected", rows[2]["text"])
		self.assertEqual(rows[3], {"text": "Result on submit: Rejected", "colour": "red"})

	def test_overdue_instrument_alone_turns_the_line_red(self):
		late = _instrument("PEPL-T-P1-BORE", days_ago=40)
		qi = _inspection()
		qi.readings[0].reading_1 = "10"
		qi.readings[0].custom_instrument = late
		qi.save()
		row = _rows(qi)[1]
		self.assertIn("in tolerance", row["text"])
		self.assertEqual(row["colour"], "red")

	def test_submitted_result_and_no_plan(self):
		qi = _inspection()
		qi.readings[0].reading_1 = "10"
		qi.readings[1].reading_value = "Smooth"
		qi.save()
		qi.submit()
		rows = _rows(qi)
		self.assertEqual(rows[-1], {"text": "Result: Accepted", "colour": "green"})
		bare = _inspection(BARE)
		texts = _texts(bare)
		self.assertIn("No inspection plan", texts[1])
		self.assertNotIn("Calibration gate: Hard Block", texts)

	def test_panel_hooked_on_the_form(self):
		self.assertIn(
			"public/js/quality_inspection.js", str(frappe.get_hooks("doctype_js").get("Quality Inspection"))
		)
