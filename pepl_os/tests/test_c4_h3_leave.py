"""C4-H3 - Earned Leave: 1 per 20 days worked, sandwich across applications, PEPL leave types, approver."""

import frappe
from frappe.utils import add_days, getdate

from pepl_os.pepl_people import hr_setup, leave
from pepl_os.tests.bootstrap import TEST_COMPANY
from pepl_os.tests.test_c4_h1_people import make_employee
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

LIST = "_T C4 H3 Holidays"


def weekdays(start, count):
	days = []
	day = getdate(start)
	while len(days) < count:
		if day.weekday() < 6:  # Monday - Saturday (Sunday is the weekly off)
			days.append(day)
		day = add_days(day, 1)
	return days


def mark(emp, days, status="Present"):
	for day in days:
		frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": emp.name,
				"attendance_date": day,
				"status": status,
				"company": TEST_COMPANY,
			}
		).insert(ignore_permissions=True).submit()


def allocate(emp, year, days):
	doc = frappe.get_doc(
		{
			"doctype": "Leave Allocation",
			"employee": emp.name,
			"leave_type": hr_setup.EARNED_LEAVE,
			"from_date": f"{year}-01-01",
			"to_date": f"{year}-12-31",
			"new_leaves_allocated": days,
		}
	).insert(ignore_permissions=True)
	doc.submit()
	return doc


def application(emp, from_date, to_date, approver, leave_type=hr_setup.EARNED_LEAVE):
	return frappe.get_doc(
		{
			"doctype": "Leave Application",
			"employee": emp.name,
			"leave_type": leave_type,
			"from_date": from_date,
			"to_date": to_date,
			"company": TEST_COMPANY,
			"leave_approver": approver,
			"status": "Open",
		}
	).insert(ignore_permissions=True)


def approve(doc):
	doc.status = "Approved"
	doc.flags.ignore_permissions = True
	doc.submit()
	return doc


