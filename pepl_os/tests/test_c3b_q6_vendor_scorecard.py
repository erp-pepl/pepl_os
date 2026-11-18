"""C3b-Q6 - Vendor scorecard: quality score from incoming inspections, NCR count, composite with the delivery score."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import add_days, today

from pepl_os.common.jobs import JOB_RUN
from pepl_os.pepl_purchase import rfq
from pepl_os.pepl_quality import incoming_qc as qc
from pepl_os.pepl_quality import scorecard as sc
from pepl_os.pepl_quality.params import validate_quality_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import SYSTEM_PARAMETERS, PEPLTestCase, make_user, set_param

PIN = "PEPL-T-VS-PIN"
SUPPLIER = "PEPL T VS Pins"
OTHER = "PEPL T VS Nuts"
PARAMETER = "PEPL-T-VS Diameter"
TEMPLATE = "PEPL-T-VS Pin Plan"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _lot(supplier, reading):
	"""One incoming lot of 10 pins from the supplier, inspected and submitted with the given reading (plan 9.9-10.1)."""
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": supplier,
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
	qi.readings[0].reading_1 = reading
	qi.save()
	qi.submit()
	return qi


def _scores(supplier):
	return frappe.db.get_value(
		"Supplier",
		supplier,
		[sc.QUALITY_FIELD, sc.LOTS_FIELD, sc.NCRS_FIELD, sc.COMPOSITE_FIELD],
		as_dict=True,
	)


class TestVendorScorecard(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(PIN, st.BOUGHT_OUT, valuation_rate=10)
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
		frappe.db.set_value("Item", PIN, {qc.FLAG: 1, qc.TEMPLATE: TEMPLATE})
		for name in (SUPPLIER, OTHER):
			if not frappe.db.exists("Supplier", name):
				make_supplier(name).insert(ignore_permissions=True)
			frappe.db.set_value("Supplier", name, "custom_approval_state", "Approved")
		qc.switch_stock_settings_once()

	def setUp(self):
		set_param("custom_po_approval_value_threshold", 0)
		set_param(qc.MODE_FIELD, qc.ADVISORY)
		set_param("custom_vendor_score_lookback_days", 365)
		set_param(sc.DELIVERY_WEIGHT_FIELD, 50)
		set_param(sc.QUALITY_WEIGHT_FIELD, 50)

	# ---- quality score ----
	def test_each_lot_updates_the_quality_score_at_once(self):
		_lot(SUPPLIER, "10.0")
		self.assertEqual(sc.quality_score(SUPPLIER), (100.0, 1))
		_lot(SUPPLIER, "10.4")  # rejected (also raises its NCR, C3b-Q3)
		_lot(SUPPLIER, "10.05")
		_lot(SUPPLIER, "9.95")
		self.assertEqual(sc.quality_score(SUPPLIER), (75.0, 4))
		s = _scores(SUPPLIER)
		self.assertEqual((s[sc.QUALITY_FIELD], s[sc.LOTS_FIELD], s[sc.NCRS_FIELD]), (75, 4, 1))
		self.assertEqual(
			s[sc.COMPOSITE_FIELD], 75
		)  # no delivery score yet: the composite is the quality score

	def test_cancelled_and_old_lots_do_not_count(self):
		bad = _lot(SUPPLIER, "10.4")
		_lot(SUPPLIER, "10.0")
		self.assertEqual(sc.quality_score(SUPPLIER), (50.0, 2))
		bad.cancel()
		self.assertEqual(sc.quality_score(SUPPLIER), (100.0, 1))
		self.assertEqual(_scores(SUPPLIER)[sc.LOTS_FIELD], 1)  # updated at once on cancel
		set_param("custom_vendor_score_lookback_days", 30)
		self.assertEqual(sc.quality_score(SUPPLIER, as_of=add_days(today(), 40)), (None, 0))

	def test_supplier_without_inspections_has_no_quality_score(self):
		self.assertEqual(sc.quality_score(OTHER), (None, 0))
		row = frappe._dict(
			custom_delivery_score=80,
			custom_delivery_scored_lines=5,
			custom_quality_score=0,
			custom_quality_scored_lots=0,
			custom_composite_score=80,
		)
		self.assertEqual(sc.card_scores(row), (80, None, 80))
		row.custom_delivery_scored_lines = 0
		self.assertEqual(sc.card_scores(row), (None, None, None))

	# ---- composite ----
	def test_composite_weights(self):
		self.assertEqual(sc.composite(80.0, 60.0), 70.0)
		set_param(sc.DELIVERY_WEIGHT_FIELD, 30)
		set_param(sc.QUALITY_WEIGHT_FIELD, 70)
		self.assertEqual(sc.composite(80.0, 60.0), 66.0)
		self.assertEqual(sc.composite(None, 60.0), 60.0)
		self.assertEqual(sc.composite(80.0, None), 80.0)
		self.assertIsNone(sc.composite(None, None))

	def test_weights_must_add_up_to_100(self):
		doc = frappe.get_doc(SYSTEM_PARAMETERS)
		doc.set(sc.DELIVERY_WEIGHT_FIELD, 60)
		doc.set(sc.QUALITY_WEIGHT_FIELD, 60)
		with self.assertRaisesRegex(frappe.ValidationError, "add up to 100"):
			validate_quality_params(doc)
		doc.set(sc.QUALITY_WEIGHT_FIELD, 40)
		validate_quality_params(doc)

	# ---- job, run now, screens ----
	def test_daily_job_scores_every_supplier_and_is_tracked(self):
		_lot(SUPPLIER, "10.0")
		frappe.db.set_value("Supplier", SUPPLIER, {sc.QUALITY_FIELD: 0, sc.LOTS_FIELD: 0})
		self.assertIn(
			"pepl_os.pepl_quality.scorecard.daily_vendor_scores",
			frappe.get_hooks("scheduler_events")["daily"],
		)
		sc.daily_vendor_scores()
		self.assertEqual(_scores(SUPPLIER)[sc.LOTS_FIELD], 1)
		self.assertTrue(frappe.db.exists(JOB_RUN, {"job_name": "Vendor quality and composite scores"}))
		self.assertGreaterEqual(sc.run_vendor_scores_now()["records_touched"], 1)
		frappe.set_user(make_user("pepl.t.vs.stores@example.com", ["Stock User"]))
		with self.assertRaises(frappe.PermissionError):
			sc.run_vendor_scores_now()

	def test_rfq_supplier_card_and_comparison_show_the_scores(self):
		_lot(SUPPLIER, "10.0")
		card = rfq.supplier_card(SUPPLIER)
		self.assertEqual((card["quality_score"], card["composite_score"]), (100, 100))
		self.assertIsNone(rfq.supplier_card(OTHER)["quality_score"])
		meta = frappe.get_meta("PEPL Quotation Comparison Row")
		self.assertTrue(meta.get_field("composite_score"))
		for field in (sc.LOTS_FIELD, sc.NCRS_FIELD, sc.COMPOSITE_FIELD, sc.UPDATED_FIELD):
			self.assertTrue(frappe.get_meta("Supplier").get_field(field).read_only, field)
