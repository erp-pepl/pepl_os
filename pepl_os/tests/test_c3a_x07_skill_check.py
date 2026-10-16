"""C3a-X7 - Operator skill check on the Shift Production Entry (Advisory / Soft Block / Hard Block)."""

import frappe
from frappe.utils import add_days, today

from pepl_os.common.overrides import log_override
from pepl_os.pepl_production import masters, skill
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_downtime_category,
	make_operator,
	make_shift,
	make_spr,
	make_workstation,
)
from pepl_os.tests.utils import PEPLTestCase, set_param, stored_single

L1, L2, L3, L4 = masters.LEVELS
DAY = "T-SK Day"
CNC = "T-SK CNC-01"  # group T-SK CNC
LOOSE = "T-SK BENCH-01"  # no machine group
NO_LOAD = "T-SK No Load"
SKILLED = "T-SK-OP-L3"
JUNIOR = "T-SK-OP-L2"
NOBODY = "T-SK-OP-NONE"
LAPSED = "T-SK-OP-EXP"
YESTERDAY = add_days(today(), -1)


def _entry(operator, machine=CNC, day=YESTERDAY):
	return make_spr(
		machine,
		DAY,
		operator,
		day,
		downtime=[{"downtime_category": NO_LOAD, "from_time": "08:00", "to_time": "16:00"}],
	)


class TestSkillCheck(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(CNC, "T-SK CNC")
		make_workstation(LOOSE)
		make_downtime_category(NO_LOAD, "Planned", 0)
		make_operator(SKILLED, pin="1111", skills=[("T-SK CNC", L3)])
		make_operator(JUNIOR, pin="2222", skills=[("T-SK CNC", L2)])
		make_operator(NOBODY, pin="3333")
		make_operator(
			LAPSED,
			pin="4444",
			skills=[{"workstation_type": "T-SK CNC", "level": L4, "valid_until": add_days(today(), -3)}],
		)

	def setUp(self):
		set_param("skill_check_mode", skill.SOFT)
		set_param(skill.MIN_LEVEL_FIELD, L3)
		set_param("custom_enforce_override_reason", 1)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 1)

	def test_qualified_operator(self):
		doc = _entry(SKILLED).insert(ignore_permissions=True)
		self.assertEqual((doc.skill_status, doc.skill_level), (skill.QUALIFIED, L3))
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_below_minimum_level_is_not_qualified(self):
		doc = _entry(JUNIOR).insert(ignore_permissions=True)
		self.assertEqual((doc.skill_status, doc.skill_level), (skill.NOT_QUALIFIED, L2))

	def test_no_skill_on_the_group_is_not_qualified(self):
		doc = _entry(NOBODY).insert(ignore_permissions=True)
		self.assertEqual((doc.skill_status, doc.skill_level), (skill.NOT_QUALIFIED, skill.NO_LEVEL))

	def test_expired_skill_does_not_count_but_counts_for_earlier_shifts(self):
		self.assertEqual(_entry(LAPSED).insert(ignore_permissions=True).skill_status, skill.NOT_QUALIFIED)
		earlier = _entry(LAPSED, day=add_days(today(), -5)).insert(ignore_permissions=True)
		self.assertEqual((earlier.skill_status, earlier.skill_level), (skill.QUALIFIED, L4))

	def test_minimum_level_comes_from_system_parameters(self):
		set_param(skill.MIN_LEVEL_FIELD, L2)
		self.assertEqual(_entry(JUNIOR).insert(ignore_permissions=True).skill_status, skill.QUALIFIED)

	def test_machine_without_group_is_not_checked_and_never_blocked(self):
		set_param("skill_check_mode", skill.HARD)
		doc = _entry(NOBODY, machine=LOOSE).insert(ignore_permissions=True)
		self.assertEqual(doc.skill_status, skill.NOT_CHECKED)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_advisory_only_warns(self):
		set_param("skill_check_mode", skill.ADVISORY)
		doc = _entry(NOBODY).insert(ignore_permissions=True)
		self.assertIsNone(skill.gate_message(doc))
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_soft_block_needs_a_reason_at_submit(self):
		doc = _entry(JUNIOR).insert(ignore_permissions=True)
		self.assertTrue(skill.gate_message(doc))
		with self.assertRaisesRegex(frappe.ValidationError, r"\[PRD-SKILL\]"):
			doc.submit()
		doc.reload()
		log_override(skill.RULE_CODE, doc.doctype, doc.name, "test", "Supervisor stood with him all shift")
		self.assertIsNone(skill.gate_message(doc))
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_soft_block_only_warns_when_reasons_are_switched_off(self):
		set_param("custom_enforce_override_reason", 0)
		doc = _entry(JUNIOR).insert(ignore_permissions=True)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_hard_block_refuses_the_entry(self):
		set_param("skill_check_mode", skill.HARD)
		with self.assertRaisesRegex(frappe.ValidationError, "not qualified"):
			_entry(JUNIOR).insert(ignore_permissions=True)
		self.assertTrue(_entry(SKILLED).insert(ignore_permissions=True).name)

	def test_unexplained_minutes_are_reported_before_the_skill_gate(self):
		doc = make_spr(
			CNC,
			DAY,
			JUNIOR,
			YESTERDAY,
			downtime=[{"downtime_category": NO_LOAD, "from_time": "08:00", "to_time": "12:00"}],
		).insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "not explained"):
			doc.submit()

	def test_form_gate_check_api(self):
		doc = _entry(JUNIOR).insert(ignore_permissions=True)
		answer = skill.skill_gate_check(doc.name)
		self.assertEqual(answer["rule_code"], skill.RULE_CODE)
		self.assertIn(JUNIOR, answer["message"])
		set_param("skill_check_mode", skill.ADVISORY)
		self.assertIsNone(skill.skill_gate_check(doc.name))

	def test_panel_shows_the_skill(self):
		from pepl_os.pepl_production import spr

		doc = _entry(JUNIOR).insert(ignore_permissions=True)
		rows = spr.get_spr_panel(doc.name)["rows"]
		self.assertTrue(
			any("not qualified" in r["text"].lower() and r["colour"] == "orange" for r in rows), rows
		)

	def test_min_level_parameter_seeded(self):
		self.assertEqual(stored_single("PEPL System Parameters", skill.MIN_LEVEL_FIELD), L3)
		self.assertEqual(skill.mode(), skill.SOFT)
