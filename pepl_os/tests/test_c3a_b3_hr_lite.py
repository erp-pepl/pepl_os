"""C3a-B3 - HR-lite: operator master alignment with Employee, the skill matrix and shift eligibility."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_production import hr_lite, kiosk, masters, spr
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_downtime_category,
	make_operator,
	make_shift,
	make_spr,
	make_workstation,
)
from pepl_os.tests.utils import PEPLTestCase, set_param

DAY = "T-B3 Day"  # 08:00-16:30
EVENING = "T-B3 Evening"  # 16:30-01:00
MILL = "T-B3 MILL-01"
LATHE = "T-B3 LATHE-01"
MILLS = "T-B3 MILL GROUP"
LATHES = "T-B3 LATHE GROUP"
NO_LOAD = "T-B3 No Load"
PIN = "5678"
LEVEL3 = masters.LEVELS[2]
LEVEL2 = masters.LEVELS[1]
SYSTEM_PARAMETERS = "PEPL System Parameters"


def make_employee(first_name, **fields):
	if not frappe.db.exists("Gender", "Male"):
		frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
	return frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": first_name,
			"company": TEST_COMPANY,
			"gender": "Male",
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2020-04-01",
			"status": "Active",
			**fields,
		}
	).insert(ignore_permissions=True)


class TestHRLite(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_shift(EVENING, "16:30:00", "01:00:00", 30)
		make_workstation(MILL, MILLS)
		make_workstation(LATHE, LATHES)
		make_downtime_category(NO_LOAD, "Planned", 0)

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")
		set_param("custom_skill_min_level", LEVEL3)
		set_param(hr_lite.ELIGIBILITY_FIELD, hr_lite.WARN)
		set_param(hr_lite.EXPIRY_FIELD, 30)
		set_param(hr_lite.COVER_FIELD, 2)

	def _operator(self, code, shifts=(), skills=(), **fields):
		doc = frappe.get_doc(
			{
				"doctype": masters.OPERATOR,
				"employee_code": code,
				"operator_name": "Op " + code,
				"pin": PIN,
				**fields,
			}
		)
		for shift in shifts:
			doc.append("eligible_shifts", {"shift": shift})
		for row in skills:
			doc.append("skills", row)
		return doc.insert(ignore_permissions=True)

	def _entry(self, operator, shift=DAY):
		return make_spr(
			MILL,
			shift,
			operator,
			add_days(today(), -1),
			downtime=[{"downtime_category": NO_LOAD, "from_time": "08:00", "to_time": "16:30"}]
			if shift == DAY
			else [{"downtime_category": NO_LOAD, "from_time": "16:30", "to_time": "01:00"}],
		)

	# ---- 1. operator <-> Employee ----
	def test_operator_takes_name_joining_date_and_login_from_the_employee(self):
		emp = make_employee("Mahesh", last_name="Patil")
		op = self._operator("T-B3-E1", employee=emp.name, operator_name="typed name")
		self.assertEqual(op.operator_name, emp.employee_name)
		self.assertEqual(str(op.joining_date), "2020-04-01")
		self.assertEqual(op.status, "Active")

	def test_one_employee_is_one_operator(self):
		emp = make_employee("Suresh")
		self._operator("T-B3-E2", employee=emp.name)
		with self.assertRaisesRegex(frappe.ValidationError, "already operator"):
			self._operator("T-B3-E3", employee=emp.name)

	def test_an_employee_who_left_makes_the_operator_inactive(self):
		emp = make_employee("Dinesh")
		op = self._operator("T-B3-E4", employee=emp.name)
		emp.reload()
		emp.status = "Left"
		emp.relieving_date = today()
		emp.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value(masters.OPERATOR, op.name, "status"), "Inactive")
		self.assertFalse(masters.verify_operator_pin(op.name, PIN))  # no kiosk any more

	def test_renaming_the_employee_renames_the_operator(self):
		emp = make_employee("Ganesh")
		op = self._operator("T-B3-E5", employee=emp.name)
		emp.reload()
		emp.first_name = "Ganesh Kumar"
		emp.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value(masters.OPERATOR, op.name, "operator_name"), emp.employee_name)
		self.assertIn("Ganesh Kumar", emp.employee_name)

	# ---- 3. shift eligibility ----
	def test_default_shift_must_be_eligible(self):
		with self.assertRaisesRegex(frappe.ValidationError, "not one of the Eligible Shifts"):
			self._operator("T-B3-S1", shifts=[DAY], default_shift=EVENING)
		with self.assertRaisesRegex(frappe.ValidationError, "listed twice"):
			self._operator("T-B3-S2", shifts=[DAY, DAY])

	def test_no_eligible_shifts_means_any_shift(self):
		op = self._operator("T-B3-S3")
		self.assertTrue(hr_lite.is_eligible(op.name, EVENING))
		doc = self._entry(op.name, EVENING).insert(ignore_permissions=True)
		self.assertIsNone(hr_lite.panel_row(doc))

	def test_warn_mode_saves_and_shows_it_on_the_shift_panel(self):
		op = self._operator("T-B3-S4", shifts=[DAY])
		doc = self._entry(op.name, EVENING).insert(ignore_permissions=True)
		texts = [r["text"] for r in spr.panel_rows(doc)]
		self.assertIn(f"Operator {op.name} is not set to work the {EVENING} shift (eligible: {DAY}).", texts)
		ok = self._entry(op.name, DAY)
		ok.workstation = LATHE
		ok.insert(ignore_permissions=True)
		self.assertNotIn("not set to work", " ".join(r["text"] for r in spr.panel_rows(ok)))

	def test_block_mode_refuses_the_entry_and_the_kiosk(self):
		set_param(hr_lite.ELIGIBILITY_FIELD, hr_lite.BLOCK)
		op = self._operator("T-B3-S5", shifts=[DAY])
		with self.assertRaisesRegex(frappe.ValidationError, "not set to work the"):
			self._entry(op.name, EVENING).insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "not set to work the"):
			kiosk.sign_in(MILL, EVENING, today(), op.name, PIN)
		self.assertTrue(kiosk.sign_in(MILL, DAY, today(), op.name, PIN)["token"])

	# ---- 2. skills ----
	def test_skill_states(self):
		# Regression (CI #49): plain dicts, not only Frappe rows, are read (row.get, never row.valid_until)
		as_of = today()
		self.assertEqual(hr_lite.skill_state({"valid_until": None}, as_of), "current")
		self.assertEqual(hr_lite.skill_state({"valid_until": add_days(as_of, -1)}, as_of), "expired")
		self.assertEqual(hr_lite.skill_state({"valid_until": add_days(as_of, 30)}, as_of), "expiring")
		self.assertEqual(hr_lite.skill_state({"valid_until": add_days(as_of, 31)}, as_of), "current")

	def test_operator_panel_warns_of_a_skill_expiring_soon(self):
		op = self._operator(
			"T-B3-K1",
			skills=[{"workstation_type": MILLS, "level": LEVEL3, "valid_until": add_days(today(), 10)}],
		)
		texts = [r["text"] for r in masters.get_operator_panel(op.name)["rows"]]
		self.assertTrue(any(t.startswith(f"{MILLS} expires on") and "(10 days)" in t for t in texts), texts)
		self.assertIn("Not linked to an Employee", texts)
		self.assertIn("Eligible shifts: any", texts)

	def test_skill_matrix(self):
		emp = make_employee("Ramesh")
		self._operator(
			"T-B3-M1",
			skills=[
				{"workstation_type": MILLS, "level": LEVEL3},
				{"workstation_type": LATHES, "level": LEVEL2},
			],
			employee=emp.name,
			default_shift=DAY,
		)
		self._operator(
			"T-B3-M2",
			skills=[{"workstation_type": MILLS, "level": LEVEL3, "valid_until": add_days(today(), -3)}],
		)
		groups, keys, rows, cover, thin = hr_lite.matrix({"status": "Active"})
		self.assertIn(MILLS, groups)
		self.assertIn(LATHES, groups)
		m1 = next(r for r in rows if r["operator"] == "T-B3-M1")
		m2 = next(r for r in rows if r["operator"] == "T-B3-M2")
		self.assertEqual((m1[keys[MILLS]], m1[keys[MILLS] + "_colour"]), ("3", "green"))
		self.assertEqual((m1[keys[LATHES]], m1[keys[LATHES] + "_colour"]), ("2", "orange"))  # below level 3
		self.assertEqual((m2[keys[MILLS]], m2[keys[MILLS] + "_colour"]), ("3 expired", "red"))
		self.assertEqual(m1["issues"], "")
		self.assertIn("no default shift", m2["issues"])
		self.assertIn("not linked to an Employee", m2["issues"])
		self.assertIn(f"{MILLS} expired", m2["issues"])
		self.assertEqual(cover[keys[MILLS]], "1")  # the expired skill does not count
		self.assertIn(MILLS, thin)  # fewer than 2 qualified
		set_param(hr_lite.COVER_FIELD, 1)
		self.assertNotIn(MILLS, hr_lite.matrix({"status": "Active"})[4])

	def test_report_runs(self):
		from pepl_os.pepl_production.report.pepl_skill_matrix import pepl_skill_matrix as report

		self._operator("T-B3-R1", skills=[{"workstation_type": MILLS, "level": LEVEL3}])
		columns, data, message = report.execute({"status": "Active", "workstation_type": MILLS})
		labels = [c["label"] for c in columns]
		self.assertIn(MILLS, labels)
		self.assertNotIn(LATHES, labels)
		self.assertTrue(data[-1].get("is_cover"))
		self.assertIn("Minimum Skill Level", message)
		self.assertTrue(frappe.db.exists("Report", "PEPL Skill Matrix"))

	# ---- settings ----
	def test_settings_are_checked(self):
		doc = frappe.get_doc(SYSTEM_PARAMETERS)
		for field, bad, words in (
			(hr_lite.ELIGIBILITY_FIELD, "Maybe", "Shift Eligibility Check"),
			(hr_lite.EXPIRY_FIELD, -1, "Skill Expiry Warning Days"),
			(hr_lite.COVER_FIELD, -1, "Minimum Qualified Operators"),
		):
			doc.reload()
			doc.set(field, bad)
			with self.assertRaisesRegex(frappe.ValidationError, words):
				validate_production_params(doc)

	def test_settings_have_defaults(self):
		meta = frappe.get_meta(SYSTEM_PARAMETERS)
		self.assertEqual(meta.get_field(hr_lite.ELIGIBILITY_FIELD).default, "Warn")
		self.assertEqual(str(meta.get_field(hr_lite.EXPIRY_FIELD).default), "30")
		self.assertEqual(str(meta.get_field(hr_lite.COVER_FIELD).default), "2")
