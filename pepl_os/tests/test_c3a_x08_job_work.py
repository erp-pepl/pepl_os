"""C3a-X8 - Job-work reconciliation: sent to the job worker, received back processed, returned unprocessed."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_production import job_work as jw
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier, test_warehouse
from pepl_os.tests.utils import PEPLTestCase, set_param

PLATER = "T-JW Platers"
STORE_NAME = "T-JW Platers Store"
ROD = "T-JW-ROD"
PIN = "T-JW-PIN"
OWNER = "Administrator"


def _entry(rows, posting_date=None, movement=None, purpose="Material Transfer", is_return=0):
	doc = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": purpose,
			"purpose": purpose,
			"company": TEST_COMPANY,
			"set_posting_time": 1,
			"posting_date": posting_date or today(),
			"is_return": is_return,
			"items": [
				{
					"item_code": item,
					"qty": qty,
					"s_warehouse": source,
					"t_warehouse": target,
					"basic_rate": 10,
				}
				for item, qty, source, target in rows
			],
		}
	)
	if movement:
		doc.set(jw.MOVEMENT_FIELD, movement)
	return doc


class TestJobWork(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		if not frappe.db.exists("Supplier", PLATER):
			make_supplier(PLATER).insert(ignore_permissions=True)
		parent = frappe.db.get_value("Warehouse", test_warehouse("RM Stores"), "parent_warehouse")
		cls.store = frappe.db.get_value("Warehouse", {"warehouse_name": STORE_NAME, "company": TEST_COMPANY})
		if not cls.store:
			cls.store = (
				frappe.get_doc(
					{
						"doctype": "Warehouse",
						"warehouse_name": STORE_NAME,
						"company": TEST_COMPANY,
						"parent_warehouse": parent,
						jw.JOB_WORKER_FIELD: PLATER,
					}
				)
				.insert(ignore_permissions=True)
				.name
			)
		cls.rm = test_warehouse("RM Stores")
		for code in (ROD, PIN):
			make_item(code, st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10)
		receipt = _entry(
			[(ROD, 500, None, cls.rm), (PIN, 500, None, cls.rm)],
			posting_date=add_days(today(), -400),
			purpose="Material Receipt",
		)
		receipt.insert(ignore_permissions=True)
		receipt.submit()

	def setUp(self):
		set_param(jw.RETURN_DAYS_FIELD, 30)
		set_param(jw.GST_WARNING_FIELD, 30)
		set_param("enable_operational_todos", 1)
		set_param(jw.OWNER_FIELD, OWNER)

	def _send(self, item, qty, days_ago):
		doc = _entry([(item, qty, self.rm, self.store)], posting_date=add_days(today(), -days_ago))
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def _back(self, item, qty, days_ago, movement):
		doc = _entry(
			[(item, qty, self.store, self.rm)], posting_date=add_days(today(), -days_ago), movement=movement
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def _line(self, item):
		rows = [r for r in jw.reconcile(TEST_COMPANY, PLATER) if r.item_code == item]
		return rows[0] if rows else None

	# ---- movements ----
	def test_material_going_to_the_job_worker_is_marked_sent(self):
		doc = self._send(ROD, 10, 5)
		self.assertEqual(doc.get(jw.MOVEMENT_FIELD), jw.SENT)

	def test_material_coming_back_must_say_what_it_is(self):
		self._send(ROD, 10, 5)
		doc = _entry([(ROD, 4, self.store, self.rm)])
		with self.assertRaisesRegex(frappe.ValidationError, "Job-Work Movement|coming back"):
			doc.insert(ignore_permissions=True)

	def test_a_return_entry_is_returned_unprocessed(self):
		self._send(ROD, 10, 5)
		doc = _entry([(ROD, 4, self.store, self.rm)], is_return=1)
		jw.validate_stock_entry(doc)  # the rule alone (a return entry has ERPNext rules of its own)
		self.assertEqual(doc.get(jw.MOVEMENT_FIELD), jw.RETURNED)

	def test_send_and_bring_back_in_one_entry_refused(self):
		self._send(ROD, 10, 5)
		doc = _entry([(PIN, 2, self.rm, self.store), (ROD, 2, self.store, self.rm)], movement=jw.RETURNED)
		with self.assertRaisesRegex(frappe.ValidationError, "two entries"):
			doc.insert(ignore_permissions=True)

	def test_send_to_subcontractor_must_go_to_a_job_worker_store(self):
		doc = _entry(
			[(ROD, 2, self.rm, test_warehouse("WIP Main Workshop"))], purpose="Send to Subcontractor"
		)
		with self.assertRaisesRegex(frappe.ValidationError, "job worker's store"):
			jw.validate_stock_entry(doc)
		ok = _entry([(ROD, 2, self.rm, self.store)], purpose="Send to Subcontractor")
		jw.validate_stock_entry(ok)
		self.assertEqual(ok.get(jw.MOVEMENT_FIELD), jw.SENT)

	def test_ordinary_transfers_are_untouched(self):
		doc = _entry([(ROD, 2, self.rm, test_warehouse("WIP Main Workshop"))], movement=jw.RECEIVED)
		doc.insert(ignore_permissions=True)
		self.assertFalse(doc.get(jw.MOVEMENT_FIELD))

	# ---- reconciliation ----
	def test_sent_received_returned_and_balance(self):
		self._send(ROD, 100, 20)
		self._back(ROD, 60, 10, jw.RECEIVED)
		self._back(ROD, 15, 8, jw.RETURNED)
		line = self._line(ROD)
		self.assertEqual((line.sent, line.received, line.returned, line.balance), (100, 60, 15, 25))
		self.assertEqual((line.job_worker, line.warehouse), (PLATER, self.store))
		self.assertEqual(line.days_outside, 20)
		self.assertEqual(line.status, jw.OUTSIDE)
		self.assertAlmostEqual(line.value, 250, places=2)

	def test_age_is_first_in_first_out(self):
		self._send(ROD, 50, 40)
		self._send(ROD, 50, 10)
		self._back(ROD, 50, 5, jw.RECEIVED)  # the first lot is back
		line = self._line(ROD)
		self.assertEqual((line.balance, line.days_outside, line.status), (50, 10, jw.OUTSIDE))

	def test_overdue_and_gst_limits(self):
		self._send(ROD, 10, 40)
		self.assertEqual(self._line(ROD).status, jw.OVERDUE)
		self._send(PIN, 10, 340)
		self.assertEqual(self._line(PIN).status, jw.GST_NEAR)
		set_param(jw.GST_WARNING_FIELD, 10)
		self.assertEqual(self._line(PIN).status, jw.OVERDUE)

	def test_gst_limit_passed_after_a_year(self):
		self._send(PIN, 10, 370)
		self.assertEqual(self._line(PIN).status, jw.GST_PASSED)

	def test_everything_back_is_clear(self):
		self._send(ROD, 10, 50)
		self._back(ROD, 10, 45, jw.RECEIVED)
		line = self._line(ROD)
		self.assertEqual((line.balance, line.status, line.days_outside), (0, jw.CLEAR, 0))

	def test_as_on_an_earlier_date(self):
		self._send(ROD, 10, 50)
		self._back(ROD, 10, 5, jw.RECEIVED)
		line = next(
			r for r in jw.reconcile(TEST_COMPANY, PLATER, add_days(today(), -10)) if r.item_code == ROD
		)
		self.assertEqual((line.balance, line.days_outside), (10, 40))

	# ---- alerts and report ----
	def test_daily_alert_one_todo_per_job_worker_then_closed(self):
		self._send(ROD, 10, 40)
		self.assertEqual(jw.daily_job_work_alerts(), [PLATER])
		todos = frappe.get_all(
			"ToDo",
			filters={"reference_type": "Supplier", "reference_name": PLATER, "status": "Open"},
			fields=["description", "allocated_to"],
		)
		self.assertEqual(len(todos), 1)
		self.assertIn(ROD, todos[0].description)
		self.assertEqual(todos[0].allocated_to, OWNER)
		self._back(ROD, 10, 1, jw.RECEIVED)
		self.assertEqual(jw.daily_job_work_alerts(), [])
		self.assertFalse(
			frappe.get_all(
				"ToDo", filters={"reference_type": "Supplier", "reference_name": PLATER, "status": "Open"}
			)
		)

	def test_run_now_is_for_the_production_manager(self):
		from pepl_os.tests.utils import make_user

		frappe.set_user(make_user("pepl.test.jw.store@example.com", ["Stock User"]))
		with self.assertRaises(frappe.PermissionError):
			jw.run_job_work_alerts_now()

	def test_report_runs_and_shows_what_is_outside(self):
		from pepl_os.pepl_production.report.pepl_job_work_reconciliation import (
			pepl_job_work_reconciliation as report,
		)

		self._send(ROD, 10, 5)
		columns, rows, _message, _chart, summary = report.execute(
			{"company": TEST_COMPANY, "supplier": PLATER, "outstanding_only": 1}
		)
		self.assertIn("balance", [c["fieldname"] for c in columns])
		self.assertEqual([r.item_code for r in rows], [ROD])
		self.assertEqual(summary[0]["value"], 1)

	def test_summary_for_the_supplier_form(self):
		self._send(ROD, 10, 40)
		result = jw.job_work_summary(PLATER)
		self.assertEqual([r.item_code for r in result["overdue"]], [ROD])

	# ---- set-up ----
	def test_parameters_validated(self):
		with self.assertRaises(frappe.ValidationError):
			validate_production_params(frappe._dict({jw.RETURN_DAYS_FIELD: 0}))
		with self.assertRaises(frappe.ValidationError):
			validate_production_params(frappe._dict({jw.GST_WARNING_FIELD: 400}))

	def test_daily_job_registered(self):
		self.assertIn(
			"pepl_os.pepl_production.job_work.daily_job_work_alerts",
			frappe.get_hooks("scheduler_events")["daily"],
		)
