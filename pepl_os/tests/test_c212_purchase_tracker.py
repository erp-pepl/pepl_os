"""C2-12 - Purchase Tracker: created on PO submit, recomputed by receipts, close, cancel and the daily job."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import add_days, getdate, today

from pepl_os.pepl_purchase import tracker as trk
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, set_param

ITEM = "PEPL-T-TRK-ITEM"
ITEM_2 = "PEPL-T-TRK-ITEM-2"
SUPPLIER = "PEPL T TRK Supplier"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _po(lines):
	"""lines: [(item_code, qty, promised_date)]"""
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": SUPPLIER,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"schedule_date": min(d for _i, _q, d in lines),
			"items": [
				{
					"item_code": code,
					"qty": qty,
					"rate": 10,
					"schedule_date": promised,
					"warehouse": _wh("Bought-Out Stores"),
				}
				for code, qty, promised in lines
			],
		}
	).insert(ignore_permissions=True)
	po.submit()
	return po


def _tracker(po):
	return frappe.get_doc(trk.DOCTYPE, trk.tracker_of(po.name))


def _receive(po, qty):
	pr = make_purchase_receipt(po.name)
	for row in pr.items:
		row.qty = qty
		row.received_qty = qty
	pr.insert(ignore_permissions=True)
	pr.submit()
	return pr


class TestPurchaseTrackerRules(PEPLTestCase):
	"""The status rules on their own (no database)."""

	def test_line_status_rules(self):
		d = getdate("2026-10-10")
		cases = [
			# ordered, received, as_of, closed, grace, lead -> status, days overdue
			((10, 10, "2026-10-20", False, 0, 3), (trk.RECEIVED, 0)),
			((10, 4, "2026-10-20", True, 0, 3), (trk.SHORT_CLOSED, 0)),
			((10, 0, "2026-10-13", False, 0, 3), (trk.OVERDUE, 3)),
			((10, 0, "2026-10-12", False, 2, 3), (trk.DUE_TODAY, 0)),  # within the grace days
			((10, 0, "2026-10-13", False, 2, 3), (trk.OVERDUE, 3)),
			((10, 0, "2026-10-10", False, 0, 3), (trk.DUE_TODAY, 0)),
			((10, 0, "2026-10-08", False, 0, 3), (trk.DUE_SOON, 0)),
			((10, 5, "2026-10-01", False, 0, 3), (trk.PART_RECEIVED, 0)),
			((10, 0, "2026-10-01", False, 0, 3), (trk.NOT_DUE, 0)),
		]
		for (ordered, received, as_of, closed, grace, lead), (status, overdue) in cases:
			got = trk.line_status(ordered, received, d, getdate(as_of), closed, grace, lead)
			self.assertEqual((got[0], got[2]), (status, overdue), (ordered, received, as_of, closed, grace))

	def test_worst_line_wins(self):
		self.assertEqual(trk.overall_status([trk.NOT_DUE, trk.OVERDUE, trk.DUE_SOON]), trk.OVERDUE)
		self.assertEqual(trk.overall_status([trk.RECEIVED, trk.SHORT_CLOSED]), trk.COMPLETED)
		self.assertEqual(trk.overall_status([trk.NOT_DUE], po_cancelled=True), trk.CANCELLED)


class TestPurchaseTracker(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(ITEM, st.BOUGHT_OUT, valuation_rate=10)
		make_item(ITEM_2, st.BOUGHT_OUT, valuation_rate=10)
		if not frappe.db.exists("Supplier", SUPPLIER):
			make_supplier(SUPPLIER).insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")

	def setUp(self):
		set_param("custom_po_approval_value_threshold", 0)
		set_param("custom_late_grace_days", 0)
		set_param("custom_delivery_alert_lead_days", 3)

	def test_tracker_created_on_po_submit_one_per_po(self):
		po = _po([(ITEM, 100, add_days(today(), 10)), (ITEM_2, 5, add_days(today(), 2))])
		self.assertEqual(frappe.db.count(trk.DOCTYPE, {"purchase_order": po.name}), 1)
		doc = _tracker(po)
		self.assertEqual(len(doc.lines), 2)
		self.assertEqual(doc.supplier, SUPPLIER)
		self.assertEqual(doc.status, trk.DUE_SOON)  # ITEM_2 is due in 2 days (lead 3)
		self.assertEqual(getdate(doc.next_due_date), getdate(add_days(today(), 2)))
		self.assertTrue(doc.last_computed_on)
		trk.ensure_tracker(po.name)  # a second trigger never makes a second tracker
		self.assertEqual(frappe.db.count(trk.DOCTYPE, {"purchase_order": po.name}), 1)

	def test_daily_job_is_registered(self):
		from frappe.core.doctype.scheduled_job_type.scheduled_job_type import sync_jobs

		method = "pepl_os.pepl_purchase.tracker.refresh_open_purchase_trackers"
		self.assertIn(method, frappe.get_hooks("scheduler_events")["daily"])
		sync_jobs()
		self.assertEqual(frappe.db.get_value("Scheduled Job Type", {"method": method}, "frequency"), "Daily")

	def test_job_recomputes_days_overdue(self):
		"""The frozen-job regression: days overdue must move on every run."""
		promised = add_days(today(), 1)
		po = _po([(ITEM, 10, promised)])
		name = trk.tracker_of(po.name)
		trk.refresh_all(as_of=add_days(promised, 3))
		doc = frappe.get_doc(trk.DOCTYPE, name)
		self.assertEqual((doc.status, doc.lines[0].days_overdue, doc.worst_days_overdue), (trk.OVERDUE, 3, 3))
		trk.refresh_all(as_of=add_days(promised, 5))
		doc = frappe.get_doc(trk.DOCTYPE, name)
		self.assertEqual((doc.lines[0].days_overdue, doc.worst_days_overdue), (5, 5))

	def test_tracked_job_runs(self):
		po = _po([(ITEM, 10, add_days(today(), 10))])
		trk.refresh_open_purchase_trackers()
		run = frappe.get_all(
			"PEPL Job Run",
			filters={"method": "pepl_os.pepl_purchase.tracker.refresh_open_purchase_trackers"},
			fields=["status", "records_touched"],
			order_by="creation desc",
			limit=1,
		)
		self.assertEqual(run[0].status, "Success")
		self.assertGreaterEqual(run[0].records_touched, 1)
		self.assertTrue(trk.tracker_of(po.name))

	def test_part_receipt_updates_immediately(self):
		po = _po([(ITEM, 100, add_days(today(), 10))])
		_receive(po, 60)
		line = _tracker(po).lines[0]
		self.assertEqual((line.received_qty, line.pending_qty, line.line_status), (60, 40, trk.PART_RECEIVED))

	def test_full_receipt_completes(self):
		po = _po([(ITEM, 10, add_days(today(), 10))])
		pr = _receive(po, 10)
		self.assertEqual(_tracker(po).status, trk.COMPLETED)
		pr.cancel()  # cancelling the receipt re-opens the line
		self.assertEqual(_tracker(po).lines[0].pending_qty, 10)

	def test_revised_date_does_not_change_promised_date(self):
		promised = add_days(today(), 1)
		po = _po([(ITEM, 10, promised)])
		doc = _tracker(po)
		doc.lines[0].revised_date = add_days(today(), 20)
		doc.vendor_revised_date = add_days(today(), 20)
		doc.save()
		trk.recompute_tracker(doc.name, as_of=add_days(promised, 2))
		doc.reload()
		self.assertEqual(getdate(doc.lines[0].promised_date), getdate(promised))
		self.assertEqual(getdate(doc.lines[0].revised_date), getdate(add_days(today(), 20)))
		self.assertEqual((doc.lines[0].line_status, doc.lines[0].days_overdue), (trk.OVERDUE, 2))

	def test_po_close_marks_short_closed(self):
		po = _po([(ITEM, 100, add_days(today(), 10))])
		_receive(po, 60)
		frappe.get_doc("Purchase Order", po.name).update_status("Closed")
		doc = _tracker(po)
		self.assertEqual((doc.lines[0].line_status, doc.status), (trk.SHORT_CLOSED, trk.COMPLETED))

	def test_po_cancel_cancels_tracker(self):
		po = _po([(ITEM, 10, add_days(today(), 10))])
		frappe.get_doc("Purchase Order", po.name).cancel()
		self.assertEqual(_tracker(po).status, trk.CANCELLED)

	def test_draft_po_is_not_tracked(self):
		doc = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": SUPPLIER,
				"company": TEST_COMPANY,
				"transaction_date": today(),
				"schedule_date": add_days(today(), 5),
				"items": [
					{
						"item_code": ITEM,
						"qty": 1,
						"rate": 10,
						"schedule_date": add_days(today(), 5),
						"warehouse": _wh("Bought-Out Stores"),
					}
				],
			}
		).insert(ignore_permissions=True)
		self.assertIsNone(trk.tracker_of(doc.name))
