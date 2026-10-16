"""C3a-X1 - Shift Production Entry (SPR): one machine, one shift, one operator.

Time blocks against Job Cards (good and rejected quantity), downtime by category, tool changes with a
photo, consumables used. On submit the blocks become Job Card time logs and the consumables one Material
Issue; cancel takes both back.
"""

import frappe
from frappe.utils import add_days, get_datetime, today

from pepl_os.pepl_governance.access_matrix import MATRIX_DOCTYPES
from pepl_os.pepl_production import spr
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.pepl_stores import consumables as cons
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	blank_png,
	make_downtime_category,
	make_file,
	make_item,
	make_job_card,
	make_operator,
	make_shift,
	make_spr,
	make_workstation,
	test_warehouse,
)
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param, set_single, stored_single

DAY = "T-SPR Day"  # 08:00-16:30, 30 min break = 480 planned minutes
NIGHT = "T-SPR Night"  # 22:00-06:00, 30 min break = 450 planned minutes
VMC = "T-SPR VMC-01"
LATHE = "T-SPR LATHE-01"
OP1, OP2 = "T-SPR-OP1", "T-SPR-OP2"
NO_LOAD = "T-SPR No Load"  # Planned
SPINDLE = "T-SPR Spindle"  # Unplanned breakdown
WAIT = "T-SPR Waiting"  # Unplanned
OIL = "T-SPR-COOLANT"
YESTERDAY = add_days(today(), -1)


def _down(category, start, end, **extra):
	return {"downtime_category": category, "from_time": start, "to_time": end, **extra}


def _whole_shift_no_load(**kwargs):
	"""An entry that explains the whole day shift as planned 'no load' - valid without any Job Card."""
	return make_spr(VMC, DAY, OP1, YESTERDAY, downtime=[_down(NO_LOAD, "08:00", "16:00")], **kwargs)


class SPRBase(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_shift(NIGHT, "22:00:00", "06:00:00", 30)
		make_workstation(VMC, "T-SPR VMC")
		make_workstation(LATHE, "T-SPR LATHE")
		make_operator(OP1, pin="1111")
		make_operator(OP2, pin="2222")
		make_downtime_category(NO_LOAD, "Planned", 0)
		make_downtime_category(SPINDLE, "Unplanned", 1)
		make_downtime_category(WAIT, "Unplanned", 0)
		make_item(OIL, st.CONSUMABLES, valuation_rate=10)

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 1)


