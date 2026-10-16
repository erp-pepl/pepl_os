"""C3a-X2 - Shop-floor masters: shifts, downtime categories, operators with PIN and machine skills."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_governance.access_matrix import MATRIX_DOCTYPES
from pepl_os.pepl_production import masters
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.tests.factories import (
	make_downtime_category,
	make_operator,
	make_shift,
	make_workstation,
	make_workstation_type,
)
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param, stored_single

L1, L2, L3, L4 = masters.LEVELS
FOREMAN = "pepl.test.foreman@example.com"
PROD_MANAGER = "pepl.test.prodmanager@example.com"


class TestShift(PEPLTestCase):
	def test_day_shift_planned_minutes(self):
		shift = make_shift("T-DAY", "08:00:00", "16:30:00", 30)
		self.assertEqual((shift.planned_minutes, shift.crosses_midnight), (480, 0))

	def test_night_shift_crosses_midnight(self):
		shift = make_shift("T-NIGHT", "22:00:00", "06:00:00", 30)
		self.assertEqual((shift.planned_minutes, shift.crosses_midnight), (450, 1))

	def test_same_start_and_end_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "same"):
			make_shift("T-ZERO", "08:00:00", "08:00:00", 0)

	def test_break_longer_than_shift_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "[Bb]reak"):
			make_shift("T-SHORT", "08:00:00", "09:00:00", 60)

	def test_negative_break_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "[Bb]reak"):
			make_shift("T-NEG", "08:00:00", "16:00:00", -5)

	def test_shift_minutes_helper(self):
		self.assertEqual(masters.shift_minutes("20:00:00", "08:00:00"), 720)
		self.assertEqual(masters.shift_minutes("06:00", "14:00"), 480)


class TestDowntimeCategory(PEPLTestCase):
	def test_defaults_seeded_on_install(self):
		names = set(frappe.get_all(masters.DOWNTIME, pluck="name"))
		for name, _stop_type, _breakdown in masters.SEED_DOWNTIME_CATEGORIES:
			self.assertIn(name, names)
		self.assertTrue(frappe.db.exists(masters.DOWNTIME, {"is_breakdown": 1, "stop_type": "Unplanned"}))
		self.assertTrue(frappe.db.exists(masters.DOWNTIME, {"stop_type": "PM / Calibration"}))
		self.assertTrue(frappe.db.exists(masters.DOWNTIME, {"stop_type": "Planned"}))

	def test_seeding_is_once_only(self):
		victim = masters.SEED_DOWNTIME_CATEGORIES[0][0]
		frappe.delete_doc(masters.DOWNTIME, victim, force=1, ignore_permissions=True)
		masters.ensure_production_masters()
		self.assertFalse(frappe.db.exists(masters.DOWNTIME, victim))  # PEPL's removal is respected

	def test_breakdown_must_be_unplanned(self):
		with self.assertRaisesRegex(frappe.ValidationError, "[Bb]reakdown"):
			make_downtime_category("T-PLANNED-BREAKDOWN", "Planned", 1)

	def test_effect_explains_oee_and_mtbf(self):
		breakdown = make_downtime_category("T-SPINDLE", "Unplanned", 1)
		self.assertIn("availability", breakdown.effect)
		self.assertIn("MTBF", breakdown.effect)
		planned = make_downtime_category("T-NO-LOAD", "Planned", 0)
		self.assertIn("planned production time", planned.effect)
		self.assertNotIn("MTBF", planned.effect)


class TestOperator(PEPLTestCase):
	def setUp(self):
		set_param("custom_operator_pin_digits", 4)

	def test_pin_must_be_digits(self):
		with self.assertRaisesRegex(frappe.ValidationError, "digits"):
			make_operator("T-OP-ALPHA", pin="12a4")

	def test_pin_length_from_system_parameters(self):
		with self.assertRaisesRegex(frappe.ValidationError, "4"):
			make_operator("T-OP-LONG", pin="12345")
		set_param("custom_operator_pin_digits", 6)
		self.assertEqual(make_operator("T-OP-SIX", pin="123456").pin_set, 1)

	def test_pin_is_never_stored_readable(self):
		op = make_operator("T-OP-SECRET", pin="4321")
		self.assertEqual(op.pin_set, 1)
		stored = frappe.db.get_value(masters.OPERATOR, op.name, "pin")
		self.assertNotIn("4321", stored or "")
		self.assertEqual(frappe.get_doc(masters.OPERATOR, op.name).get_password("pin"), "4321")

	def test_operator_without_pin_is_saved_but_flagged(self):
		op = make_operator("T-OP-NOPIN", pin=None)
		self.assertEqual(op.pin_set, 0)
		panel = masters.get_operator_panel(op.name)
		self.assertTrue(any("PIN" in r["text"] and r["colour"] == "orange" for r in panel["rows"]))

	def test_saving_other_fields_keeps_the_pin(self):
		op = make_operator("T-OP-KEEP", pin="2468")
		op = frappe.get_doc(masters.OPERATOR, op.name)
		op.operator_name = "Renamed Operator"
		op.save(ignore_permissions=True)
		self.assertEqual(op.pin_set, 1)
		self.assertTrue(masters.verify_operator_pin(op.name, "2468"))

	def test_verify_pin(self):
		op = make_operator("T-OP-VERIFY", pin="1357")
		self.assertTrue(masters.verify_operator_pin(op.name, "1357"))
		self.assertFalse(masters.verify_operator_pin(op.name, "1358"))
		self.assertFalse(masters.verify_operator_pin(op.name, ""))
		self.assertFalse(masters.verify_operator_pin("NO-SUCH-OPERATOR", "1357"))
		frappe.db.set_value(masters.OPERATOR, op.name, "status", "Inactive")
		self.assertFalse(masters.verify_operator_pin(op.name, "1357"))

	def test_same_pin_allowed_for_two_operators(self):
		# PINs are checked per operator (code + PIN), so a clash never reveals another person's PIN.
		make_operator("T-OP-SAME-1", pin="1111")
		self.assertEqual(make_operator("T-OP-SAME-2", pin="1111").pin_set, 1)

	def test_one_login_one_operator(self):
		user = make_user("pepl.test.oplogin@example.com")
		make_operator("T-OP-USER-1", user=user)
		with self.assertRaisesRegex(frappe.ValidationError, "already"):
			make_operator("T-OP-USER-2", user=user)

	def test_skill_rows_checked(self):
		with self.assertRaisesRegex(frappe.ValidationError, "twice"):
			make_operator("T-OP-DUP", skills=[("T-VMC", L3), ("T-VMC", L2)])
		with self.assertRaisesRegex(frappe.ValidationError, "[Vv]alid"):
			make_operator(
				"T-OP-DATES",
				skills=[
					{
						"workstation_type": "T-VMC",
						"level": L3,
						"certified_on": today(),
						"valid_until": add_days(today(), -1),
					}
				],
			)

	def test_level_on_machine(self):
		make_workstation("T-VMC-01", "T-VMC")
		make_workstation("T-LATHE-01", "T-LATHE")
		make_workstation("T-NOGROUP-01")
		op = make_operator("T-OP-LEVEL", skills=[("T-VMC", L3)])
		self.assertEqual(masters.operator_level(op.name, "T-VMC-01"), L3)
		self.assertIsNone(masters.operator_level(op.name, "T-LATHE-01"))
		self.assertIsNone(masters.operator_level(op.name, "T-NOGROUP-01"))
		self.assertEqual(masters.level_rank(L3), 3)
		self.assertEqual(masters.level_rank(None), 0)

	def test_expired_skill_does_not_count(self):
		make_workstation("T-GRINDER-01", "T-GRINDER")
		op = make_operator(
			"T-OP-EXPIRED",
			skills=[{"workstation_type": "T-GRINDER", "level": L4, "valid_until": add_days(today(), -1)}],
		)
		self.assertIsNone(masters.operator_level(op.name, "T-GRINDER-01"))
		panel = masters.get_operator_panel(op.name)
		self.assertTrue(any("expired" in r["text"] and r["colour"] == "red" for r in panel["rows"]))

	def test_panel_lists_machine_groups(self):
		op = make_operator("T-OP-PANEL", skills=[("T-VMC", L3), ("T-LATHE", L1)])
		texts = " ".join(r["text"] for r in masters.get_operator_panel(op.name)["rows"])
		self.assertIn("T-VMC", texts)
		self.assertIn("T-LATHE", texts)
		self.assertIn("PIN set", texts)


class TestMastersSetup(PEPLTestCase):
	def test_pin_digits_parameter_range(self):
		doc = frappe.get_doc("PEPL System Parameters")
		doc.custom_operator_pin_digits = 4
		validate_production_params(doc)  # the seeded default is valid
		for wrong in (3, 7):
			doc.custom_operator_pin_digits = wrong
			with self.assertRaisesRegex(frappe.ValidationError, "PIN"):
				validate_production_params(doc)
		events = frappe.get_hooks("doc_events")["PEPL System Parameters"]["validate"]
		self.assertIn("pepl_os.pepl_production.params.validate_production_params", events)

	def test_pin_digits_default_seeded(self):
		stored = stored_single("PEPL System Parameters", masters.PIN_DIGITS_FIELD)
		self.assertEqual(str(stored), "4")

	def test_changes_tracked(self):
		for doctype in (masters.SHIFT, masters.DOWNTIME, masters.OPERATOR):
			self.assertTrue(frappe.get_meta(doctype).track_changes, doctype)

	def test_in_access_matrix(self):
		listed = {doctype for _area, doctype, _label in MATRIX_DOCTYPES}
		for doctype in (masters.SHIFT, masters.DOWNTIME, masters.OPERATOR):
			self.assertIn(doctype, listed)

	def test_foreman_reads_operators_but_cannot_create_them(self):
		make_user(FOREMAN, ["Manufacturing User"])
		make_user(PROD_MANAGER, ["Manufacturing Manager"])
		op = make_operator("T-OP-PERM", pin="9753")
		self.assertTrue(frappe.has_permission(masters.OPERATOR, "read", op.name, user=FOREMAN))
		self.assertFalse(frappe.has_permission(masters.OPERATOR, "create", user=FOREMAN))
		self.assertTrue(frappe.has_permission(masters.OPERATOR, "create", user=PROD_MANAGER))
		self.assertFalse(frappe.has_permission(masters.OPERATOR, "delete", user=PROD_MANAGER))

	def test_nobody_reads_the_pin_from_the_record(self):
		op = make_operator("T-OP-HIDDEN", pin="8642")
		frappe.set_user("Administrator")
		self.assertEqual(set(frappe.get_doc(masters.OPERATOR, op.name).pin or "*"), {"*"})
