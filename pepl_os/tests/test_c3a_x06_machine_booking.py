"""C3a-X6 - A Production Plan may not book a machine for more jobs at the same time than it can run."""

import frappe
from frappe.utils import add_days, get_datetime, today

from pepl_os.common.overrides import log_override
from pepl_os.pepl_production import machine_booking as mb
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	make_bom,
	make_item,
	make_production_plan,
	make_work_order,
	make_workstation,
)
from pepl_os.tests.utils import PEPLTestCase, set_param, set_single, stored_single

M1 = "T-MB M1"  # runs one job at a time
M2 = "T-MB M2"  # runs two jobs at a time
SHAFT = "T-MB-FG-SHAFT"  # 60 min a piece on M1
PIN = "T-MB-FG-PIN"  # 30 min a piece on M1
BUSH = "T-MB-FG-BUSH"  # 60 min a piece on M2
DAY = add_days(today(), 30)


def at(hhmm):
	return f"{DAY} {hhmm}:00"


class TestMachineDoubleBooking(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure("_Test Company")
		rm = make_item("T-MB-RM-BAR", st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10).name
		make_workstation(M1, "T-MB Group")
		make_workstation(M2, "T-MB Group", production_capacity=2)
		for code, machine, minutes in ((SHAFT, M1, 60), (PIN, M1, 30), (BUSH, M2, 60)):
			make_item(code, st.FINISHED_GOODS)
			make_bom(code, rm, machine, f"{code} Op", minutes)

	def setUp(self):
		set_single("Manufacturing Settings", "disable_capacity_planning", 1)
		set_single("Manufacturing Settings", "mins_between_operations", 0)
		set_param(mb.MODE_FIELD, mb.ADVISORY)
		set_param(mb.ENFORCE_FIELD, 1)

	# ---- layout ----
	def test_a_row_books_its_machine_for_qty_times_bom_minutes(self):
		plan = make_production_plan([(SHAFT, 2, at("09:00"))])
		bookings = mb.plan_bookings(plan)
		self.assertEqual(len(bookings), 1)
		self.assertEqual(bookings[0]["workstation"], M1)
		self.assertEqual(bookings[0]["start"], get_datetime(at("09:00")))
		self.assertEqual(bookings[0]["end"], get_datetime(at("11:00")))

	def test_layout_follows_erpnext_sequence_and_gap(self):
		start = at("08:00")
		ops = [
			{"workstation": "A", "operation": "Cut", "minutes": 60, "sequence_id": 0},
			{"workstation": "B", "operation": "Turn", "minutes": 30, "sequence_id": 0},
		]
		rows = mb.layout(start, ops, gap=10)
		self.assertEqual(rows[1]["start"], get_datetime(at("09:10")))
		together = [dict(o, sequence_id=1) for o in ops]
		rows = mb.layout(start, together, gap=10)
		self.assertEqual(rows[1]["start"], rows[0]["start"])

	# ---- clashes ----
	def test_two_rows_on_one_machine_at_the_same_time_clash(self):
		plan = make_production_plan([(SHAFT, 1, at("09:00")), (PIN, 1, at("09:30"))])
		self.assertIn(M1, plan.get(mb.CLASHES_FIELD))
		self.assertIn(PIN, plan.get(mb.CLASHES_FIELD))
		plan.submit()  # Advisory: warning only
		self.assertEqual(plan.docstatus, 1)

	def test_back_to_back_rows_do_not_clash(self):
		plan = make_production_plan([(SHAFT, 1, at("09:00")), (PIN, 1, at("10:00"))])
		self.assertFalse(plan.get(mb.CLASHES_FIELD))

	def test_a_machine_that_runs_two_jobs_takes_two(self):
		plan = make_production_plan([(BUSH, 1, at("09:00")), (BUSH, 1, at("09:15"))])
		self.assertFalse(plan.get(mb.CLASHES_FIELD))
		plan = make_production_plan([(BUSH, 1, at("09:00")), (BUSH, 1, at("09:15")), (BUSH, 1, at("09:30"))])
		self.assertIn(M2, plan.get(mb.CLASHES_FIELD))

	def test_a_row_ending_as_a_job_order_starts_does_not_clash(self):
		make_work_order(SHAFT, 1, at("09:30"))
		self.assertFalse(make_production_plan([(PIN, 1, at("09:00"))]).get(mb.CLASHES_FIELD))

	def test_an_open_job_order_holds_its_machine(self):
		wo = make_work_order(SHAFT, 1, at("09:30"))
		plan = make_production_plan([(PIN, 1, at("09:45"))])
		self.assertIn(wo.name, plan.get(mb.CLASHES_FIELD))

	def test_a_stopped_job_order_does_not_hold_the_machine(self):
		wo = make_work_order(SHAFT, 1, at("09:30"))
		frappe.db.set_value("Work Order", wo.name, "status", "Stopped")
		plan = make_production_plan([(PIN, 1, at("09:45"))])
		self.assertFalse(plan.get(mb.CLASHES_FIELD))

	def test_draft_job_order_does_not_hold_the_machine(self):
		make_work_order(SHAFT, 1, at("09:30"), submit=False)
		plan = make_production_plan([(PIN, 1, at("09:45"))])
		self.assertFalse(plan.get(mb.CLASHES_FIELD))

	def test_planned_times_stored_by_capacity_planning_are_used(self):
		wo = make_work_order(SHAFT, 1, at("09:30"))
		op = frappe.get_all("Work Order Operation", filters={"parent": wo.name}, pluck="name")[0]
		frappe.db.set_value(
			"Work Order Operation", op, {"planned_start_time": at("14:00"), "planned_end_time": at("15:00")}
		)
		self.assertFalse(
			make_production_plan([(PIN, 1, at("09:45"))]).get(mb.CLASHES_FIELD)
		)  # computed time would clash
		self.assertIn(wo.name, make_production_plan([(PIN, 1, at("14:30"))]).get(mb.CLASHES_FIELD))

	def test_another_open_plan_holds_the_machine(self):
		first = make_production_plan([(SHAFT, 1, at("09:00"))], submit=True)
		second = make_production_plan([(PIN, 1, at("09:15"))])
		self.assertIn(first.name, second.get(mb.CLASHES_FIELD))

	# ---- modes ----
	def test_soft_block_needs_a_reason_to_submit(self):
		set_param(mb.MODE_FIELD, mb.SOFT)
		plan = make_production_plan([(SHAFT, 1, at("09:00")), (PIN, 1, at("09:30"))])
		with self.assertRaises(frappe.ValidationError) as caught:
			plan.submit()
		self.assertIn(f"[{mb.RULE_CODE}]", str(caught.exception))
		log_override(mb.RULE_CODE, "Production Plan", plan.name, "double-booked", "Second shift will run it")
		plan = frappe.get_doc("Production Plan", plan.name)
		plan.submit()
		self.assertEqual(plan.docstatus, 1)

	def test_soft_block_only_warns_when_reasons_are_off(self):
		set_param(mb.MODE_FIELD, mb.SOFT)
		set_param(mb.ENFORCE_FIELD, 0)
		plan = make_production_plan([(SHAFT, 1, at("09:00")), (PIN, 1, at("09:30"))])
		plan.submit()
		self.assertEqual(plan.docstatus, 1)

	def test_hard_block_saves_the_draft_but_refuses_submit_even_with_a_reason(self):
		set_param(mb.MODE_FIELD, mb.HARD)
		plan = make_production_plan([(SHAFT, 1, at("09:00")), (PIN, 1, at("09:30"))])
		self.assertTrue(frappe.db.exists("Production Plan", plan.name))  # the draft is kept
		log_override(
			mb.RULE_CODE, "Production Plan", plan.name, "double-booked", "Planner insists on this slot"
		)
		with self.assertRaises(frappe.ValidationError) as caught:
			frappe.get_doc("Production Plan", plan.name).submit()
		self.assertIn("Hard Block", str(caught.exception))

	def test_hard_block_submits_a_plan_without_clashes(self):
		set_param(mb.MODE_FIELD, mb.HARD)
		plan = make_production_plan([(SHAFT, 1, at("09:00")), (PIN, 1, at("10:00"))])
		plan.submit()
		self.assertEqual(plan.docstatus, 1)

	def test_form_asks_for_a_reason_only_in_soft_block(self):
		plan = make_production_plan([(SHAFT, 1, at("09:00")), (PIN, 1, at("09:30"))])
		set_param(mb.MODE_FIELD, mb.SOFT)
		self.assertEqual(mb.booking_gate_check(plan.name)["rule_code"], mb.RULE_CODE)
		set_param(mb.MODE_FIELD, mb.HARD)
		self.assertIsNone(mb.booking_gate_check(plan.name))
		set_param(mb.MODE_FIELD, mb.ADVISORY)
		self.assertIsNone(mb.booking_gate_check(plan.name))

	# ---- set-up ----
	def test_mode_must_be_one_of_the_three(self):
		with self.assertRaises(frappe.ValidationError):
			validate_production_params(frappe._dict({mb.MODE_FIELD: "Sometimes"}))

	def test_hooks_registered(self):
		events = frappe.get_hooks("doc_events")["Production Plan"]
		self.assertIn("pepl_os.pepl_production.machine_booking.check_on_save", events["validate"])
		self.assertIn("pepl_os.pepl_production.machine_booking.check_on_submit", events["before_submit"])

	def test_parameter_seeded_soft_block(self):
		self.assertIsNotNone(stored_single("PEPL System Parameters", mb.MODE_FIELD))