class TestSPRTimes(SPRBase):
	def test_day_shift_times_and_minutes(self):
		doc = _whole_shift_no_load().insert(ignore_permissions=True)
		row = doc.downtime[0]
		self.assertEqual(get_datetime(row.from_datetime), get_datetime(f"{YESTERDAY} 08:00:00"))
		self.assertEqual(get_datetime(row.to_datetime), get_datetime(f"{YESTERDAY} 16:00:00"))
		self.assertEqual(row.minutes, 480)
		self.assertEqual((doc.planned_minutes, doc.downtime_minutes, doc.unaccounted_minutes), (480, 480, 0))

	def test_night_shift_rows_after_midnight_belong_to_the_next_day(self):
		doc = make_spr(VMC, NIGHT, OP1, YESTERDAY, downtime=[_down(NO_LOAD, "23:00", "01:30")]).insert(
			ignore_permissions=True
		)
		row = doc.downtime[0]
		self.assertEqual(get_datetime(row.from_datetime), get_datetime(f"{YESTERDAY} 23:00:00"))
		self.assertEqual(get_datetime(row.to_datetime), get_datetime(f"{today()} 01:30:00"))
		self.assertEqual(row.minutes, 150)

	def test_row_outside_the_shift_refused(self):
		doc = make_spr(VMC, DAY, OP1, YESTERDAY, downtime=[_down(NO_LOAD, "17:30", "18:00")])
		with self.assertRaisesRegex(frappe.ValidationError, "outside"):
			doc.insert(ignore_permissions=True)

	def test_grace_minutes_allow_a_little_before_and_after(self):
		doc = make_spr(VMC, DAY, OP1, YESTERDAY, downtime=[_down(NO_LOAD, "07:40", "16:50")])
		self.assertTrue(doc.insert(ignore_permissions=True).name)
		set_param("custom_spr_shift_grace_minutes", 0)
		late = make_spr(LATHE, DAY, OP1, YESTERDAY, downtime=[_down(NO_LOAD, "07:40", "08:30")])
		with self.assertRaisesRegex(frappe.ValidationError, "outside"):
			late.insert(ignore_permissions=True)

	def test_to_before_from_refused(self):
		doc = make_spr(VMC, DAY, OP1, YESTERDAY, downtime=[_down(NO_LOAD, "11:00", "10:00")])
		with self.assertRaisesRegex(frappe.ValidationError, "after"):
			doc.insert(ignore_permissions=True)

	def test_rows_of_one_entry_cannot_overlap(self):
		doc = make_spr(
			VMC,
			DAY,
			OP1,
			YESTERDAY,
			downtime=[_down(NO_LOAD, "08:00", "10:00"), _down(WAIT, "09:30", "10:30")],
		)
		with self.assertRaisesRegex(frappe.ValidationError, "overlaps"):
			doc.insert(ignore_permissions=True)

	def test_two_entries_on_one_machine_cannot_overlap(self):
		make_spr(VMC, DAY, OP1, YESTERDAY, downtime=[_down(NO_LOAD, "08:00", "12:00")]).insert(
			ignore_permissions=True
		)
		other = make_spr(VMC, DAY, OP2, YESTERDAY, downtime=[_down(NO_LOAD, "11:00", "13:00")])
		with self.assertRaisesRegex(frappe.ValidationError, "overlaps"):
			other.insert(ignore_permissions=True)
		elsewhere = make_spr(LATHE, DAY, OP2, YESTERDAY, downtime=[_down(NO_LOAD, "11:00", "13:00")])
		self.assertTrue(elsewhere.insert(ignore_permissions=True).name)  # another machine is fine

	def test_one_entry_per_machine_shift_day_and_operator(self):
		_whole_shift_no_load().insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "already"):
			make_spr(VMC, DAY, OP1, YESTERDAY, downtime=[_down(NO_LOAD, "16:00", "16:20")]).insert(
				ignore_permissions=True
			)

	def test_future_date_refused(self):
		doc = make_spr(VMC, DAY, OP1, add_days(today(), 1), downtime=[_down(NO_LOAD, "08:00", "09:00")])
		with self.assertRaisesRegex(frappe.ValidationError, "future"):
			doc.insert(ignore_permissions=True)

	def test_inactive_masters_refused(self):
		make_operator("T-SPR-OP-OFF", pin="3333", status="Inactive")
		doc = make_spr(VMC, DAY, "T-SPR-OP-OFF", YESTERDAY, downtime=[_down(NO_LOAD, "08:00", "09:00")])
		with self.assertRaisesRegex(frappe.ValidationError, "[Ii]nactive"):
			doc.insert(ignore_permissions=True)
		make_downtime_category("T-SPR Old Reason", "Unplanned", 0)
		frappe.db.set_value("PEPL Downtime Category", "T-SPR Old Reason", "is_active", 0)
		doc = make_spr(VMC, DAY, OP1, YESTERDAY, downtime=[_down("T-SPR Old Reason", "08:00", "09:00")])
		with self.assertRaisesRegex(frappe.ValidationError, "[Ii]nactive"):
			doc.insert(ignore_permissions=True)

	def test_downtime_row_carries_stop_type_and_breakdown(self):
		doc = make_spr(VMC, DAY, OP1, YESTERDAY, downtime=[_down(SPINDLE, "08:00", "09:00")]).insert(
			ignore_permissions=True
		)
		self.assertEqual((doc.downtime[0].stop_type, doc.downtime[0].is_breakdown), ("Unplanned", 1))


