"""C3a-C1 - Production configuration: OEE factor targets, standard-time governance, settings review, downtime
category cleanup, one measure for slow / fast runs."""

import frappe
from frappe.utils import add_days, today

from pepl_os.patches.v0_40 import remove_spr_slow_speed_parameter as slow_patch
from pepl_os.pepl_production import config
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
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param, stored_single

DAY = "T-C1 Day"  # 08:00-16:30, 30 min break = 480 planned minutes
MILL = "T-C1 MILL-01"
OP = "T-C1-OP1"
NO_LOAD = "T-C1 No Load"  # Planned
NO_LOAD_TWIN = "T-C1 No-load"  # the same stop typed differently
WAITING = "T-C1 Waiting"  # Unplanned
UNUSED = "T-C1 Never Used"
YESTERDAY = add_days(today(), -1)


class TestProductionConfiguration(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(MILL, "T-C1 MILL")
		make_operator(OP, pin="1111")
		make_downtime_category(NO_LOAD, "Planned", 0)
		make_downtime_category(NO_LOAD_TWIN, "Planned", 0)
		make_downtime_category(WAITING, "Unplanned", 0)
		make_downtime_category(UNUSED, "Planned", 0)

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")
		for _label, field, default in config.FACTOR_FIELDS:
			set_param(field, default)

	def _shift_entry(self, category=NO_LOAD, good=38, rejected=2):
		card = make_job_card(MILL, "T-C1-JC", qty=40, minutes_per_piece=6).name
		row = {"job_card": card, "from_time": "08:00", "to_time": "12:00", "good_qty": good}
		if rejected:
			row.update({"rejected_qty": rejected, "rejection_reason": "Undersize"})
		doc = make_spr(
			MILL,
			DAY,
			OP,
			YESTERDAY,
			production=[row],
			downtime=[{"downtime_category": category, "from_time": "12:00", "to_time": "16:00"}],
		).insert(ignore_permissions=True)
		doc.submit()
		return doc

	# ---- settings ----
	def test_new_settings_start_with_their_defaults(self):
		self.assertEqual(float(stored_single("PEPL System Parameters", config.LOOKBACK_FIELD)), 90)
		self.assertEqual(stored_single("PEPL System Parameters", config.BASIS_FIELD), "Median")
		settings = config.std_time_settings()
		self.assertEqual(
			(settings.lookback_days, settings.min_runs, settings.basis, settings.max_change_percent),
			(90, 5, "Median", 20),
		)
		self.assertEqual(settings.approver_role, "PEPL Production Manager")  # empty = the default role
		self.assertEqual((settings.band_low, settings.band_high), (0.8, 1.2))

	def test_settings_are_validated(self):
		for values in (
			{config.AVAILABILITY_FIELD: 0},
			{config.QUALITY_FIELD: 150},
			{config.LOOKBACK_FIELD: 3},
			{config.MIN_RUNS_FIELD: 0},
			{config.BASIS_FIELD: "Mode"},
			{config.MAX_CHANGE_FIELD: 0},
		):
			with self.assertRaises(frappe.ValidationError, msg=str(values)):
				validate_production_params(frappe._dict(values))
		validate_production_params(frappe._dict({config.LOOKBACK_FIELD: 30, config.BASIS_FIELD: "Average"}))

	def test_the_v0_39_slow_speed_field_is_gone(self):
		self.assertIsNone(
			frappe.get_meta("PEPL System Parameters").get_field("custom_spr_slow_speed_percent")
		)
		slow_patch.execute()  # safe to run again
		self.assertFalse(
			frappe.db.exists("Custom Field", {"dt": "PEPL System Parameters", "fieldname": slow_patch.FIELD})
		)

	# ---- OEE thresholds ----
	def test_factors_below_their_targets(self):
		self.assertEqual(
			config.factors_below(70, 96, 95), "Availability 70 % (target 90 %), Quality 95 % (target 99 %)"
		)
		self.assertEqual(config.factors_below(90, 95, 99), "")  # on the target is not below it

	def test_daily_oee_names_the_factor_that_let_the_day_down(self):
		self._shift_entry()  # 40 pieces x 6 min in 240 min run of 240 planned: A 100, P 100, Q 95
		record = frappe.get_all(
			"PEPL OEE Daily",
			filters={"workstation": MILL, "oee_date": YESTERDAY},
			fields=["availability", "performance", "quality", "factors_below_target"],
		)[0]
		self.assertEqual((record.availability, record.performance, record.quality), (100, 100, 95))
		self.assertEqual(record.factors_below_target, "Quality 95 % (target 99 %)")

	# ---- settings review ----
	def test_settings_review(self):
		set_param(config.LOOKBACK_FIELD, 60)
		rows = {r.fieldname: r for r in config.settings_rows()}
		self.assertEqual(rows[config.LOOKBACK_FIELD].status, "Changed from default")
		self.assertEqual(rows[config.LOOKBACK_FIELD].value, "60")
		self.assertEqual(rows[config.AVAILABILITY_FIELD].status, "Default, to confirm with PEPL")
		for name in ("skill_check_mode", "cycle_deviation_threshold_high", "disable_capacity_planning"):
			self.assertIn(name, rows)
		self.assertTrue(frappe.db.exists("Report", "PEPL Production Settings"))
		self.assertTrue(frappe.db.exists("Report", "PEPL Downtime Category Review"))

	# ---- downtime categories ----
	def test_review_finds_look_alikes_and_unused(self):
		self._shift_entry(NO_LOAD)
		rows = {r.category: r for r in config.review_rows()}
		self.assertIn(f"Looks like the same stop as {NO_LOAD_TWIN}", rows[NO_LOAD].notes)
		self.assertEqual((rows[NO_LOAD].recent, rows[NO_LOAD].total), (1, 1))
		self.assertIn("Never used", rows[UNUSED].notes)
		panel = config.get_downtime_category_review(NO_LOAD)
		self.assertIn("Used 1 time(s) in the last 90 days", panel["rows"][0]["text"])
		self.assertTrue(panel["can_merge"])

	def test_merge_moves_the_rows_and_switches_the_old_one_off(self):
		entry = self._shift_entry(NO_LOAD_TWIN)
		result = config.merge_downtime_category(NO_LOAD_TWIN, NO_LOAD)
		self.assertEqual((result["moved"], result["rebuilt_days"]), (1, 1))
		self.assertEqual(
			frappe.db.get_value("PEPL SPR Downtime", {"parent": entry.name}, "downtime_category"), NO_LOAD
		)
		self.assertEqual(frappe.db.get_value(config.CATEGORY, NO_LOAD_TWIN, "is_active"), 0)
		self.assertIn(
			f"Merged into {NO_LOAD}", frappe.db.get_value(config.CATEGORY, NO_LOAD_TWIN, "description")
		)
		self.assertTrue(frappe.db.exists("PEPL OEE Daily", {"workstation": MILL, "oee_date": YESTERDAY}))

	def test_merge_refuses_a_different_kind_of_stop(self):
		with self.assertRaisesRegex(frappe.ValidationError, "same kind"):
			config.merge_downtime_category(NO_LOAD, WAITING)
		with self.assertRaises(frappe.ValidationError):
			config.merge_downtime_category(NO_LOAD, NO_LOAD)

	def test_only_production_managers_merge(self):
		user = make_user("t-c1-plain@example.com", ["Manufacturing User"])
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			config.merge_downtime_category(NO_LOAD_TWIN, NO_LOAD)

	def test_merge_button_on_the_form(self):
		path = frappe.get_app_path(
			"pepl_os", "pepl_production", "doctype", "pepl_downtime_category", "pepl_downtime_category.js"
		)
		with open(path) as f:
			self.assertIn("config.merge_downtime_category", f.read())
