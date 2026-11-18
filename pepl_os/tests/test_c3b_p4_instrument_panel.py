"""C3b-P4 - Instrument panel: calibration state and days, last record, history, use in QC Inspections, next step."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import add_days, formatdate, today

from pepl_os.pepl_quality import calibration as cal
from pepl_os.pepl_quality import incoming_qc as qc
from pepl_os.pepl_quality import instrument_panel as ip
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

OWNER = "pepl.t.p4.owner@example.com"
PIN = "PEPL-T-P4-PIN"
SUPPLIER = "PEPL T P4 Pins"
PARAMETER = "PEPL-T-P4 Diameter"
TEMPLATE = "PEPL-T-P4 Pin Plan"


def _instrument(code, frequency=365, **fields):
	if frappe.db.exists(cal.INSTRUMENT, code):
		frappe.delete_doc(cal.INSTRUMENT, code, force=True)
	return frappe.get_doc(
		{
			"doctype": cal.INSTRUMENT,
			"instrument_id": code,
			"instrument_name": f"Vernier {code}",
			"instrument_type": "Vernier Caliper",
			"calibration_frequency_days": frequency,
			**fields,
		}
	).insert(ignore_permissions=True)


def _record(instrument, days_ago, result=cal.PASS):
	doc = frappe.get_doc(
		{
			"doctype": cal.RECORD,
			"instrument": instrument,
			"calibration_date": add_days(today(), -days_ago),
			"result": result,
			"certificate_no": f"CERT-{days_ago}" if result != cal.FAIL else None,
			"errors_found": "Jaw worn 0.05 mm" if result == cal.FAIL else None,
		}
	).insert(ignore_permissions=True)
	doc.submit()
	return doc


def _rows(name):
	return ip.get_instrument_panel(name)


def _row(name, start):
	return next((r for r in _rows(name) if r["text"].startswith(start)), None)


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _inspection(instrument):
	"""A draft incoming QC Inspection (plan 9.9 - 10.1) read as 10 with this instrument."""
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
	qi.readings[0].reading_1 = "10"
	qi.readings[0].set(cal.READING_FIELD, instrument)
	qi.save()
	return qi


class TestInstrumentPanel(PEPLTestCase):
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

	def test_never_calibrated(self):
		code = "PEPL-T-P4-NEW"
		_instrument(code, measuring_range="0-150 mm", least_count="0.02 mm", location="QC room")
		rows = _rows(code)
		self.assertEqual(
			rows[0],
			{
				"text": f"{code}: Vernier {code} (Vernier Caliper) · Active · range 0-150 mm,"
				" least count 0.02 mm · at QC room",
				"colour": "gray",
			},
		)
		self.assertEqual(
			rows[1], {"text": f"{code} has never been calibrated · every 365 days", "colour": "red"}
		)
		self.assertEqual(rows[2], {"text": "No calibration record yet", "colour": "orange"})
		self.assertEqual(rows[3], {"text": "Not used in a submitted QC Inspection yet", "colour": "gray"})
		self.assertEqual(rows[-1]["colour"], "red")
		self.assertTrue(rows[-1]["text"].startswith("Next: stop using it, calibrate it"))

	def test_valid_due_soon_overdue(self):
		code = "PEPL-T-P4-OK"
		_instrument(code)
		rec = _record(code, 10)
		rows = _rows(code)
		self.assertEqual(
			rows[1],
			{
				"text": f"{code} is calibrated until {formatdate(add_days(today(), 355))} (355 day(s) left)"
				" · every 365 days",
				"colour": "green",
			},
		)
		self.assertEqual(
			rows[2],
			{
				"text": f"Last calibration {formatdate(add_days(today(), -10))}: Pass · certificate CERT-10 ({rec.name})",
				"colour": "green",
			},
		)
		self.assertEqual(rows[3], {"text": "Calibration records: 1 (Pass 1)", "colour": "gray"})
		self.assertFalse([r for r in rows if r["text"].startswith("Next")])

		soon = "PEPL-T-P4-SOON"
		_instrument(soon, frequency=20)
		_record(soon, 10)
		due = formatdate(add_days(today(), 10))
		self.assertEqual(
			_rows(soon)[1],
			{
				"text": f"{soon} is due for calibration on {due} (10 day(s) left) · every 20 days",
				"colour": "orange",
			},
		)
		self.assertEqual(
			_row(soon, "Next"), {"text": f"Next: book the calibration before {due}", "colour": "orange"}
		)

		late = "PEPL-T-P4-LATE"
		_instrument(late, frequency=30)
		_record(late, 40)
		self.assertEqual(
			_rows(late)[1],
			{
				"text": f"{late} is overdue for calibration (due {formatdate(add_days(today(), -10))})"
				" - 10 day(s) overdue · every 30 days",
				"colour": "red",
			},
		)

	def test_failed_calibration_history(self):
		code = "PEPL-T-P4-FAIL"
		_instrument(code)
		_record(code, 40)
		fail = _record(code, 5, cal.FAIL)
		rows = _rows(code)
		self.assertEqual(rows[0]["text"], f"{code}: Vernier {code} (Vernier Caliper) · Out of Service")
		self.assertEqual(
			rows[1], {"text": f"{code} is not in use (Out of Service) · every 365 days", "colour": "red"}
		)
		self.assertEqual(
			rows[2],
			{
				"text": f"Last calibration {formatdate(add_days(today(), -5))}: Fail ({fail.name})",
				"colour": "red",
			},
		)
		self.assertEqual(
			rows[3]["text"],
			f"Calibration records: 2 (Pass 1, Fail 1) · last Fail {formatdate(add_days(today(), -5))}:"
			" Jaw worn 0.05 mm",
		)
		self.assertEqual(
			rows[-1],
			{
				"text": "Next: repair it, then submit a passed Calibration Record to bring it back to Active",
				"colour": "red",
			},
		)

	def test_use_and_drafts_the_gate_would_stop(self):
		good = "PEPL-T-P4-USED"
		_instrument(good)
		_record(good, 1)
		qi = _inspection(good)
		self.assertEqual(
			_row(good, "1 draft"),
			{"text": f"1 draft QC Inspection(s) name this instrument ({qi.name})", "colour": "gray"},
		)
		qi.submit()
		self.assertEqual(
			_row(good, "Used in"),
			{
				"text": f"Used in 1 submitted QC Inspection(s) in the last 90 days · last {qi.name} ({PIN})"
				f" on {formatdate(qi.report_date)}",
				"colour": "gray",
			},
		)
		self.assertIsNone(_row(good, "1 draft"))

		late = "PEPL-T-P4-STALE"
		_instrument(late, frequency=30)
		_record(late, 40)
		draft = _inspection(late)
		self.assertEqual(
			_row(late, "1 draft"),
			{
				"text": f"1 draft QC Inspection(s) name this instrument ({draft.name})"
				" - the Calibration Gate (Hard Block) will refuse them",
				"colour": "red",
			},
		)
		set_param(cal.GATE_FIELD, cal.SOFT_BLOCK)
		self.assertEqual(_row(late, "1 draft")["colour"], "orange")
		self.assertTrue(
			_row(late, "1 draft")["text"].endswith("will ask for a reason when they are submitted")
		)

	def test_scrapped(self):
		code = "PEPL-T-P4-SCRAP"
		_instrument(code, status=cal.SCRAPPED)
		rows = _rows(code)
		self.assertEqual(rows[1], {"text": f"{code} is not in use (Scrapped)", "colour": "gray"})
		self.assertEqual(rows[2], {"text": "No calibration record yet", "colour": "gray"})
		self.assertEqual(
			rows[-1], {"text": "Scrapped: it takes no more calibration records", "colour": "gray"}
		)
