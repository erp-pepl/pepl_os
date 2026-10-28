"""C3a-P2 - Production Plan load view: each machine's booked hours against its available hours."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_production import load_view as lv
from pepl_os.pepl_production import machine_booking as mb
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	make_bom,
	make_item,
	make_production_plan,
	make_shift,
	make_work_order,
	make_workstation,
)
from pepl_os.tests.utils import PEPLTestCase, set_param, set_single

M1 = "T-LV M1"  # 08:00-16:00 = 8 h a day, one job at a time
M2 = "T-LV M2"  # 8 h a day, two jobs at a time
M3 = "T-LV M3"  # no working hours of its own: hours come from the active shifts
SHAFT = "T-LV-FG-SHAFT"  # 60 min a piece on M1
BUSH = "T-LV-FG-BUSH"  # 60 min a piece on M2
COLLAR = "T-LV-FG-COLLAR"  # 60 min a piece on M3
PLAIN = "T-LV-FG-PLAIN"  # no operations
DAY = add_days(today(), 40)
EIGHT_HOURS = [{"start_time": "08:00:00", "end_time": "16:00:00"}]


def at(hhmm, day=DAY):
	return f"{day} {hhmm}:00"


def _texts(rows):
	return " | ".join(r["text"] for r in rows)


def _load(plan, machine):
	return next(x for x in lv.machine_loads(plan) if x.workstation == machine)


class TestProductionPlanLoadView(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure("_Test Company")
		rm = make_item("T-LV-RM-BAR", st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10).name
		# an empty Holiday List on each machine, so the company's own list (weekly offs) never changes the days
		none = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "T-LV No Holidays",
				"from_date": add_days(DAY, -30),
				"to_date": add_days(DAY, 30),
			}
		).insert(ignore_permissions=True)
		make_workstation(M1, "T-LV Group", working_hours=EIGHT_HOURS, holiday_list=none.name)
		make_workstation(
			M2, "T-LV Group", production_capacity=2, working_hours=EIGHT_HOURS, holiday_list=none.name
		)
		make_workstation(M3, "T-LV Group", holiday_list=none.name)
		make_shift("T-LV Day", "08:00:00", "16:30:00", 30)  # at least one active shift
		for code, machine in ((SHAFT, M1), (BUSH, M2), (COLLAR, M3)):
			make_item(code, st.FINISHED_GOODS)
			make_bom(code, rm, machine, f"{code} Op", 60)
		make_item(PLAIN, st.FINISHED_GOODS)
		make_bom(PLAIN, rm)

	def setUp(self):
		set_single("Manufacturing Settings", "disable_capacity_planning", 1)
		set_single("Manufacturing Settings", "mins_between_operations", 0)
		set_param(mb.MODE_FIELD, mb.ADVISORY)
		set_param(lv.WARNING_FIELD, 85)

	# ---- hours ----
	def test_plan_hours_against_the_machines_working_hours(self):
		plan = make_production_plan([(SHAFT, 2, at("09:00"))])
		load = _load(plan, M1)
		self.assertEqual((load.own_hours, load.held_hours, load.available_hours, load.percent), (2, 0, 8, 25))
		self.assertEqual(load.days, 1)
		rows = lv.panel_rows(plan)
		self.assertEqual(rows[0]["colour"], "green")
		line = next(r for r in rows if r["text"].startswith(M1))
		self.assertIn("this plan 2 h of 8 h", line["text"])
		self.assertIn("25%", line["text"])
		self.assertEqual(line["colour"], "green")

	def test_open_job_orders_on_those_days_count_as_already_booked(self):
		make_work_order(SHAFT, 4, at("11:00"))
		make_work_order(SHAFT, 3, at("09:00", add_days(DAY, 5)))  # another day: not counted
		plan = make_production_plan([(SHAFT, 2, at("09:00"))])
		load = _load(plan, M1)
		self.assertEqual((load.own_hours, load.held_hours, load.percent), (2, 4, 75))
		self.assertIn("this plan 2 h + already booked 4 h = 6 h of 8 h", _texts(lv.panel_rows(plan)))

	def test_another_open_plan_counts_as_already_booked(self):
		make_production_plan([(SHAFT, 3, at("12:00"))], submit=True)
		self.assertEqual(_load(make_production_plan([(SHAFT, 2, at("09:00"))]), M1).held_hours, 3)

	def test_job_orders_made_from_this_plan_count_as_this_plan(self):
		plan = make_production_plan([(SHAFT, 2, at("09:00"))])
		wo = make_work_order(SHAFT, 3, at("12:00"))
		frappe.db.set_value("Work Order", wo.name, "production_plan", plan.name)
		load = _load(plan, M1)
		self.assertEqual((load.own_hours, load.held_hours), (5, 0))

	def test_orange_from_the_warning_share_red_over_100(self):
		set_param(lv.WARNING_FIELD, 70)
		make_work_order(SHAFT, 4, at("11:00"))
		rows = lv.panel_rows(make_production_plan([(SHAFT, 2, at("09:00"))]))  # 75 %
		self.assertEqual(rows[0]["colour"], "orange")
		self.assertEqual(next(r for r in rows if r["text"].startswith(M1))["colour"], "orange")
		rows = lv.panel_rows(make_production_plan([(SHAFT, 10, at("06:00"))]))  # 10 h + 4 h of 8 h
		self.assertEqual(rows[0]["colour"], "red")
		self.assertIn("overloaded", rows[0]["text"])
		self.assertIn("175%", _texts(rows))

	def test_a_plan_running_into_the_next_day_gets_both_days(self):
		load = _load(make_production_plan([(SHAFT, 20, at("09:00"))]), M1)  # ends 05:00 the next day
		self.assertEqual((load.days, load.available_hours, load.percent), (2, 16, 125))

	def test_holidays_are_not_working_days(self):
		holidays = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "T-LV Holidays",
				"from_date": add_days(DAY, -30),
				"to_date": add_days(DAY, 30),
				"holidays": [{"holiday_date": add_days(DAY, 1), "description": "T-LV holiday"}],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Workstation", M1, "holiday_list", holidays.name)
		load = _load(make_production_plan([(SHAFT, 20, at("09:00"))]), M1)
		self.assertEqual((load.days, load.available_hours), (1, 8))

	def test_a_half_day_holiday_counts_half(self):
		holidays = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "T-LV Half Day",
				"from_date": add_days(DAY, -30),
				"to_date": add_days(DAY, 30),
				"holidays": [
					{"holiday_date": add_days(DAY, 1), "description": "T-LV half day", "is_half_day": 1}
				],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Workstation", M1, "holiday_list", holidays.name)
		load = _load(make_production_plan([(SHAFT, 20, at("09:00"))]), M1)
		self.assertEqual((load.days, load.available_hours), (1.5, 12))

	def test_a_machine_that_runs_two_jobs_has_twice_the_hours(self):
		load = _load(make_production_plan([(BUSH, 4, at("09:00"))]), M2)
		self.assertEqual((load.available_hours, load.percent), (16, 25))
		self.assertIn("2 jobs at once", _texts(lv.panel_rows(make_production_plan([(BUSH, 4, at("09:00"))]))))

	def test_without_working_hours_the_active_shifts_are_used(self):
		minutes = sum(frappe.get_all("PEPL Shift", filters={"is_active": 1}, pluck="planned_minutes"))
		per_day, source = lv.hours_a_day(M3)
		self.assertAlmostEqual(per_day, minutes / 60.0)
		self.assertEqual(source, "active shifts")
		self.assertIn(
			"from the active shifts", _texts(lv.panel_rows(make_production_plan([(COLLAR, 1, at("09:00"))])))
		)

	def test_no_hours_anywhere_shows_the_hours_in_grey(self):
		frappe.db.sql("update `tabPEPL Shift` set is_active = 0")
		rows = lv.panel_rows(make_production_plan([(COLLAR, 3, at("09:00"))]))
		line = next(r for r in rows if r["text"].startswith(M3))
		self.assertEqual(line["colour"], "gray")
		self.assertIn("this plan 3 h (no working hours on the machine and no active shift)", line["text"])

	def test_a_plan_without_machine_time(self):
		rows = lv.panel_rows(make_production_plan([(PLAIN, 5, at("09:00"))]))
		self.assertEqual(len(rows), 1)
		self.assertIn("No machine time", rows[0]["text"])

	def test_double_bookings_are_pointed_out(self):
		plan = make_production_plan([(SHAFT, 2, at("09:00")), (SHAFT, 1, at("10:00"))])
		self.assertIn("double-booked", _texts(lv.panel_rows(plan)))

	# ---- set-up ----
	def test_warning_share_validated(self):
		with self.assertRaises(frappe.ValidationError):
			validate_production_params(frappe._dict({lv.WARNING_FIELD: 150}))

	def test_form_api(self):
		plan = make_production_plan([(SHAFT, 1, at("09:00"))])
		self.assertTrue(lv.get_production_plan_load(plan.name)["rows"])

	def test_panel_hooked_on_the_form(self):
		self.assertIn(
			"public/js/production_plan.js", str(frappe.get_hooks("doctype_js").get("Production Plan"))
		)
