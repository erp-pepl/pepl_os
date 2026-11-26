"""C4-H0 - Frappe HR (HRMS) in place: dependency, access, PEPL's HR set-up."""

from unittest.mock import patch

import frappe
from frappe.utils import getdate

from pepl_os import hooks
from pepl_os.pepl_governance import access_plan as ap
from pepl_os.pepl_people import hr_setup
from pepl_os.setup import permissions, roles
from pepl_os.tests.factories import make_shift
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

LIST = "_T C4 PEPL Holidays"
HOLIDAYS_2026 = [
	["2026-01-23", "Saraswati Puja"],
	["2026-01-26", "Republic Day"],
	["2026-03-03", "Dol Jatra (Holi)"],
	["2026-05-01", "May Day"],
	["2026-08-15", "Independence Day"],
	["2026-09-18", "Viswakarma Puja"],
	["2026-10-19", "Durga Puja"],
	["2026-10-20", "Durga Puja"],
	["2026-10-21", "Durga Puja"],
	["2026-11-09", "Kali Puja"],
]
HR_DOCTYPES = (
	"Employee",
	"Attendance",
	"Leave Application",
	"Leave Allocation",
	"Holiday List",
	"Shift Type",
)


class TestHrmsInPlace(PEPLTestCase):
	def test_hrms_is_a_required_app_and_installed(self):
		self.assertIn("hrms", hooks.required_apps)
		self.assertLess(hooks.required_apps.index("erpnext"), hooks.required_apps.index("hrms"))
		self.assertIn("hrms", frappe.get_installed_apps())

	def test_hr_profiles(self):
		self.assertEqual(roles.ROLE_PROFILES["PEPL HR Manager"], ("HR Manager", "HR User", "Leave Approver"))
		self.assertEqual(roles.ROLE_PROFILES["PEPL HR Assistant"], ("HR User",))
		for profile in ("PEPL HR Manager", "PEPL HR Assistant"):
			self.assertTrue(frappe.db.exists("Role Profile", profile), profile)
		have = set(frappe.get_all("Has Role", filters={"parent": "PEPL HR Assistant"}, pluck="role"))
		self.assertNotIn("HR Manager", have)
		self.assertNotIn("Leave Approver", have)

	def test_hr_records_deleted_only_by_the_system_manager(self):
		for doctype in HR_DOCTYPES:
			self.assertIn(doctype, permissions.CORE_DOCTYPES)
			self.assertEqual(permissions.roles_with_delete(doctype), [], doctype)

	def test_ceo_views_people_and_leave(self):
		for doctype in ("Employee", "Attendance", "Leave Application"):
			self.assertIn(doctype, permissions.ceo_view_doctypes())
			row = next(
				(
					r
					for r in permissions.perm_rows(doctype)
					if r.role == permissions.CEO_ROLE and not r.permlevel
				),
				None,
			)
			self.assertTrue(row and row.read, doctype)
			self.assertFalse(row.write, doctype)

	def test_only_the_hr_head_cancels(self):
		for doctype in ("Attendance", "Leave Application", "Leave Allocation"):
			self.assertEqual(ap.CANCEL_RULES[doctype], ("HR Manager",))
			self.assertEqual(ap.cancel_offenders(doctype), [], doctype)
			self.assertTrue(
				any(r.role == "HR Manager" and r.cancel for r in permissions.perm_rows(doctype)), doctype
			)

	def test_employee_changes_and_views_are_tracked(self):
		meta = frappe.get_meta("Employee")
		self.assertTrue(meta.track_changes)
		self.assertTrue(meta.track_views)


