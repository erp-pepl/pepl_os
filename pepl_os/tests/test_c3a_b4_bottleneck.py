"""C3a-B4 - Bottleneck report: wait in front of each machine group between Job Order operations."""

import frappe
from frappe.utils import add_days, add_to_date, get_datetime, now_datetime, today

from pepl_os.pepl_production import bottleneck as bn
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_item,
	make_operation,
	make_workstation,
	test_warehouse,
)
from pepl_os.tests.utils import PEPLTestCase, set_param, set_single

MILL = "T-B4 MILL-01"
LATHE = "T-B4 LATHE-01"
GRIND = "T-B4 GRIND-01"
MILLS = "T-B4 MILL GROUP"
LATHES = "T-B4 LATHE GROUP"
GRINDERS = "T-B4 GRIND GROUP"
SYSTEM_PARAMETERS = "PEPL System Parameters"
NOW = get_datetime(f"{today()} 18:00:00")
T = add_days(today(), -2)  # all logs on the day before yesterday


def at(clock, day=T):
	return get_datetime(f"{day} {clock}:00")


def op(name, group, start=None, end=None, finished=False):
	return {"operation": name, "group": group, "start": start, "end": end, "finished": finished}


class TestBottleneck(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_workstation(MILL, MILLS)
		make_workstation(LATHE, LATHES)
		make_workstation(GRIND, GRINDERS)
		set_single("Manufacturing Settings", "disable_capacity_planning", 1)
		fg = make_item("T-B4-FG", st.FINISHED_GOODS).name
		rm = make_item("T-B4-RM", st.BOUGHT_OUT, valuation_rate=10).name
		for name, ws in (("T-B4 Milling", MILL), ("T-B4 Turning", LATHE), ("T-B4 Grinding", GRIND)):
			make_operation(name, ws)
		bom = frappe.get_doc(
			{
				"doctype": "BOM",
				"item": fg,
				"company": TEST_COMPANY,
				"currency": frappe.get_cached_value("Company", TEST_COMPANY, "default_currency"),
				"quantity": 1,
				"is_active": 1,
				"is_default": 1,
				"with_operations": 1,
				"items": [{"item_code": rm, "qty": 1, "rate": 10}],
				"operations": [
					{"operation": "T-B4 Milling", "workstation": MILL, "time_in_mins": 6},
					{"operation": "T-B4 Turning", "workstation": LATHE, "time_in_mins": 6},
					{"operation": "T-B4 Grinding", "workstation": GRIND, "time_in_mins": 6},
				],
			}
		).insert(ignore_permissions=True)
		bom.submit()
		cls.fg, cls.bom = fg, bom.name

	def setUp(self):
		set_param(bn.WARNING_FIELD, 8)

	def _job_order(self, qty=10):
		wo = frappe.get_doc(
			{
				"doctype": "Work Order",
				"production_item": self.fg,
				"bom_no": self.bom,
				"qty": qty,
				"stock_uom": "Nos",
				"company": TEST_COMPANY,
				"skip_transfer": 1,
				"fg_warehouse": test_warehouse("FG Stores"),
				"planned_start_date": add_to_date(now_datetime(), days=-3),
				"transfer_material_against": "Work Order",
			}
		)
		wo.get_items_and_operations_from_bom()
		wo.insert(ignore_permissions=True)
		wo.submit()
		cards = {
			c.operation: c.name
			for c in frappe.get_all("Job Card", filters={"work_order": wo.name}, fields=["name", "operation"])
		}
		return wo.name, cards

	def _log(self, card, start, end, qty):
		"""A time log as the shift entry posts it (written directly: the report only reads logs)."""
		frappe.get_doc(
			{
				"doctype": "Job Card Time Log",
				"parent": card,
				"parenttype": "Job Card",
				"parentfield": "time_logs",
				"from_time": start,
				"to_time": end,
				"completed_qty": qty,
				"time_in_mins": (get_datetime(end) - get_datetime(start)).total_seconds() / 60,
			}
		).db_insert()

	# ---- the rule ----
	def test_wait_is_this_start_minus_previous_finish(self):
		rows = bn.operation_waits(
			[
				op("Milling", MILLS, at("08:00"), at("12:00"), True),
				op("Turning", LATHES, at("18:00"), at("20:00"), True),
			],
			now=NOW,
		)
		self.assertEqual(len(rows), 1)  # the first operation has no wait
		self.assertEqual((rows[0]["group"], rows[0]["state"], rows[0]["hours"]), (LATHES, "waited", 6))

	def test_starting_before_the_previous_finished_is_an_overlap(self):
		rows = bn.operation_waits(
			[
				op("Milling", MILLS, at("08:00"), at("12:00"), True),
				op("Turning", LATHES, at("10:00"), at("13:00"), False),
			],
			now=NOW,
		)
		self.assertEqual((rows[0]["state"], rows[0]["hours"]), ("overlapped", 0))
		rows = bn.operation_waits(
			[op("Milling", MILLS, at("08:00"), at("12:00"), False), op("Turning", LATHES, at("11:00"), None)],
			now=NOW,
		)
		self.assertEqual(rows[0]["state"], "overlapped")  # previous not finished yet, pieces passed on

	def test_waiting_now_counts_hours_since_the_previous_finished(self):
		ops = [op("Milling", MILLS, at("08:00"), at("12:00"), True), op("Turning", LATHES)]
		rows = bn.operation_waits(ops, is_open=True, now=at("18:00", today()))
		self.assertEqual(rows[0]["state"], "waiting")
		self.assertAlmostEqual(rows[0]["hours"], 54, places=2)  # 2 days and 6 hours
		self.assertEqual(bn.operation_waits(ops, is_open=False, now=NOW)[0]["state"], "")  # closed Job Order

	def test_groups_ranked_by_average_wait(self):
		rows = [
			{"group": LATHES, "state": "waited", "hours": 6, "minutes": 120},
			{"group": LATHES, "state": "waited", "hours": 14, "minutes": 60},
			{"group": GRINDERS, "state": "waited", "hours": 2, "minutes": 30},
			{"group": GRINDERS, "state": "overlapped", "hours": 0, "minutes": 30},
			{"group": GRINDERS, "state": "waiting", "hours": 30, "minutes": 0},
		]
		groups = bn.group_rows(rows, warning=8)
		self.assertEqual([g["workstation_type"] for g in groups], [LATHES, GRINDERS])
		lathe, grind = groups
		self.assertEqual(
			(lathe["waits"], lathe["average_hours"], lathe["longest_hours"], lathe["total_hours"]),
			(2, 10, 14, 20),
		)
		self.assertEqual(
			(lathe["run_hours"], lathe["colour"], lathe["bottleneck"], lathe["rank"]), (3, "red", 1, 1)
		)
		self.assertEqual(
			(grind["waits"], grind["overlapped"], grind["waiting_now"], grind["oldest_waiting_hours"]),
			(1, 1, 1, 30),
		)
		self.assertEqual(
			(grind["colour"], grind["bottleneck"]), ("orange", 0)
		)  # below 8 h on average, but work waiting
		text = bn.summary(groups, warning=8)
		self.assertIn(f"Bottleneck: {LATHES} - work waited on average 10.0 h", text)
		self.assertIn(f"Average wait above 8 h: {LATHES}", text)
		self.assertEqual(bn.summary([], warning=8), "No waiting between operations in this period.")

	# ---- from real Job Orders ----
	def test_from_job_card_time_logs(self):
		name, cards = self._job_order(qty=10)
		self._log(cards["T-B4 Milling"], at("08:00"), at("10:00"), 6)
		self._log(cards["T-B4 Milling"], at("10:00"), at("12:00"), 4)  # 10 of 10: milling finished at 12:00
		self._log(cards["T-B4 Turning"], at("18:00"), at("20:00"), 10)  # turning finished at 20:00
		# grinding not started: waiting since 20:00 the day before yesterday
		rows = bn.operation_rows(
			{"job_order": name, "from_date": add_days(today(), -7), "to_date": today()}, now=NOW
		)
		by_op = {r["operation"]: r for r in rows}
		self.assertEqual((by_op["T-B4 Turning"]["state"], by_op["T-B4 Turning"]["hours"]), ("waited", 6))
		self.assertEqual(by_op["T-B4 Turning"]["group"], LATHES)
		self.assertEqual(by_op["T-B4 Grinding"]["state"], "waiting")
		self.assertAlmostEqual(
			by_op["T-B4 Grinding"]["hours"], 46, places=2
		)  # 20:00 two days ago -> 18:00 today
		self.assertEqual(by_op["T-B4 Grinding"]["group"], GRINDERS)
		self.assertNotIn("T-B4 Milling", by_op)

	def test_unfinished_previous_operation_is_not_a_wait(self):
		name, cards = self._job_order(qty=10)
		self._log(cards["T-B4 Milling"], at("08:00"), at("10:00"), 6)  # 6 of 10: milling still running
		rows = bn.operation_rows(
			{"job_order": name, "from_date": add_days(today(), -7), "to_date": today()}, now=NOW
		)
		self.assertEqual(rows, [])

	def test_report_runs(self):
		from pepl_os.pepl_production.report.pepl_bottleneck import pepl_bottleneck as report

		name, cards = self._job_order(qty=10)
		self._log(cards["T-B4 Milling"], at("08:00"), at("12:00"), 10)
		self._log(cards["T-B4 Turning"], at("22:00"), at("23:00"), 10)  # waited 10 h: above 8 -> red
		filters = {"job_order": name, "from_date": add_days(today(), -7), "to_date": today()}
		columns, data, message = report.execute(filters)
		lathe = next(r for r in data if r["workstation_type"] == LATHES)
		self.assertEqual((lathe["average_hours"], lathe["colour"]), (10, "red"))
		self.assertIn("Bottleneck:", message)
		columns, data, message = report.execute({**filters, "show": "Operations"})
		self.assertIn("job_order", [c["fieldname"] for c in columns])
		self.assertIn("Waiting now", [r["state_text"] for r in data])  # grinding waits since 23:00
		self.assertTrue(frappe.db.exists("Report", "PEPL Bottleneck"))

	# ---- settings ----
	def test_warning_hours_must_be_more_than_zero(self):
		doc = frappe.get_doc(SYSTEM_PARAMETERS)
		doc.set(bn.WARNING_FIELD, 0)
		with self.assertRaisesRegex(frappe.ValidationError, "Bottleneck: Wait Warning Hours"):
			validate_production_params(doc)
		field = frappe.get_meta(SYSTEM_PARAMETERS).get_field(bn.WARNING_FIELD)
		self.assertEqual((field.fieldtype, str(field.default)), ("Float", "8"))
