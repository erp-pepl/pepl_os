"""C3a-B7 - The Daily Stand-up, exception-only: only what needs attention, or "All clear"."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_production import oee, standup
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_downtime_category,
	make_job_card,
	make_operator,
	make_shift,
	make_spr,
	make_workstation,
)
from pepl_os.tests.utils import PEPLTestCase, set_param

DAY = "T-B7 Day"
MILL = "T-B7 MILL-01"  # works yesterday
LATHE = "T-B7 LATHE-01"  # worked 5 days ago, nothing yesterday
OP = "T-B7-OP1"
NO_LOAD = "T-B7 No Load"  # planned: never an exception
SPINDLE = "T-B7 Spindle"  # unplanned breakdown, 60 min
YESTERDAY = add_days(today(), -1)
QUIET_DAY = add_days(today(), -200)


def _down(category, start, end):
	return {"downtime_category": category, "from_time": start, "to_time": end}


class TestStandupExceptions(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(MILL, "T-B7 MILL")
		make_workstation(LATHE, "T-B7 LATHE")
		make_operator(OP, pin="7777")
		make_downtime_category(NO_LOAD, "Planned", 0)
		make_downtime_category(SPINDLE, "Unplanned", 1)
		cls.card = make_job_card(MILL, "T-B7-JC", qty=10, minutes_per_piece=6)

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")
		set_param(standup.EXCEPTION_FIELD, 1)
		set_param(standup.MIN_STOP_FIELD, 30)
		set_param(oee.TARGET_FIELD, 85)

	def _floor(self):
		"""Mill yesterday: 4 h run, 1 h spindle breakdown, 3 h no load (OEE far below 85 %). Lathe: 5 days ago."""
		doc = make_spr(
			MILL,
			DAY,
			OP,
			YESTERDAY,
			production=[
				{"job_card": self.card.name, "from_time": "08:00", "to_time": "12:00", "good_qty": 10}
			],
			downtime=[_down(SPINDLE, "12:00", "13:00"), _down(NO_LOAD, "13:00", "16:00")],
		).insert(ignore_permissions=True)
		doc.submit()
		lathe = make_spr(LATHE, DAY, OP, add_days(today(), -5), downtime=[_down(NO_LOAD, "08:00", "16:00")])
		lathe.insert(ignore_permissions=True)
		lathe.submit()

	def test_only_what_needs_attention(self):
		self._floor()
		doc = standup.build(YESTERDAY)
		page = doc.summary
		self.assertIn("thing(s) need attention", page)
		self.assertIn("1. Machines below the OEE target", page)
		self.assertIn(MILL, page)
		self.assertIn("Unplanned stops of 30 minutes or more", page)
		self.assertIn(SPINDLE, page)
		self.assertIn("breakdown", page)
		self.assertNotIn(NO_LOAD, page)  # a planned stop is not an exception
		self.assertIn("Machines without a shift entry", page)
		self.assertIn(LATHE, page)
		self.assertNotIn("Job work overdue", page)  # empty parts are left out
		self.assertGreaterEqual(doc.exceptions, 3)  # mill below target, spindle, lathe missing
		self.assertEqual(doc.all_clear, 0)
		self.assertIn(f"{doc.exceptions} exception(s)", standup.subject(doc))

	def test_today_s_oee_target_decides_below_target(self):
		# Regression (Check 48): the Daily OEE was built with 85 %; lowering the target afterwards must count
		self._floor()
		self.assertIn("Machines below the OEE target", standup.build(YESTERDAY).summary)
		set_param(oee.TARGET_FIELD, 1)
		page = standup.build(YESTERDAY).summary
		self.assertNotIn("Machines below the OEE target", page)
		self.assertIn("1 of 1 machines at or above the OEE target.", page)

	def test_short_stops_and_machines_on_target_are_left_out(self):
		set_param(oee.TARGET_FIELD, 1)  # every machine meets 1 %
		set_param(standup.MIN_STOP_FIELD, 90)  # the 60-minute breakdown is under it
		self._floor()
		page = standup.build(YESTERDAY).summary
		self.assertIn("1 of 1 machines at or above the OEE target.", page)
		self.assertNotIn("Machines below the OEE target", page)
		self.assertNotIn(SPINDLE, page)
		self.assertIn("1. Machines without a shift entry", page)  # numbering follows what is shown

	def _quiet(self, **parts):
		"""Build the stand-up for a day with nothing on it; the parts that read today's whole site (delivery risk,
		job work, LD, waiting work, rejections to weigh) give only what the test hands them (CI #55: the site
		keeps records of other tests)."""
		world = {
			"job_orders_at_risk": [],
			"job_work_overdue": [],
			"_ld_running": [],
			"_waiting": [],
			"_to_weigh": [],
		}
		world.update(parts)
		patches = [patch.object(standup, name, return_value=value) for name, value in world.items()]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)
		return standup.build(QUIET_DAY)

	def test_all_clear(self):
		doc = self._quiet()
		self.assertEqual((doc.exceptions, doc.all_clear), (0, 1))
		self.assertIn("all clear", doc.summary)
		self.assertIn("Nothing needs attention today.", doc.summary)
		self.assertTrue(standup.subject(doc).endswith("- all clear"))

	def test_ld_running_and_rejections_to_weigh(self):
		orders = [
			{
				"sales_order": "SO-LATE",
				"customer_name": "Railway",
				"days_late": 10,
				"ld_now": 10.0,
				"cap_amount": 100.0,
				"colour": "red",
			},
			{
				"sales_order": "SO-SOON",
				"customer_name": "Railway",
				"days_late": 0,
				"ld_now": 0.0,
				"cap_amount": 100.0,
				"colour": "orange",
			},
		]
		weigh = [frappe._dict(reference_name="SPR-T-0001")]
		doc = self._quiet(_ld_running=orders, _to_weigh=weigh)
		self.assertIn("Orders running LD", doc.summary)
		self.assertIn("SO-LATE", doc.summary)
		self.assertNotIn("SO-SOON", doc.summary.split("Orders running LD")[1].split("<p>")[0])
		self.assertIn("1 more order(s) start LD within the look-ahead days.", doc.summary)
		self.assertIn("Rejected pieces waiting for Stores to weigh", doc.summary)
		self.assertIn("SPR-T-0001", doc.summary)
		self.assertEqual(doc.exceptions, 2)

	def test_work_waiting_in_front_of_a_machine_group(self):
		waiting = [{"job_order": "JO-T-1", "operation": "Turning", "group": "LATHES", "hours": 30.0}]
		doc = self._quiet(_waiting=waiting)
		self.assertIn("Work waiting in front of a machine group", doc.summary)
		self.assertIn("JO-T-1", doc.summary)

	def test_a_failing_part_is_left_out_and_logged(self):
		before = frappe.db.count("Error Log")
		failing = patch.object(standup, "_waiting", side_effect=Exception("boom"))
		failing.start()
		self.addCleanup(failing.stop)
		world = {"job_orders_at_risk": [], "job_work_overdue": [], "_ld_running": [], "_to_weigh": []}
		for name, value in world.items():
			p = patch.object(standup, name, return_value=value)
			p.start()
			self.addCleanup(p.stop)
		doc = standup.build(QUIET_DAY)
		self.assertEqual(doc.all_clear, 1)
		self.assertGreater(frappe.db.count("Error Log"), before)

	def test_the_full_page_is_still_there(self):
		set_param(standup.EXCEPTION_FIELD, 0)
		self._floor()
		doc = standup.build(YESTERDAY)
		self.assertIn("1. Shop floor yesterday", doc.summary)
		self.assertIn(NO_LOAD, doc.summary)
		self.assertNotIn("need attention", doc.summary)
		self.assertNotIn("exception", standup.subject(doc))

	def test_settings(self):
		meta = frappe.get_meta("PEPL System Parameters")
		self.assertEqual(str(meta.get_field(standup.EXCEPTION_FIELD).default), "1")
		self.assertEqual(str(meta.get_field(standup.MIN_STOP_FIELD).default), "30")
		with self.assertRaisesRegex(frappe.ValidationError, "Minimum Stop Minutes"):
			validate_production_params(frappe._dict({standup.MIN_STOP_FIELD: -1}))