class TestHrSetup(PEPLTestCase):
	def test_sundays(self):
		days = hr_setup.sundays("2026-01-01", "2026-12-31")
		self.assertEqual(len(days), 52)
		self.assertEqual(days[0], getdate("2026-01-04"))
		self.assertTrue(all(d.weekday() == 6 for d in days))

	def test_holiday_list_sundays_and_pepl_holidays_once(self):
		first = hr_setup.ensure_holiday_list(LIST, "2026-01-01", "2027-12-31", HOLIDAYS_2026)
		self.assertTrue(first["created"])
		doc = frappe.get_doc("Holiday List", LIST)
		weekly = [r for r in doc.holidays if r.weekly_off]
		self.assertEqual(len(weekly), len(hr_setup.sundays("2026-01-01", "2027-12-31")))
		self.assertEqual(len([r for r in doc.holidays if not r.weekly_off]), 10)
		again = hr_setup.ensure_holiday_list(LIST, "2026-01-01", "2027-12-31", HOLIDAYS_2026)
		self.assertFalse(again["created"])
		self.assertEqual(again["added"], [])
		# 2027 holidays added later go in; nothing is deleted
		later = hr_setup.ensure_holiday_list(
			LIST, "2026-01-01", "2027-12-31", [["2027-01-26", "Republic Day"]]
		)
		self.assertEqual(later["added"], [getdate("2027-01-26")])
		with self.assertRaises(frappe.ValidationError):
			hr_setup.ensure_holiday_list(LIST, "2026-01-01", "2027-12-31", [["2028-01-26", "Too late"]])

	def test_company_default_only_when_empty(self):
		hr_setup.ensure_holiday_list(LIST, "2026-01-01", "2027-12-31", HOLIDAYS_2026)
		company = frappe.get_all("Company", pluck="name")[0]
		frappe.db.set_value("Company", company, "default_holiday_list", None)
		result = hr_setup.set_company_holiday_lists(LIST)
		self.assertEqual(result[company], "set")
		self.assertEqual(frappe.db.get_value("Company", company, "default_holiday_list"), LIST)
		self.assertNotIn(company, hr_setup.set_company_holiday_lists(LIST))

	def test_leave_types(self):
		hr_setup.ensure_leave_types()
		el = frappe.get_doc("Leave Type", hr_setup.EARNED_LEAVE)
		for field, value in hr_setup.EARNED_LEAVE_FLAGS.items():
			self.assertEqual(el.get(field), value, field)
		lwp = frappe.get_doc("Leave Type", hr_setup.LEAVE_WITHOUT_PAY)
		self.assertEqual((lwp.include_holiday, lwp.is_lwp), (1, 1))
		self.assertEqual(hr_setup.ensure_leave_types(), {})

	def test_leave_periods_per_company_and_year(self):
		hr_setup.ensure_leave_periods([2026, 2027])
		for company in frappe.get_all("Company", pluck="name"):
			for year in (2026, 2027):
				self.assertTrue(
					frappe.db.exists(
						"Leave Period",
						{"company": company, "from_date": f"{year}-01-01", "to_date": f"{year}-12-31"},
					)
				)
		self.assertEqual(hr_setup.ensure_leave_periods([2026, 2027]), [])

	def test_shift_type_follows_pepl_shift_and_rules(self):
		make_shift("_T C4 Day", start="08:00:00", end="16:30:00")
		hr_setup.ensure_holiday_list(LIST, "2026-01-01", "2027-12-31", HOLIDAYS_2026)
		result = hr_setup.ensure_shift_types(LIST)
		self.assertEqual(result.get("_T C4 Day"), "created")
		st = frappe.get_doc("Shift Type", "_T C4 Day")
		self.assertEqual(str(st.start_time), "8:00:00")
		self.assertEqual(st.late_entry_grace_period, 15)
		self.assertEqual(st.working_hours_threshold_for_half_day, 4.5)
		self.assertEqual(st.working_hours_threshold_for_absent, 4)
		self.assertEqual(st.enable_auto_attendance, 0)  # attendance stays in Attendo for now
		self.assertEqual(st.enable_late_entry_marking, 1)
		self.assertEqual(st.holiday_list, LIST)
		self.assertNotIn("_T C4 Day", hr_setup.ensure_shift_types(LIST))
		new_rules = {
			"late_entry_grace_period": 20,
			"working_hours_threshold_for_half_day": 5,
			"working_hours_threshold_for_absent": 3,
		}
		with patch.object(hr_setup, "attendance_rules", return_value=new_rules):
			self.assertIn("_T C4 Day", hr_setup.apply_rules_to_shift_types())
		st.reload()
		self.assertEqual(st.late_entry_grace_period, 20)
		self.assertEqual(st.working_hours_threshold_for_absent, 3)

	def test_rules_from_system_parameters(self):
		set_param(hr_setup.GRACE_FIELD, 10)
		self.assertEqual(hr_setup.attendance_rules()["late_entry_grace_period"], 10)

	def test_parameter_validation(self):
		ok = frappe._dict({hr_setup.GRACE_FIELD: 15, hr_setup.HALF_DAY_FIELD: 4.5, hr_setup.ABSENT_FIELD: 4})
		self.assertEqual(hr_setup.validate_params(ok), [])
		self.assertEqual(len(hr_setup.validate_params(frappe._dict({hr_setup.GRACE_FIELD: 200}))), 1)
		bad = frappe._dict({hr_setup.HALF_DAY_FIELD: 4, hr_setup.ABSENT_FIELD: 5})
		self.assertEqual(len(hr_setup.validate_params(bad)), 1)

	def test_hr_settings(self):
		hr_setup.apply_hr_settings()
		hr = frappe.get_doc("HR Settings")
		for field, value in hr_setup.HR_SETTINGS.items():
			self.assertEqual(hr.get(field), value, field)
		self.assertEqual(hr_setup.apply_hr_settings(), [])

	def test_add_profile_keeps_other_profiles(self):
		user = make_user("c4.h0.assistant@example.com")
		self.assertEqual(hr_setup.add_profile(user, hr_setup.HR_ASSISTANT_PROFILE), "added")
		self.assertEqual(hr_setup.add_profile(user, hr_setup.HR_ASSISTANT_PROFILE), "had it")
		self.assertIn("HR User", frappe.get_all("Has Role", filters={"parent": user}, pluck="role"))
		self.assertEqual(
			hr_setup.add_profile("nobody.c4@example.com", hr_setup.HR_MANAGER_PROFILE), "no such login"
		)

	def test_set_up_only_by_the_system_manager(self):
		user = make_user("c4.h0.plain@example.com", ["HR User"])
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			hr_setup.apply_hr_setup(LIST, "2026-01-01", "2027-12-31", HOLIDAYS_2026, [2026, 2027])

	def test_whole_set_up_runs_twice(self):
		lines = hr_setup.apply_hr_setup(LIST, "2026-01-01", "2027-12-31", HOLIDAYS_2026, [2026, 2027])
		self.assertTrue(any(line.startswith("2. Holiday List") for line in lines))
		again = hr_setup.apply_hr_setup(LIST, "2026-01-01", "2027-12-31", HOLIDAYS_2026, [2026, 2027])
		self.assertIn("1. HR Settings: already as PEPL decided", again)
		status = hr_setup.hr_setup_status(LIST, [2026, 2027])
		self.assertEqual(len(status["holiday_list"]["holidays"]), 10)
		self.assertEqual(status["holiday_list"]["weekly_off"], status["holiday_list"]["sundays_expected"])
