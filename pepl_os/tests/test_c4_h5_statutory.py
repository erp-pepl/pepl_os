"""C4-H5 - Statutory data on the Employee: level 6, formats, Aadhaar, Show Aadhaar, readiness."""

import frappe

from pepl_os.pepl_people import statutory
from pepl_os.setup import permissions
from pepl_os.tests.test_c4_h1_people import make_employee
from pepl_os.tests.utils import PEPLTestCase, make_user

VALID_AADHAAR = "234123412346"  # Verhoeff check digit 6
VALID_AADHAAR_2 = "987654321012"
WRONG_CHECK_DIGIT = "234123412345"


class TestStatutoryAccess(PEPLTestCase):
	def test_fields_at_level_six(self):
		meta = frappe.get_meta("Employee")
		for field in (
			"custom_uan",
			"custom_esic_ip_number",
			"custom_aadhaar",
			"custom_aadhaar_masked",
			"custom_father_or_husband_name",
			"bank_ac_no",
			"bank_name",
			"pan_number",
			"provident_fund_account",
			"ifsc_code",
			"ctc",
		):
			df = meta.get_field(field)
			self.assertTrue(df, field)
			self.assertEqual(df.permlevel, 6, field)
		self.assertEqual(meta.get_field("custom_aadhaar").fieldtype, "Password")

	def test_only_hr_manager_and_system_manager_see_level_six(self):
		self.assertEqual(statutory.level_roles(), ["HR Manager", "System Manager"])
		ceo = [
			r
			for r in permissions.perm_rows("Employee")
			if r.role == permissions.CEO_ROLE and r.permlevel == 6
		]
		self.assertEqual(ceo, [])
		self.assertEqual(statutory.ensure_statutory_access(), [])  # nothing left to change

	def test_hr_assistant_has_no_level_six(self):
		self.assertNotIn("HR User", statutory.level_roles())


class TestStatutoryData(PEPLTestCase):
	def test_formats_refused(self):
		for fields in (
			{"custom_uan": "12345"},
			{"custom_esic_ip_number": "12345678901"},
			{"pan_number": "ABC123"},
			{"custom_aadhaar": WRONG_CHECK_DIGIT},
			{"custom_aadhaar": "123412341234"},  # cannot start with 1
		):
			with self.assertRaises(frappe.ValidationError, msg=str(fields)):
				make_employee("C4H5 Bad", **fields)

	def test_clean_values_kept(self):
		emp = make_employee(
			"C4H5 Good",
			custom_uan="1001 2345 6789",
			custom_esic_ip_number="12-3456-7890",
			pan_number="abcde1234f",
		)
		self.assertEqual(emp.custom_uan, "100123456789")
		self.assertEqual(emp.custom_esic_ip_number, "1234567890")
		self.assertEqual(emp.pan_number, "ABCDE1234F")

	def test_uan_and_esic_unique(self):
		make_employee("C4H5 First", custom_uan="200123456789", custom_esic_ip_number="2234567890")
		with self.assertRaises(frappe.ValidationError):
			make_employee("C4H5 Second", custom_uan="200123456789")
		with self.assertRaises(frappe.ValidationError):
			make_employee("C4H5 Third", custom_esic_ip_number="2234567890")

	def test_aadhaar_encrypted_and_masked(self):
		emp = make_employee("C4H5 Aadhaar", custom_aadhaar="2341 2341 2346")
		self.assertEqual(emp.custom_aadhaar_masked, "XXXX XXXX 2346")
		stored = frappe.db.get_value("Employee", emp.name, "custom_aadhaar")
		self.assertNotIn("2341", str(stored or ""))  # never the number in the table
		self.assertEqual(emp.get_password("custom_aadhaar"), VALID_AADHAAR)
		# saving again without touching it keeps it
		emp.reload()
		emp.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Employee", emp.name, "custom_aadhaar_masked"), "XXXX XXXX 2346")
		self.assertEqual(emp.get_password("custom_aadhaar"), VALID_AADHAAR)

	def test_show_aadhaar_recorded_and_only_for_hr_manager(self):
		emp = make_employee("C4H5 Show", custom_aadhaar=VALID_AADHAAR_2)
		self.assertEqual(statutory.show_aadhaar(emp.name), VALID_AADHAAR_2)
		self.assertTrue(
			frappe.db.exists("Access Log", {"reference_document": emp.name, "method": "Show Aadhaar"})
		)
		assistant = make_user("c4.h5.assistant@example.com", ["HR User"])
		frappe.set_user(assistant)
		with self.assertRaises(frappe.PermissionError):
			statutory.show_aadhaar(emp.name)

	def test_verhoeff(self):
		self.assertTrue(statutory.aadhaar_ok(VALID_AADHAAR))
		self.assertTrue(statutory.aadhaar_ok(VALID_AADHAAR_2))
		self.assertFalse(statutory.aadhaar_ok(WRONG_CHECK_DIGIT))
		self.assertFalse(statutory.aadhaar_ok("23412341234"))  # 11 digits

	def test_readiness(self):
		emp = make_employee("C4H5 Ready", custom_pf_applicable=1, custom_esic_applicable=1)
		row = next(r for r in statutory.readiness_rows() if r.name == emp.name)
		for word in ("UAN", "PF number", "ESIC IP number", "PAN", "Aadhaar", "father"):
			self.assertIn(word, row["missing"])
		from pepl_os.pepl_people.report.pepl_statutory_data_readiness.pepl_statutory_data_readiness import (
			execute,
		)

		_columns, data, message = execute({"only_missing": 1})
		self.assertTrue(any(r.name == emp.name for r in data))
		self.assertIn("complete", message)

	def test_readiness_report_refused_to_the_ceo(self):
		ceo = make_user("c4.h5.ceo@example.com", ["PEPL CEO"])
		frappe.set_user(ceo)
		from pepl_os.pepl_people.report.pepl_statutory_data_readiness.pepl_statutory_data_readiness import (
			execute,
		)

		with self.assertRaises(frappe.PermissionError):
			execute({})
