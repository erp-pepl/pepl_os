"""C3b-Q2 - Instruments and calibration: master, records, daily due alert, Calibration Gate on QC Inspection."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import add_days, today

from pepl_os.common.jobs import JOB_RUN
from pepl_os.common.overrides import log_override
from pepl_os.pepl_quality import calibration as cal
from pepl_os.pepl_quality import incoming_qc as qc
from pepl_os.pepl_quality.params import validate_quality_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import SYSTEM_PARAMETERS, PEPLTestCase, make_user, set_param

OWNER = "pepl.t.cal.owner@example.com"
PIN = "PEPL-T-CAL-PIN"  # bought-out item, inspected on receipt, with a plan
SUPPLIER = "PEPL T CAL Pins"
PARAMETER = "PEPL-T-CAL Diameter"
TEMPLATE = "PEPL-T-CAL Pin Plan"


def _instrument(code, frequency=365, status=cal.ACTIVE):
	if frappe.db.exists(cal.INSTRUMENT, code):
		frappe.delete_doc(cal.INSTRUMENT, code, force=True)
	return frappe.get_doc(
		{
			"doctype": cal.INSTRUMENT,
			"instrument_id": code,
			"instrument_name": f"Vernier {code}",
			"instrument_type": "Vernier Caliper",
			"status": status,
			"calibration_frequency_days": frequency,
		}
	).insert(ignore_permissions=True)


def _record(instrument, days_ago, result=cal.PASS, submit=True, **fields):
	doc = frappe.get_doc(
		{
			"doctype": cal.RECORD,
			"instrument": instrument,
			"calibration_date": add_days(today(), -days_ago),
			"result": result,
			"certificate_no": f"CERT-{instrument}-{days_ago}" if result != cal.FAIL else None,
			"errors_found": "Jaw worn 0.05 mm" if result == cal.FAIL else None,
			**fields,
		}
	).insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def _todo(instrument):
	rows = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": cal.INSTRUMENT,
			"reference_name": instrument,
			"status": "Open",
			"description": ["like", f"%{cal.DUE_RULE}%"],
		},
		fields=["priority", "description", "allocated_to"],
	)
	return rows[0] if rows else None


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _inspection():
	"""A draft incoming QC Inspection with one numeric reading (plan 9.9 - 10.1), made by a Purchase Receipt."""
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": SUPPLIER,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 5),
			"items": [
				{
					"item_code": PIN,
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
	qi = frappe.get_doc(qc.QI, pr.items[0].quality_inspection)
	qi.readings[0].reading_1 = "10.0"
	return qi


class TestCalibration(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(PIN, st.BOUGHT_OUT, valuation_rate=10)
		frappe.db.set_value("Item", PIN, qc.FLAG, 1)
		if not frappe.db.exists("Quality Inspection Parameter", PARAMETER):
			frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": PARAMETER}).insert(
				ignore_permissions=True
			)
		if not frappe.db.exists("Quality Inspection Template", TEMPLATE):
			frappe.get_doc(
				{
					"doctype": "Quality Inspection Template",
					"quality_inspection_template_name": TEMPLATE,
					"item_quality_inspection_parameter": [
						{"specification": PARAMETER, "numeric": 1, "min_value": 9.9, "max_value": 10.1}
					],
				}
			).insert(ignore_permissions=True)
		frappe.db.set_value("Item", PIN, qc.TEMPLATE, TEMPLATE)
		if not frappe.db.exists("Supplier", SUPPLIER):
			make_supplier(SUPPLIER).insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")
		qc.switch_stock_settings_once()

	def setUp(self):
		set_param("custom_po_approval_value_threshold", 0)
		set_param("enable_operational_todos", 1)
		set_param("custom_enforce_override_reason", 1)
		set_param(cal.ALERT_FIELD, 15)
		set_param(cal.GATE_FIELD, cal.HARD_BLOCK)
		set_param(qc.MODE_FIELD, qc.ADVISORY)
		set_param(cal.OWNER_FIELD, make_user(OWNER, ["Quality Manager"]))

	# ---- state ----
	def test_state_rules(self):
		day = "2026-11-18"
		self.assertEqual(cal.state_of("Active", None, day, 15), (cal.NEVER, None))
		self.assertEqual(cal.state_of("Active", "2026-12-31", day, 15), (cal.VALID, 43))
		self.assertEqual(cal.state_of("Active", "2026-12-03", day, 15), (cal.DUE_SOON, 15))
		self.assertEqual(cal.state_of("Active", "2026-11-18", day, 15), (cal.DUE_SOON, 0))
		self.assertEqual(cal.state_of("Active", "2026-11-17", day, 15), (cal.OVERDUE, -1))
		self.assertEqual(cal.state_of("Out of Service", "2026-12-31", day, 15), (cal.NOT_IN_USE, 43))

	def test_new_instrument_is_never_calibrated_and_alerted(self):
		inst = _instrument("PEPL-T-VC-NEW")
		self.assertEqual(inst.calibration_state, cal.NEVER)
		todo = _todo(inst.name)
		self.assertEqual((todo.priority, todo.allocated_to), ("High", OWNER))
		self.assertIn("never been calibrated", todo.description)

	def test_frequency_must_be_sensible(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Calibration Frequency"):
			_instrument("PEPL-T-VC-ZERO", frequency=0)

	# ---- records ----
	def test_pass_record_fills_instrument_and_closes_alert(self):
		inst = _instrument("PEPL-T-VC-PASS", frequency=180)
		rec = _record(inst.name, 10, certificate_no="NABL-123")
		inst.reload()
		self.assertEqual(str(rec.next_due_on), add_days(today(), 170))
		self.assertEqual(
			(str(inst.last_calibrated_on), str(inst.calibration_due_on), inst.last_certificate_no),
			(add_days(today(), -10), add_days(today(), 170), "NABL-123"),
		)
		self.assertEqual(
			(inst.calibration_state, inst.days_to_due, inst.last_calibration_record),
			(cal.VALID, 170, rec.name),
		)
		self.assertIsNone(_todo(inst.name))

	def test_due_soon_and_overdue(self):
		soon = _instrument("PEPL-T-VC-SOON", frequency=30)
		_record(soon.name, 20)  # due in 10 days, window 15
		late = _instrument("PEPL-T-VC-LATE", frequency=30)
		_record(late.name, 40)  # due 10 days ago
		self.assertEqual(frappe.db.get_value(cal.INSTRUMENT, soon.name, "calibration_state"), cal.DUE_SOON)
		self.assertEqual(frappe.db.get_value(cal.INSTRUMENT, late.name, "calibration_state"), cal.OVERDUE)
		self.assertEqual(_todo(soon.name).priority, "Medium")
		self.assertEqual(_todo(late.name).priority, "High")
		self.assertIn("overdue", _todo(late.name).description)

	def test_fail_takes_out_of_service_pass_brings_back(self):
		inst = _instrument("PEPL-T-VC-FAIL")
		_record(inst.name, 5, result=cal.FAIL)
		self.assertEqual(
			frappe.db.get_value(cal.INSTRUMENT, inst.name, ["status", "calibration_state"]),
			(cal.OUT_OF_SERVICE, cal.NOT_IN_USE),
		)
		_record(inst.name, 1, result=cal.PASS_ADJUSTED)
		self.assertEqual(
			frappe.db.get_value(cal.INSTRUMENT, inst.name, ["status", "calibration_state"]),
			(cal.ACTIVE, cal.VALID),
		)

	def test_cancel_goes_back_to_previous_record(self):
		inst = _instrument("PEPL-T-VC-CANCEL")
		first = _record(inst.name, 100)
		second = _record(inst.name, 3)
		self.assertEqual(
			frappe.db.get_value(cal.INSTRUMENT, inst.name, "last_calibration_record"), second.name
		)
		second.cancel()
		self.assertEqual(
			frappe.db.get_value(cal.INSTRUMENT, inst.name, ["last_calibration_record", "calibration_due_on"]),
			(first.name, frappe.utils.getdate(first.next_due_on)),
		)

	def test_record_rules(self):
		inst = _instrument("PEPL-T-VC-RULES")
		with self.assertRaisesRegex(frappe.ValidationError, "future"):
			_record(inst.name, -2)
		with self.assertRaisesRegex(frappe.ValidationError, "Next Due On"):
			_record(inst.name, 5, next_due_on=add_days(today(), -6))
		rec = _record(inst.name, 5, submit=False)
		rec.certificate_no = None
		rec.save()
		with self.assertRaisesRegex(frappe.ValidationError, "certificate"):
			rec.submit()
		failed = _record(inst.name, 5, result=cal.FAIL, submit=False)
		failed.errors_found = ""
		failed.save()
		with self.assertRaisesRegex(frappe.ValidationError, "Errors Found"):
			failed.submit()
		scrapped = _instrument("PEPL-T-VC-SCRAP", status=cal.SCRAPPED)
		with self.assertRaisesRegex(frappe.ValidationError, "Scrapped"):
			_record(scrapped.name, 1)
		self.assertIsNone(_todo(scrapped.name))  # not in use: no alert

	# ---- daily job ----
	def test_daily_job_moves_state_with_the_calendar(self):
		inst = _instrument("PEPL-T-VC-JOB", frequency=30)
		_record(inst.name, 1)  # due in 29 days: Valid
		self.assertIsNone(_todo(inst.name))
		result = cal.refresh_calibration_alerts(as_of=add_days(today(), 20))  # 9 days left: Due Soon
		self.assertGreaterEqual(result["records_touched"], 1)
		self.assertEqual(
			frappe.db.get_value(cal.INSTRUMENT, inst.name, ["calibration_state", "days_to_due"]),
			(cal.DUE_SOON, 9),
		)
		self.assertEqual(_todo(inst.name).priority, "Medium")
		cal.refresh_calibration_alerts(as_of=today())  # back to Valid: ToDo closes itself
		self.assertIsNone(_todo(inst.name))

	def test_daily_job_is_scheduled_and_tracked(self):
		self.assertIn(
			"pepl_os.pepl_quality.calibration.daily_calibration_alerts",
			frappe.get_hooks("scheduler_events")["daily"],
		)
		cal.daily_calibration_alerts()
		self.assertTrue(frappe.db.exists(JOB_RUN, {"job_name": "Instrument calibration due alerts"}))
		self.assertIn("instrument(s) due", cal.run_calibration_alerts_now()["message"])
		frappe.set_user(make_user("pepl.t.cal.stores@example.com", ["Stock User"]))
		with self.assertRaises(frappe.PermissionError):
			cal.run_calibration_alerts_now()

	# ---- the Calibration Gate ----
	def test_gate_hard_block_refuses_overdue_instrument(self):
		late = _instrument("PEPL-T-VC-GATE-LATE", frequency=30)
		_record(late.name, 40)
		qi = _inspection()
		qi.readings[0].custom_instrument = late.name
		qi.save()
		self.assertIsNone(cal.calibration_gate_check(qi.name))  # Hard Block never offers a reason
		with self.assertRaisesRegex(frappe.ValidationError, "overdue for calibration"):
			qi.submit()

	def test_gate_soft_block_reason_and_valid_instrument(self):
		set_param(cal.GATE_FIELD, cal.SOFT_BLOCK)
		never = _instrument("PEPL-T-VC-GATE-NEVER")
		qi = _inspection()
		qi.readings[0].custom_instrument = never.name
		qi.save()
		check = cal.calibration_gate_check(qi.name)
		self.assertEqual(check["rule_code"], cal.GATE_RULE)
		self.assertIn("never been calibrated", check["message"])
		with self.assertRaisesRegex(frappe.ValidationError, cal.GATE_RULE):
			qi.reload().submit()
		log_override(cal.GATE_RULE, qc.QI, qi.name, check["message"], "Only gauge on the shop floor tonight")
		qi.reload().submit()
		self.assertEqual(qi.docstatus, 1)
		good = _instrument("PEPL-T-VC-GATE-GOOD")
		_record(good.name, 2)
		qi2 = _inspection()
		qi2.readings[0].custom_instrument = good.name
		qi2.save()
		self.assertIsNone(cal.calibration_gate_check(qi2.name))
		qi2.submit()
		self.assertEqual(qi2.status, "Accepted")

	def test_gate_advisory_only_warns(self):
		set_param(cal.GATE_FIELD, cal.ADVISORY)
		broken = _instrument("PEPL-T-VC-GATE-BROKEN", status=cal.OUT_OF_SERVICE)
		qi = _inspection()
		qi.readings[0].custom_instrument = broken.name
		qi.save()
		qi.submit()
		self.assertEqual(qi.docstatus, 1)

	# ---- settings ----
	def test_settings_validated(self):
		doc = frappe.get_doc(SYSTEM_PARAMETERS)
		doc.set(cal.ALERT_FIELD, 400)
		with self.assertRaisesRegex(frappe.ValidationError, "Calibration: Alert Days"):
			validate_quality_params(doc)
		doc.set(cal.ALERT_FIELD, 15)
		doc.set(cal.GATE_FIELD, "Sometimes")
		with self.assertRaisesRegex(frappe.ValidationError, "Calibration Gate"):
			validate_quality_params(doc)
		field = frappe.get_meta(SYSTEM_PARAMETERS).get_field(cal.GATE_FIELD)
		self.assertEqual(str(field.default), cal.HARD_BLOCK)
		self.assertTrue(frappe.get_meta("Quality Inspection Reading").get_field(cal.READING_FIELD))
		self.assertTrue(frappe.get_meta(cal.INSTRUMENT).track_changes)
		self.assertTrue(frappe.get_meta(cal.RECORD).track_changes)
