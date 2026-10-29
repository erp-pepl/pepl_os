"""C3a-P5 - Entry aids on the Shift Production Entry: gaps, Job Cards left, speed against standard, open cards."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_production import spr, spr_aids
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

DAY = "T-P5 Day"  # 08:00-16:30, 30 min break
NIGHT = "T-P5 Night"  # 22:00-06:00, 30 min break
MILL = "T-P5 MILL-01"
OP1, OP2 = "T-P5-OP1", "T-P5-OP2"
NO_LOAD = "T-P5 No Load"
YESTERDAY = add_days(today(), -1)
EARLIER = add_days(today(), -2)


def _texts(rows):
	return " | ".join(r["text"] for r in rows)


def _clock_gaps(doc):
	return [(spr._clock(a), spr._clock(b), m) for a, b, m in spr_aids.gaps(doc)]


class TestSPREntryAids(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_shift(NIGHT, "22:00:00", "06:00:00", 30)
		make_workstation(MILL, "T-P5 MILL")
		make_operator(OP1, pin="1111")
		make_operator(OP2, pin="2222")
		make_downtime_category(NO_LOAD, "Planned", 0)

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")
		set_param(spr_aids.LOW_FIELD, 0.8)
		set_param(spr_aids.HIGH_FIELD, 1.2)
		self.card = make_job_card(MILL, "T-P5-JC", qty=10, minutes_per_piece=6).name

	def _entry(self, production=(), downtime=(), operator=OP1, day=YESTERDAY, shift=DAY):
		return make_spr(MILL, shift, operator, day, production=production, downtime=downtime).insert(
			ignore_permissions=True
		)

	def _block(self, start, end, good, rejected=0):
		row = {"job_card": self.card, "from_time": start, "to_time": end, "good_qty": good}
		if rejected:
			row.update({"rejected_qty": rejected, "rejection_reason": "Undersize"})
		return row

	# ---- gaps ----
	def test_gaps_in_the_shift(self):
		doc = self._entry(
			[self._block("08:00", "10:00", 10)],
			[{"downtime_category": NO_LOAD, "from_time": "10:30", "to_time": "12:00"}],
		)
		self.assertEqual(_clock_gaps(doc), [("10:00", "10:30", 30), ("12:00", "16:30", 270)])
		rows = spr_aids.aid_rows(doc)
		self.assertIn("2 gap(s) in the shift not covered by any row, 300 min", rows[0]["text"])
		self.assertIn("30-minute break is one of them", rows[0]["text"])
		self.assertEqual(rows[0]["colour"], "orange")  # 300 > 30 break + 15 allowed
		self.assertIn("Not covered: 12:00-16:30 (270 min)", _texts(rows))

	def test_the_other_operators_entry_covers_its_part(self):
		self._entry(
			[], [{"downtime_category": NO_LOAD, "from_time": "12:00", "to_time": "16:30"}], operator=OP2
		)
		doc = self._entry(
			[self._block("08:00", "10:00", 10)],
			[{"downtime_category": NO_LOAD, "from_time": "10:30", "to_time": "12:00"}],
		)
		self.assertEqual(_clock_gaps(doc), [("10:00", "10:30", 30)])
		self.assertEqual(spr_aids.aid_rows(doc)[0]["colour"], "gray")  # just the break

	def test_every_minute_covered(self):
		doc = self._entry(
			[self._block("08:00", "10:00", 10)],
			[{"downtime_category": NO_LOAD, "from_time": "10:00", "to_time": "16:30"}],
		)
		rows = spr_aids.aid_rows(doc)
		self.assertEqual(
			(rows[0]["text"], rows[0]["colour"]), ("Every minute of the shift is covered by a row", "green")
		)
		self.assertEqual(spr_aids.get_spr_aids(doc.name)["gaps"], [])

	def test_night_shift_gap_rows_to_add(self):
		doc = self._entry([self._block("22:00", "02:00", 10)], shift=NIGHT, day=YESTERDAY)
		self.assertEqual(spr_aids.gap_rows_to_add(doc), [{"from_time": "02:00:00", "to_time": "06:00:00"}])
		self.assertEqual(
			spr_aids.get_spr_aids(doc.name)["gaps"], [{"from_time": "02:00:00", "to_time": "06:00:00"}]
		)

	# ---- Job Cards ----
	def test_what_is_left_on_the_job_card(self):
		doc = self._entry([self._block("08:00", "09:00", 6, 1)])
		self.assertIn(
			f"Job Card {self.card}: target 10, done before 0, this entry 6 - 4 left",
			_texts(spr_aids.aid_rows(doc)),
		)

	def test_done_on_earlier_entries_counts(self):
		first = self._entry(
			[self._block("08:00", "09:00", 4)],
			[{"downtime_category": NO_LOAD, "from_time": "09:00", "to_time": "16:00"}],
			day=EARLIER,
		)
		first.submit()
		doc = self._entry([self._block("08:00", "09:00", 6)])
		line = next(r for r in spr_aids.aid_rows(doc) if r["text"].startswith("Job Card"))
		self.assertIn("done before 4, this entry 6 - finished", line["text"])
		self.assertEqual(line["colour"], "green")

	# ---- speed ----
	def test_slow_row_is_orange(self):
		doc = self._entry([self._block("08:00", "09:00", 6, 1)])  # 7 x 6 = 42 min in 60
		line = next(r for r in spr_aids.aid_rows(doc) if r["text"].startswith("Row 1"))
		self.assertIn(
			"Row 1: 7 piece(s) x 6 min standard = 42 min; took 60 min - 70% of standard speed", line["text"]
		)
		self.assertIn("slower than standard x 1.2: check the time and the quantity", line["text"])
		self.assertEqual(line["colour"], "orange")
		set_param(spr_aids.HIGH_FIELD, 1.5)  # 60 / 42 = 1.43 is inside the wider band
		line = next(r for r in spr_aids.aid_rows(doc) if r["text"].startswith("Row 1"))
		self.assertEqual(line["colour"], "green")

	def test_fast_row_is_orange(self):
		doc = self._entry([self._block("08:00", "08:30", 10)])  # 10 x 6 = 60 min in 30: cycle x 0.5
		line = next(r for r in spr_aids.aid_rows(doc) if r["text"].startswith("Row 1"))
		self.assertIn("200% of standard speed - faster than standard x 0.8", line["text"])
		self.assertEqual(line["colour"], "orange")

	def test_row_at_standard_speed_is_green(self):
		doc = self._entry([self._block("08:00", "09:00", 10)])  # 10 x 6 = 60 min in 60
		line = next(r for r in spr_aids.aid_rows(doc) if r["text"].startswith("Row 1"))
		self.assertIn("100% of standard speed", line["text"])
		self.assertEqual(line["colour"], "green")
		set_param(spr_aids.HIGH_FIELD, 1.0)
		line = next(r for r in spr_aids.aid_rows(doc) if r["text"].startswith("Row 1"))
		self.assertEqual(line["colour"], "green")  # exactly on the line is not slow

	# ---- open Job Cards ----
	def test_open_job_cards_on_the_machine(self):
		other = make_job_card(MILL, "T-P5-JD", qty=5, minutes_per_piece=6).name
		doc = self._entry([self._block("08:00", "09:00", 6)])
		text = _texts(spr_aids.aid_rows(doc))
		self.assertIn(f"Open on this machine: Job Card {other}", text)
		self.assertNotIn(f"Open on this machine: Job Card {self.card}", text)  # already on the entry

	# ---- Shift panel fix ----
	def test_shift_panel_quantities_without_decimals(self):
		# Regression: the X1 Shift panel said "Good 6.0 · Rejected 1.0 (14.29%)".
		doc = self._entry([self._block("08:00", "09:00", 6, 1)])
		self.assertIn("Good 6 · Rejected 1 (14.29%)", _texts(spr.get_spr_panel(doc.name)["rows"]))

	# ---- set-up ----
	def test_panel_hooked_on_the_form(self):
		path = frappe.get_app_path(
			"pepl_os",
			"pepl_production",
			"doctype",
			"pepl_shift_production_entry",
			"pepl_shift_production_entry.js",
		)
		with open(path) as f:
			self.assertIn("spr_aids.get_spr_aids", f.read())
