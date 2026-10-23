"""C3a-X4 - Weekly MTBF, MTTR and CPC per machine from the submitted Shift Production Entries."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, getdate, today

from pepl_os.pepl_governance.access_matrix import MATRIX_DOCTYPES
from pepl_os.pepl_production import machine_week as mw
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_downtime_category,
	make_item,
	make_job_card,
	make_operator,
	make_shift,
	make_spr,
	make_workstation,
	test_warehouse,
)
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param, set_single

DAY = "T-MW Day"  # 08:00-16:30, 30 min break = 480 planned minutes
MILL = "T-MW MILL-01"
GROUP = "T-MW MILL"
OP1 = "T-MW-OP1"
NO_LOAD = "T-MW No Load"  # Planned
SPINDLE = "T-MW Spindle"  # Unplanned, breakdown
OIL = "T-MW-COOLANT"
MONDAY = mw.week_start(add_days(today(), -7))  # last week, Monday
TUESDAY = add_days(MONDAY, 1)


def _down(category, start, end):
	return {"downtime_category": category, "from_time": start, "to_time": end}


class TestMachineWeek(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(MILL, GROUP)
		make_operator(OP1, pin="1111")
		make_downtime_category(NO_LOAD, "Planned", 0)
		make_downtime_category(SPINDLE, "Unplanned", 1)
		make_item(OIL, st.CONSUMABLES, valuation_rate=10)
		# 10 pieces at 6 standard minutes; the BOM's raw material costs 10 a piece
		cls.card = make_job_card(MILL, "T-MW-JC", qty=10, minutes_per_piece=6).name
		receipt = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"purpose": "Material Receipt",
				"company": TEST_COMPANY,
				"set_posting_time": 1,
				"posting_date": add_days(MONDAY, -10),
				"items": [
					{
						"item_code": OIL,
						"qty": 100,
						"t_warehouse": test_warehouse("Consumables Stores"),
						"basic_rate": 10,
					}
				],
			}
		).insert(ignore_permissions=True)
		receipt.submit()

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")
		set_param(mw.OVERHEAD_FIELD, 10)
		set_single("Manufacturing Settings", "overproduction_percentage_for_work_order", 0)
		frappe.db.delete("PEPL Machine Hour Rate", {"parent": mw.SYSTEM_PARAMETERS, "machine_group": GROUP})
		frappe.get_doc(
			{
				"doctype": "PEPL Machine Hour Rate",
				"name": "t-mw-rate-mill",
				"parent": mw.SYSTEM_PARAMETERS,
				"parenttype": mw.SYSTEM_PARAMETERS,
				"parentfield": mw.RATES_FIELD,
				"machine_group": GROUP,
				"rate_per_hour": 600,
			}
		).db_insert()

	def _block(self, start, end, good, rejected=0):
		row = {"job_card": self.card, "from_time": start, "to_time": end, "good_qty": good}
		if rejected:
			row.update({"rejected_qty": rejected, "rejection_reason": "Undersize"})
		return row

	def _submit(self, day, production=(), downtime=(), consumables=()):
		doc = make_spr(MILL, DAY, OP1, day, production=production, downtime=downtime, consumables=consumables)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def _week(self):
		"""Monday: 4 h run (8 good, 2 rejected), 1 h breakdown. Tuesday: 30 min breakdown, 2 h run (2 good)."""
		self._submit(
			MONDAY,
			production=[self._block("08:00", "12:00", 8, 2)],
			downtime=[_down(SPINDLE, "12:00", "13:00"), _down(NO_LOAD, "13:00", "16:00")],
		)
		self._submit(
			TUESDAY,
			production=[self._block("08:30", "10:30", 2)],
			downtime=[_down(SPINDLE, "08:00", "08:30"), _down(NO_LOAD, "10:30", "16:00")],
		)

	def _record(self):
		name = mw.record_name(MILL, MONDAY)
		return frappe.get_doc(mw.DOCTYPE, name) if name else None

	def _material_per_piece(self):
		return mw._material_per_piece(frappe.db.get_value("Job Card", self.card, "bom_no"))

	# ---- MTBF / MTTR ----
	def test_mtbf_and_mttr_of_the_week(self):
		self._week()
		rec = self._record()
		self.assertEqual(getdate(rec.week_start), getdate(MONDAY))
		self.assertEqual((rec.entries, rec.run_minutes), (2, 360))
		self.assertEqual((rec.breakdown_count, rec.breakdown_minutes), (2, 90))
		self.assertAlmostEqual(rec.mtbf_hours, 3.0, places=2)  # 6 run hours / 2
		self.assertAlmostEqual(rec.mttr_minutes, 45.0, places=2)  # 90 / 2

	def test_a_week_without_breakdowns_says_so(self):
		self._submit(
			MONDAY, production=[self._block("08:00", "12:00", 4)], downtime=[_down(NO_LOAD, "12:00", "16:00")]
		)
		rec = self._record()
		self.assertEqual((rec.breakdown_count, rec.mtbf_hours, rec.mttr_minutes), (0, 0, 0))
		self.assertIn("No breakdown", rec.notes)

	# ---- CPC ----
	def test_cost_per_component(self):
		self._week()
		rec = self._record()
		self.assertEqual((rec.rate_per_hour, rec.overhead_percent), (600, 10))
		self.assertAlmostEqual(rec.machine_cost, 3600, places=2)  # 6 h x 600
		self.assertAlmostEqual(rec.conversion_cost, 3960, places=2)  # + 10 %
		self.assertAlmostEqual(rec.cpc, 396, places=2)  # / 10 good
		self.assertEqual(len(rec.items), 1)
		row = rec.items[0]
		material = self._material_per_piece() * 12  # 10 good + 2 rejected
		self.assertEqual((row.good_qty, row.rejected_qty, row.run_minutes), (10, 2, 360))
		self.assertAlmostEqual(row.material_cost, material, places=2)
		self.assertAlmostEqual(row.total_cost, (material + 3600) * 1.1, places=1)
		self.assertAlmostEqual(row.cost_per_piece, (material + 3600) * 1.1 / 10, places=1)

	def test_consumables_issued_by_the_entries_are_costed(self):
		self._submit(
			MONDAY,
			production=[self._block("08:00", "12:00", 4)],
			downtime=[_down(NO_LOAD, "12:00", "16:00")],
			consumables=[{"item_code": OIL, "qty": 3}],
		)
		rec = self._record()
		self.assertAlmostEqual(rec.consumables_cost, 30, places=2)  # 3 x 10
		self.assertAlmostEqual(rec.conversion_cost, (2400 + 30) * 1.1, places=2)

	def test_machine_hour_rate_falls_back_to_the_machine_own_rate(self):
		frappe.db.delete("PEPL Machine Hour Rate", {"parent": mw.SYSTEM_PARAMETERS, "machine_group": GROUP})
		frappe.db.set_value("Workstation", MILL, "hour_rate", 300)
		self.assertEqual(mw.machine_rate(MILL)[0], 300)
		frappe.db.set_value("Workstation", MILL, "hour_rate", 0)
		self._submit(
			MONDAY, production=[self._block("08:00", "12:00", 4)], downtime=[_down(NO_LOAD, "12:00", "16:00")]
		)
		self.assertIn("No machine-hour rate", self._record().notes)

	# ---- when it is built ----
	def test_cancelling_the_last_entry_of_the_week_removes_it(self):
		doc = self._submit(MONDAY, downtime=[_down(NO_LOAD, "08:00", "16:00")])
		self.assertIsNotNone(self._record())
		doc.reload()
		doc.cancel()
		self.assertIsNone(self._record())

	def test_weekly_job_builds_last_week(self):
		self._submit(MONDAY, downtime=[_down(NO_LOAD, "08:00", "16:00")])
		frappe.delete_doc(mw.DOCTYPE, mw.record_name(MILL, MONDAY), ignore_permissions=True, force=True)
		self.assertIn(MILL, " ".join(mw.weekly_machine_figures()))
		self.assertIsNotNone(self._record())

	def test_rebuild_for_a_date_range(self):
		self._submit(MONDAY, downtime=[_down(NO_LOAD, "08:00", "16:00")])
		frappe.delete_doc(mw.DOCTYPE, mw.record_name(MILL, MONDAY), ignore_permissions=True, force=True)
		self.assertGreaterEqual(mw.rebuild_machine_weeks(MONDAY, TUESDAY)["records"], 1)
		self.assertIsNotNone(self._record())
		with self.assertRaises(frappe.ValidationError):
			mw.rebuild_machine_weeks(TUESDAY, MONDAY)

	def test_rebuild_is_for_the_production_manager(self):
		frappe.set_user(make_user("pepl.test.mw.foreman@example.com", ["Manufacturing User"]))
		with self.assertRaises(frappe.PermissionError):
			mw.rebuild_machine_weeks(MONDAY)

	def test_a_failure_never_stops_the_shift_entry(self):
		with patch.object(mw, "build_week", side_effect=RuntimeError("boom")):
			doc = self._submit(MONDAY, downtime=[_down(NO_LOAD, "08:00", "16:00")])
		self.assertEqual(doc.docstatus, 1)
		self.assertIsNone(self._record())

	# ---- set-up ----
	def test_week_starts_on_monday(self):
		self.assertEqual(getdate(mw.week_start("2026-10-22")), getdate("2026-10-19"))  # a Thursday
		self.assertEqual(getdate(mw.week_start("2026-10-19")), getdate("2026-10-19"))

	def test_records_are_built_not_typed(self):
		meta = frappe.get_meta(mw.DOCTYPE)
		self.assertTrue(meta.in_create)
		self.assertTrue(
			all(f.read_only for f in meta.fields if f.fieldtype not in ("Section Break", "Column Break"))
		)
		self.assertIn(mw.DOCTYPE, {doctype for _area, doctype, _label in MATRIX_DOCTYPES})

	def test_weekly_job_registered(self):
		cron = frappe.get_hooks("scheduler_events")["cron"]
		self.assertIn("pepl_os.pepl_production.machine_week.weekly_machine_figures", cron["30 2 * * 1"])
