"""C3a-X3 - Daily OEE per machine from the submitted Shift Production Entries."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_governance.access_matrix import MATRIX_DOCTYPES
from pepl_os.pepl_production import oee
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
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param, set_single, stored_single

DAY = "T-OEE Day"  # 08:00-16:30, 30 min break = 480 planned minutes
NIGHT = "T-OEE Night"  # 22:00-06:00, 30 min break = 450 planned minutes
MILL = "T-OEE MILL-01"
OP1, OP2 = "T-OEE-OP1", "T-OEE-OP2"
NO_LOAD = "T-OEE No Load"  # Planned
SPINDLE = "T-OEE Spindle"  # Unplanned, breakdown
WAIT = "T-OEE Waiting"  # Unplanned
PM = "T-OEE PM"  # PM / Calibration
YESTERDAY = add_days(today(), -1)


def _down(category, start, end):
	return {"downtime_category": category, "from_time": start, "to_time": end}


class TestDailyOEE(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_shift(NIGHT, "22:00:00", "06:00:00", 30)
		make_workstation(MILL, "T-OEE MILL")
		make_operator(OP1, pin="1111")
		make_operator(OP2, pin="2222")
		make_downtime_category(NO_LOAD, "Planned", 0)
		make_downtime_category(SPINDLE, "Unplanned", 1)
		make_downtime_category(WAIT, "Unplanned", 0)
		make_downtime_category(PM, "PM / Calibration", 0)
		# 10 pieces at 6 standard minutes a piece (Job Card: 60 minutes for 10)
		cls.card = make_job_card(MILL, "T-OEE-JC", qty=10, minutes_per_piece=6).name

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")
		set_param(oee.EXCLUDE_PM_FIELD, 1)
		set_param(oee.TARGET_FIELD, 65)
		set_single("Manufacturing Settings", "overproduction_percentage_for_work_order", 0)

	def _block(self, start, end, good, rejected=0):
		row = {"job_card": self.card, "from_time": start, "to_time": end, "good_qty": good}
		if rejected:
			row.update({"rejected_qty": rejected, "rejection_reason": "Undersize"})
		return row

	def _submit(self, operator=OP1, shift=DAY, production=(), downtime=()):
		doc = make_spr(MILL, shift, operator, YESTERDAY, production=production, downtime=downtime)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def _standard_day(self):
		"""240 min run (8 good + 2 rejected), 60 planned stop, 60 breakdown, 120 waiting = 480."""
		return self._submit(
			production=[self._block("08:00", "12:00", 8, 2)],
			downtime=[
				_down(NO_LOAD, "12:00", "13:00"),
				_down(SPINDLE, "13:00", "14:00"),
				_down(WAIT, "14:00", "16:00"),
			],
		)

	def _record(self):
		name = oee.record_name(MILL, YESTERDAY)
		return frappe.get_doc(oee.DOCTYPE, name) if name else None

	# ---- the figures ----
	def test_submitting_an_entry_builds_the_day(self):
		self._standard_day()
		rec = self._record()
		self.assertIsNotNone(rec)
		self.assertEqual((rec.planned_minutes, rec.planned_stop_minutes), (480, 60))
		self.assertEqual(rec.planned_production_minutes, 420)
		self.assertEqual((rec.run_minutes, rec.unplanned_stop_minutes), (240, 180))
		self.assertEqual((rec.breakdown_count, rec.breakdown_minutes), (1, 60))
		self.assertEqual((rec.good_qty, rec.rejected_qty, rec.ideal_minutes), (8, 2, 60))
		self.assertAlmostEqual(rec.availability, 57.14, places=2)  # 240 / 420
		self.assertAlmostEqual(rec.performance, 25.0, places=2)  # 10 x 6 / 240
		self.assertAlmostEqual(rec.quality, 80.0, places=2)  # 8 / 10
		self.assertAlmostEqual(rec.oee, 11.43, places=2)
		self.assertEqual((rec.target, rec.below_target), (65, 1))
		self.assertEqual(rec.entries, 1)

	def test_pm_left_out_of_planned_time_when_the_parameter_is_on(self):
		self._submit(
			production=[self._block("08:00", "12:00", 8)],
			downtime=[_down(PM, "12:00", "13:00"), _down(NO_LOAD, "13:00", "16:00")],
		)
		rec = self._record()
		self.assertEqual(
			(rec.pm_minutes, rec.planned_production_minutes, rec.unplanned_stop_minutes), (60, 240, 0)
		)
		self.assertAlmostEqual(rec.availability, 100.0, places=2)

	def test_pm_counts_as_a_stop_when_the_parameter_is_off(self):
		set_param(oee.EXCLUDE_PM_FIELD, 0)
		self._submit(
			production=[self._block("08:00", "12:00", 8)],
			downtime=[_down(PM, "12:00", "13:00"), _down(NO_LOAD, "13:00", "16:00")],
		)
		rec = self._record()
		self.assertEqual((rec.planned_production_minutes, rec.unplanned_stop_minutes), (300, 60))
		self.assertAlmostEqual(rec.availability, 80.0, places=2)

	def test_two_operators_in_one_shift_count_the_shift_once(self):
		self._submit(OP1, production=[self._block("08:00", "12:00", 4)])
		self._submit(OP2, production=[self._block("12:00", "16:00", 4)])
		rec = self._record()
		self.assertEqual((rec.entries, rec.planned_minutes, rec.run_minutes), (2, 480, 480))

	def test_two_shifts_add_their_planned_minutes(self):
		self._submit(shift=DAY, downtime=[_down(NO_LOAD, "08:00", "16:00")])
		self._submit(shift=NIGHT, downtime=[_down(NO_LOAD, "22:00", "05:30")])
		rec = self._record()
		self.assertEqual(rec.planned_minutes, 930)
		self.assertIn(NIGHT, rec.shifts)

	def test_performance_above_100_is_capped_in_oee_and_noted(self):
		# 10 pieces x 6 min = 60 standard minutes made in 30 minutes
		self._submit(
			production=[self._block("08:00", "08:30", 10)], downtime=[_down(NO_LOAD, "08:30", "16:00")]
		)
		rec = self._record()
		self.assertAlmostEqual(rec.performance, 200.0, places=2)
		self.assertAlmostEqual(
			rec.oee, rec.availability, places=2
		)  # quality 100 %, performance used as 100 %
		self.assertIn("100 %", rec.notes)

	def test_target_comes_from_system_parameters(self):
		set_param(oee.TARGET_FIELD, 10)
		self._standard_day()
		rec = self._record()
		self.assertEqual((rec.target, rec.below_target), (10, 0))

	# ---- when it is built ----
	def test_cancelling_the_last_entry_removes_the_day(self):
		doc = self._submit(downtime=[_down(NO_LOAD, "08:00", "16:00")])
		self.assertIsNotNone(self._record())
		doc.reload()
		doc.cancel()
		self.assertIsNone(self._record())

	def test_cancelling_one_of_two_entries_rebuilds_the_day(self):
		first = self._submit(OP1, production=[self._block("08:00", "12:00", 4)])
		self._submit(OP2, production=[self._block("12:00", "16:00", 4)])
		first.reload()
		first.cancel()
		rec = self._record()
		self.assertEqual((rec.entries, rec.run_minutes), (1, 240))

	def test_nightly_job_builds_yesterday(self):
		self._submit(downtime=[_down(NO_LOAD, "08:00", "16:00")])
		frappe.delete_doc(oee.DOCTYPE, oee.record_name(MILL, YESTERDAY), ignore_permissions=True, force=True)
		self.assertIn(MILL, " ".join(oee.daily_oee()))
		self.assertIsNotNone(self._record())

	def test_rebuild_for_a_date_range(self):
		self._submit(downtime=[_down(NO_LOAD, "08:00", "16:00")])
		frappe.delete_doc(oee.DOCTYPE, oee.record_name(MILL, YESTERDAY), ignore_permissions=True, force=True)
		self.assertGreaterEqual(oee.rebuild_oee(add_days(YESTERDAY, -1), YESTERDAY)["records"], 1)
		self.assertIsNotNone(self._record())
		with self.assertRaises(frappe.ValidationError):
			oee.rebuild_oee(YESTERDAY, add_days(YESTERDAY, -3))

	def test_rebuild_is_for_the_production_manager(self):
		frappe.set_user(make_user("pepl.test.oee.foreman@example.com", ["Manufacturing User"]))
		with self.assertRaises(frappe.PermissionError):
			oee.rebuild_oee(YESTERDAY)

	def test_a_failure_never_stops_the_shift_entry(self):
		with patch.object(oee, "build_day", side_effect=RuntimeError("boom")):
			doc = self._submit(downtime=[_down(NO_LOAD, "08:00", "16:00")])
		self.assertEqual(doc.docstatus, 1)
		self.assertIsNone(self._record())

	# ---- set-up ----
	def test_records_are_built_not_typed(self):
		meta = frappe.get_meta(oee.DOCTYPE)
		self.assertTrue(meta.in_create)
		self.assertTrue(
			all(f.read_only for f in meta.fields if f.fieldtype not in ("Section Break", "Column Break"))
		)
		foreman = make_user("pepl.test.oee.reader@example.com", ["Manufacturing User"])
		self.assertTrue(frappe.has_permission(oee.DOCTYPE, "read", user=foreman))
		self.assertFalse(frappe.has_permission(oee.DOCTYPE, "write", user=foreman))
		self.assertIn(oee.DOCTYPE, {doctype for _area, doctype, _label in MATRIX_DOCTYPES})

	def test_target_must_be_a_percentage(self):
		with self.assertRaises(frappe.ValidationError):
			validate_production_params(frappe._dict({oee.TARGET_FIELD: 120}))

	def test_nightly_job_registered_and_target_seeded(self):
		self.assertIn("pepl_os.pepl_production.oee.daily_oee", frappe.get_hooks("scheduler_events")["daily"])
		self.assertIsNotNone(stored_single("PEPL System Parameters", oee.TARGET_FIELD))