class LeaveCase(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		hr_setup.ensure_leave_types()
		hr_setup.ensure_holiday_list(LIST, "2026-01-01", "2027-12-31", [])
		hr_setup.ensure_holiday_list_assignments(LIST, "2026-01-01")
		cls.approver = make_user("c4.h3.approver@example.com", ["Leave Approver", "HR Manager"])


class TestApproverAndTypes(LeaveCase):
	def test_default_approver_and_the_hr_heads_own(self):
		head = make_user("c4.h3.head@example.com", ["Leave Approver"])
		set_param(leave.DEFAULT_APPROVER_FIELD, self.approver)
		set_param(leave.HEAD_APPROVER_FIELD, head)
		staff = make_employee("C4H3 Staff")
		self.assertEqual(staff.leave_approver, self.approver)
		hr_head = make_employee("C4H3 Head", user_id=self.approver)
		self.assertEqual(hr_head.leave_approver, head)  # nobody approves his own leave

	def test_only_pepl_leave_types(self):
		emp = make_employee("C4H3 Types", leave_approver=self.approver)
		allocate(emp, 2027, 5)
		with self.assertRaises(frappe.ValidationError):
			application(emp, "2027-02-01", "2027-02-01", self.approver, leave_type="Casual Leave")
		with self.assertRaises(frappe.ValidationError):
			leave.validate_application(frappe._dict(leave_type="Casual Leave"))
		leave.validate_application(frappe._dict(leave_type="Leave Without Pay"))  # allowed

	def test_only_the_leave_approver_decides(self):
		emp = make_employee("C4H3 Approve", leave_approver=self.approver)
		allocate(emp, 2027, 5)
		app = application(emp, "2027-02-02", "2027-02-02", self.approver)
		assistant = make_user("c4.h3.assistant@example.com", ["HR User"])
		frappe.set_user(assistant)
		with self.assertRaises(frappe.PermissionError):
			approve(app)
		frappe.set_user(self.approver)
		app.reload()
		approve(app)
		self.assertEqual(app.docstatus, 1)

	def test_over_the_balance_refused(self):
		emp = make_employee("C4H3 Balance", leave_approver=self.approver)
		allocate(emp, 2027, 1)
		with self.assertRaises(frappe.ValidationError):
			approve(application(emp, "2027-03-01", "2027-03-03", self.approver))


class TestSandwich(LeaveCase):
	def test_saturday_and_monday_in_two_applications(self):
		emp = make_employee("C4H3 Sandwich", leave_approver=self.approver)
		allocate(emp, 2027, 10)
		approve(application(emp, "2027-01-08", "2027-01-09", self.approver))  # Friday - Saturday
		monday = application(emp, "2027-01-11", "2027-01-11", self.approver)
		self.assertEqual(getdate(monday.from_date), getdate("2027-01-10"))  # Sunday counted
		self.assertEqual(monday.total_leave_days, 2)
		self.assertIn("sandwich", monday.description)

	def test_monday_first_then_saturday(self):
		emp = make_employee("C4H3 Sandwich2", leave_approver=self.approver)
		allocate(emp, 2027, 10)
		approve(application(emp, "2027-01-18", "2027-01-18", self.approver))  # Monday
		saturday = application(emp, "2027-01-16", "2027-01-16", self.approver)
		self.assertEqual(getdate(saturday.to_date), getdate("2027-01-17"))
		self.assertEqual(saturday.total_leave_days, 2)

	def test_no_sandwich_without_leave_on_the_other_side(self):
		emp = make_employee("C4H3 Plain", leave_approver=self.approver)
		allocate(emp, 2027, 10)
		monday = application(emp, "2027-01-25", "2027-01-25", self.approver)
		self.assertEqual(getdate(monday.from_date), getdate("2027-01-25"))
		self.assertEqual(monday.total_leave_days, 1)

	def test_switch_off(self):
		set_param(leave.SANDWICH_FIELD, 0)
		emp = make_employee("C4H3 Off", leave_approver=self.approver)
		allocate(emp, 2027, 10)
		approve(application(emp, "2027-02-05", "2027-02-06", self.approver))
		monday = application(emp, "2027-02-08", "2027-02-08", self.approver)
		self.assertEqual(getdate(monday.from_date), getdate("2027-02-08"))


class TestAccrual(LeaveCase):
	def test_closed_month(self):
		set_param(leave.LOCK_DAY_FIELD, 7)
		self.assertEqual(leave.last_closed_day("2026-11-07"), getdate("2026-09-30"))
		self.assertEqual(leave.last_closed_day("2026-11-08"), getdate("2026-10-31"))
		self.assertEqual(leave.last_closed_day("2027-01-08"), getdate("2026-12-31"))

	def test_one_day_per_twenty_days_worked(self):
		set_param(leave.ACCRUAL_FROM_FIELD, "2026-09-01")
		set_param(leave.LOCK_DAY_FIELD, 7)
		emp = make_employee("C4H3 Accrual", leave_approver=self.approver, date_of_joining="2026-01-01")
		days = weekdays("2026-09-01", 26)
		mark(emp, days[:24])
		mark(emp, days[24:], "Half Day")  # 24 + 2 x 0.5 = 25 days worked
		row = frappe.db.get_value("Employee", emp.name, leave.EMPLOYEE_FIELDS, as_dict=True)
		self.assertEqual(leave.days_worked(emp.name, "2026-09-01", "2026-09-30"), 25)
		result = leave.accrue_employee(row, on="2026-10-08")  # September closed
		self.assertEqual(result[2026][:2], ("created", 1))
		self.assertEqual(leave.accrue_employee(row, on="2026-10-09")[2026][0], "same")
		mark(emp, weekdays("2026-10-01", 15))  # 40 days worked by 31 October
		result = leave.accrue_employee(row, on="2026-11-08")
		self.assertEqual(result[2026][:2], ("updated", 2))
		self.assertEqual(leave.allocation_of(emp.name, 2026).new_leaves_allocated, 2)
		# October's days are not counted before the 8th of November
		self.assertEqual(leave.target_for_year(row, 2026, leave.last_closed_day("2026-11-07"))[0], 1)

	def test_opening_balance(self):
		set_param(leave.ACCRUAL_FROM_FIELD, "2026-09-01")
		emp = make_employee(
			"C4H3 Opening",
			leave_approver=self.approver,
			date_of_joining="2020-01-01",
			custom_el_opening_balance=5,
			custom_el_opening_as_on="2026-10-31",
		)
		row = frappe.db.get_value("Employee", emp.name, leave.EMPLOYEE_FIELDS, as_dict=True)
		mark(emp, weekdays("2026-10-01", 20))  # before the opening date: already in the 5
		result = leave.accrue_employee(row, on="2026-11-08")
		self.assertEqual(result[2026][:2], ("created", 5))

	def test_nothing_counted_before_the_go_live_date(self):
		set_param(leave.ACCRUAL_FROM_FIELD, None)
		emp = make_employee("C4H3 NoDate", leave_approver=self.approver)
		row = frappe.db.get_value("Employee", emp.name, leave.EMPLOYEE_FIELDS, as_dict=True)
		self.assertEqual(leave.accrue_employee(row, on="2026-11-08")[2026][0], "nothing")


class TestHolidayAssignment(LeaveCase):
	def test_company_assignment(self):
		self.assertEqual(hr_setup.holiday_list_assignments(LIST).get(TEST_COMPANY), "2026-01-01")
		self.assertEqual(hr_setup.ensure_holiday_list_assignments(LIST, "2026-01-01")[TEST_COMPANY], "had it")

	def test_parameter_validation(self):
		self.assertEqual(len(hr_setup.validate_params(frappe._dict({"custom_attendance_lock_day": 31}))), 1)
		self.assertEqual(
			len(hr_setup.validate_params(frappe._dict({"custom_el_days_worked_per_leave": 0}))), 1
		)