class TestSPRSubmitRules(SPRBase):
	def test_submit_refused_while_shift_minutes_are_unexplained(self):
		doc = make_spr(VMC, DAY, OP1, YESTERDAY, downtime=[_down(NO_LOAD, "08:00", "15:00")])
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.unaccounted_minutes, 60)
		with self.assertRaisesRegex(frappe.ValidationError, "60 minutes"):
			doc.submit()

	def test_submit_allowed_within_the_unexplained_limit(self):
		doc = make_spr(VMC, DAY, OP1, YESTERDAY, downtime=[_down(NO_LOAD, "08:00", "15:50")])
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.unaccounted_minutes, 10)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_tool_change_needs_a_photo_at_submit(self):
		tool = {"change_time": "10:00", "tool_description": "CNMG insert", "reason": "Worn out"}
		doc = _whole_shift_no_load(tools=[tool]).insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "photo"):
			doc.submit()
		doc.reload()
		doc.tool_changes[0].photo = make_file("t-spr-insert.png", blank_png())
		doc.save(ignore_permissions=True)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_photo_rule_can_be_switched_off(self):
		set_param("custom_spr_tool_photo_required", 0)
		tool = {"change_time": "10:00", "tool_description": "Drill 8 mm", "reason": "Broken"}
		doc = _whole_shift_no_load(tools=[tool]).insert(ignore_permissions=True)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_tool_change_time_inside_the_shift(self):
		tool = {"change_time": "19:00", "tool_description": "Tap M8", "reason": "Worn out"}
		with self.assertRaisesRegex(frappe.ValidationError, "outside"):
			_whole_shift_no_load(tools=[tool]).insert(ignore_permissions=True)

	def test_consumable_must_be_a_consumables_item(self):
		rod = make_item("T-SPR-ROD", st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10).name
		doc = _whole_shift_no_load(consumables=[{"item_code": rod, "qty": 1}])
		with self.assertRaisesRegex(frappe.ValidationError, "Consumables"):
			doc.insert(ignore_permissions=True)
		doc = _whole_shift_no_load(consumables=[{"item_code": OIL, "qty": 0}])
		with self.assertRaisesRegex(frappe.ValidationError, "more than 0"):
			doc.insert(ignore_permissions=True)

	def test_consumable_store_defaults_to_consumables_stores(self):
		doc = _whole_shift_no_load(consumables=[{"item_code": OIL, "qty": 2}]).insert(ignore_permissions=True)
		self.assertEqual(doc.consumables[0].warehouse, test_warehouse("Consumables Stores"))
		self.assertEqual(doc.consumables[0].uom, "Nos")


class TestSPRJobCards(SPRBase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.card = make_job_card(VMC, "T-SPR-JC", qty=10).name
		cls.lathe_card = make_job_card(LATHE, "T-SPR-JCL", qty=10).name

	def setUp(self):
		super().setUp()
		set_single("Manufacturing Settings", "overproduction_percentage_for_work_order", 0)

	def _produce(self, good, rejected=0, card=None, start="08:00", end="12:00", reason=None):
		row = {"job_card": card or self.card, "from_time": start, "to_time": end, "good_qty": good}
		if rejected:
			row.update({"rejected_qty": rejected, "rejection_reason": reason or "Undersize bore"})
		return row

	def _entry(self, *rows):
		return make_spr(
			VMC, DAY, OP1, YESTERDAY, production=list(rows), downtime=[_down(NO_LOAD, "12:00", "16:00")]
		)

	def test_row_takes_job_order_item_and_operation_from_the_job_card(self):
		doc = self._entry(self._produce(4)).insert(ignore_permissions=True)
		card = frappe.get_doc("Job Card", self.card)
		row = doc.production[0]
		self.assertEqual(
			(row.work_order, row.production_item, row.operation),
			(card.work_order, card.production_item, card.operation),
		)
		self.assertEqual((doc.production_minutes, doc.total_good_qty), (240, 4))

	def test_job_card_of_another_machine_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "machine"):
			self._entry(self._produce(4, card=self.lathe_card)).insert(ignore_permissions=True)

	def test_rejection_needs_a_reason_and_counts(self):
		row = self._produce(8, rejected=2)
		row["rejection_reason"] = ""
		with self.assertRaisesRegex(frappe.ValidationError, "reason"):
			self._entry(row).insert(ignore_permissions=True)
		doc = self._entry(self._produce(8, rejected=2)).insert(ignore_permissions=True)
		self.assertEqual((doc.total_good_qty, doc.total_rejected_qty, doc.rejection_percent), (8, 2, 20))

	def test_more_than_the_job_card_quantity_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "more than"):
			self._entry(self._produce(11)).insert(ignore_permissions=True)

	def test_submit_posts_time_logs_and_cancel_removes_them(self):
		doc = self._entry(
			self._produce(4, start="08:00", end="10:00"), self._produce(3, start="10:00", end="12:00")
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
		card = frappe.get_doc("Job Card", self.card)
		mine = [t for t in card.time_logs if t.custom_pepl_spr == doc.name]
		self.assertEqual(len(mine), 2)
		self.assertEqual(sum(t.completed_qty for t in mine), 7)
		self.assertEqual(get_datetime(mine[0].from_time), get_datetime(f"{YESTERDAY} 08:00:00"))
		self.assertEqual(card.total_completed_qty, 7)
		self.assertEqual(round(card.total_time_in_mins), 240)

		doc.cancel()
		card.reload()
		self.assertEqual([t for t in card.time_logs if t.custom_pepl_spr == doc.name], [])
		self.assertEqual(card.total_completed_qty, 0)

	def test_quantity_counts_what_the_job_card_already_has(self):
		first = self._entry(self._produce(6)).insert(ignore_permissions=True)
		first.submit()
		# 16:00-16:20 does not overlap the first entry (its last row ends at 16:00), so the quantity rule decides
		second = make_spr(VMC, DAY, OP2, YESTERDAY, production=[self._produce(5, start="16:00", end="16:20")])
		with self.assertRaisesRegex(frappe.ValidationError, "more than"):
			second.insert(ignore_permissions=True)

	def test_cancel_refused_once_the_job_card_is_submitted(self):
		doc = self._entry(self._produce(2)).insert(ignore_permissions=True)
		doc.submit()
		frappe.db.set_value("Job Card", self.card, "docstatus", 1)
		doc.reload()
		with self.assertRaisesRegex(frappe.ValidationError, "already submitted"):
			doc.cancel()

	def test_submitted_job_card_cannot_take_new_blocks(self):
		frappe.db.set_value("Job Card", self.card, "docstatus", 1)
		with self.assertRaisesRegex(frappe.ValidationError, "open Job Card"):
			self._entry(self._produce(2)).insert(ignore_permissions=True)


class TestSPRConsumables(SPRBase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"purpose": "Material Receipt",
				"company": TEST_COMPANY,
				"set_posting_time": 1,
				"posting_date": add_days(today(), -5),
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
		entry.submit()

	def test_submit_issues_consumables_against_the_machine_group(self):
		doc = _whole_shift_no_load(consumables=[{"item_code": OIL, "qty": 4}]).insert(ignore_permissions=True)
		doc.submit()
		self.assertTrue(doc.consumables_stock_entry)
		entry = frappe.get_doc("Stock Entry", doc.consumables_stock_entry)
		self.assertEqual((entry.docstatus, entry.purpose), (1, "Material Issue"))
		self.assertEqual(entry.custom_shift_production_entry, doc.name)
		self.assertEqual(str(entry.posting_date), str(YESTERDAY))
		line = entry.items[0]
		self.assertEqual((line.item_code, line.qty, line.custom_machine_group), (OIL, 4, "T-SPR VMC"))
		self.assertEqual(line.s_warehouse, test_warehouse("Consumables Stores"))

	def test_consumables_report_counts_the_issue(self):
		doc = _whole_shift_no_load(consumables=[{"item_code": OIL, "qty": 3}]).insert(ignore_permissions=True)
		doc.submit()
		f = {"company": TEST_COMPANY, "from_date": YESTERDAY, "to_date": YESTERDAY, "period": cons.DAY}
		rows, _p, _m = cons.consumables_issued(f)
		self.assertGreaterEqual(sum(r.qty for r in rows if r.group == OIL), 3)

	def test_cancel_cancels_the_issue(self):
		doc = _whole_shift_no_load(consumables=[{"item_code": OIL, "qty": 2}]).insert(ignore_permissions=True)
		doc.submit()
		name = doc.consumables_stock_entry
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Stock Entry", name, "docstatus"), 2)

	def test_entry_without_consumables_makes_no_stock_entry(self):
		doc = _whole_shift_no_load().insert(ignore_permissions=True)
		doc.submit()
		self.assertFalse(doc.consumables_stock_entry)


class TestSPRSetup(SPRBase):
	def test_parameters_seeded_and_checked(self):
		for field, value in (
			("custom_spr_shift_grace_minutes", "30"),
			("custom_spr_max_unaccounted_minutes", "15"),
			("custom_spr_tool_photo_required", "1"),
		):
			stored = stored_single("PEPL System Parameters", field)
			self.assertEqual(str(stored), value, field)
		doc = frappe.get_doc("PEPL System Parameters")
		doc.custom_operator_pin_digits = 4
		doc.custom_spr_shift_grace_minutes = 121
		with self.assertRaisesRegex(frappe.ValidationError, "Grace"):
			validate_production_params(doc)
		doc.custom_spr_shift_grace_minutes = 30
		doc.custom_spr_max_unaccounted_minutes = -1
		with self.assertRaisesRegex(frappe.ValidationError, "negative"):
			validate_production_params(doc)

	def test_changes_tracked_and_in_access_matrix(self):
		self.assertTrue(frappe.get_meta(spr.DOCTYPE).track_changes)
		self.assertTrue(frappe.get_meta(spr.DOCTYPE).is_submittable)
		self.assertIn(spr.DOCTYPE, {doctype for _area, doctype, _label in MATRIX_DOCTYPES})

	def test_foreman_submits_manager_cancels(self):
		foreman = make_user("pepl.test.spr.foreman@example.com", ["Manufacturing User"])
		manager = make_user("pepl.test.spr.manager@example.com", ["Manufacturing Manager"])
		for right in ("create", "write", "submit"):
			self.assertTrue(frappe.has_permission(spr.DOCTYPE, right, user=foreman), right)
		self.assertFalse(frappe.has_permission(spr.DOCTYPE, "cancel", user=foreman))
		self.assertTrue(frappe.has_permission(spr.DOCTYPE, "cancel", user=manager))
		self.assertFalse(frappe.has_permission(spr.DOCTYPE, "delete", user=manager))

	def test_panel_shows_minutes_output_and_missing_photos(self):
		tool = {"change_time": "10:00", "tool_description": "Insert", "reason": "Worn out"}
		doc = make_spr(
			VMC, DAY, OP1, YESTERDAY, downtime=[_down(NO_LOAD, "08:00", "15:00")], tools=[tool]
		).insert(ignore_permissions=True)
		rows = spr.get_spr_panel(doc.name)["rows"]
		texts = " | ".join(r["text"] for r in rows)
		self.assertIn("480", texts)
		self.assertTrue(any("60 minutes" in r["text"] and r["colour"] == "red" for r in rows), texts)
		self.assertTrue(any("photo" in r["text"] and r["colour"] == "red" for r in rows), texts)

	def test_time_helpers(self):
		shift = frappe._dict(start_time="22:00:00", end_time="06:00:00")
		start, end = spr.shift_window(YESTERDAY, shift)
		self.assertEqual(
			(start, end), (get_datetime(f"{YESTERDAY} 22:00:00"), get_datetime(f"{today()} 06:00:00"))
		)
		self.assertEqual(
			spr.time_in_shift(YESTERDAY, shift, "05:50", 30), get_datetime(f"{today()} 05:50:00")
		)
		self.assertEqual(
			spr.time_in_shift(YESTERDAY, shift, "21:45", 30), get_datetime(f"{YESTERDAY} 21:45:00")
		)
