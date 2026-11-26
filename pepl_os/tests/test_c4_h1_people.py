"""C4-H1 - People and logins: Person Type, device logins, operator code, leavers, idle logout, People Register."""

import time
from unittest.mock import patch

import frappe
from frappe.sessions import hash_sid

from pepl_os.pepl_people import idle_logout, people
from pepl_os.tests.bootstrap import TEST_COMPANY
from pepl_os.tests.factories import make_operator
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param


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


def delete_without_commit(sid_hash=None, user=None, reason=None):
	# Frappe's delete_session commits; in a test only the row goes
	frappe.db.delete("Sessions", {"sid": sid_hash})


def add_session(user, sid, lastupdate):
	frappe.db.sql(
		"insert into `tabSessions` (user, sid, sessiondata, lastupdate, status) values (%s, %s, '{}', %s, 'Active')",
		(user, sid, lastupdate),
	)


class TestPeople(PEPLTestCase):
	def test_person_type_from_the_login(self):
		user = make_user("c4.h1.login@example.com")
		with_login = make_employee("C4H1 Login", user_id=user)
		without = make_employee("C4H1 Floor")
		self.assertEqual(with_login.custom_person_type, people.LOGIN_USER)
		self.assertEqual(without.custom_person_type, people.SHOP_FLOOR)

	def test_no_own_record_restriction(self):
		user = make_user("c4.h1.ownrec@example.com")
		emp = make_employee("C4H1 Own", user_id=user, create_user_permission=1)
		self.assertEqual(emp.create_user_permission, 0)
		self.assertFalse(frappe.db.exists("User Permission", {"user": user, "allow": "Employee"}))

	def test_device_login_refused(self):
		user = make_user("c4.h1.tablet@example.com", ["PEPL Kiosk"])
		with self.assertRaises(frappe.ValidationError):
			make_employee("C4H1 Tablet", user_id=user)

	def test_login_stays_on_when_the_employee_leaves(self):
		user = make_user("c4.h1.leaver@example.com")
		emp = make_employee("C4H1 Leaver", user_id=user)
		self.assertEqual(frappe.db.get_value("User", user, "enabled"), 1)
		emp.status = "Left"
		emp.relieving_date = "2026-11-30"
		emp.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("User", user, "enabled"), 1)  # ERPNext alone would switch it off
		todos = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "Employee",
				"reference_name": emp.name,
				"status": "Open",
				"description": ["like", f"%{people.LEAVER_RULE}%"],
			},
		)
		self.assertEqual(len(todos), 1)

	def test_switch_off_keeps_erpnexts_rule(self):
		set_param(people.KEEP_LOGIN_FIELD, 0)
		user = make_user("c4.h1.leaver2@example.com")
		emp = make_employee("C4H1 Leaver2", user_id=user)
		emp.status = "Left"
		emp.relieving_date = "2026-11-30"
		emp.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("User", user, "enabled"), 0)

	def test_operator_code_must_equal_employee_number(self):
		emp = make_employee("C4H1 Code", employee_number="C4H1-77")
		with self.assertRaises(frappe.ValidationError):
			make_operator("C4H1-78", employee=emp.name)
		op = make_operator("C4H1-77", employee=emp.name)
		self.assertEqual(op.employee, emp.name)
		emp.reload()
		emp.employee_number = "C4H1-79"
		with self.assertRaises(frappe.ValidationError):
			emp.save(ignore_permissions=True)

	def test_make_operator_and_link_by_code(self):
		emp = make_employee("C4H1 Make", employee_number="C4H1-81")
		name = people.make_operator(emp.name)
		self.assertEqual(name, "C4H1-81")
		self.assertEqual(frappe.db.get_value("PEPL Operator", name, "employee"), emp.name)
		with self.assertRaises(frappe.ValidationError):
			people.make_operator(emp.name)
		# an operator first, the Employee later: linked by the code when the Employee is saved
		make_operator("C4H1-82")
		emp2 = make_employee("C4H1 Later", employee_number="C4H1-82")
		self.assertEqual(frappe.db.get_value("PEPL Operator", "C4H1-82", "employee"), emp2.name)

	def test_make_operator_needs_the_number(self):
		emp = make_employee("C4H1 NoNumber")
		with self.assertRaises(frappe.ValidationError):
			people.make_operator(emp.name)

	def test_people_register(self):
		user = make_user("c4.h1.register@example.com")
		emp = make_employee("C4H1 Register", user_id=user)
		make_operator("C4H1-91")
		lonely = make_user("c4.h1.nobody@example.com")
		rows = people.register_rows()
		mine = next(r for r in rows if r.get("employee") == emp.name)
		self.assertEqual(mine["person_type"], people.LOGIN_USER)
		self.assertIn("no Employee Number", mine["gaps"])
		self.assertTrue(
			any(r.get("operator") == "C4H1-91" and "without an Employee" in r["gaps"] for r in rows)
		)
		self.assertTrue(
			any(r.get("user_id") == lonely and "login without an Employee" in r["gaps"] for r in rows)
		)
		from pepl_os.pepl_people.report.pepl_people_register.pepl_people_register import execute

		_columns, data, message = execute({"only_gaps": 1})
		self.assertTrue(all(r.get("gaps") for r in data))
		self.assertIn("to put right", message)


class TestIdleLogout(PEPLTestCase):
	def test_idle_seconds(self):
		now = time.time()
		self.assertEqual(idle_logout.idle_seconds(now - 100, None, now), 100)
		# only Frappe's last-updated time: 10 minutes added, never early
		lastupdate = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-4)
		idle = idle_logout.idle_seconds(None, lastupdate, now)
		self.assertAlmostEqual(idle, 4 * 3600 - 600, delta=5)

	def test_settings(self):
		self.assertEqual(idle_logout.limit_seconds(), 3 * 3600)
		self.assertEqual(idle_logout.exempt_roles(), ["PEPL Kiosk"])
		set_param(idle_logout.HOURS_FIELD, 0)
		self.assertEqual(idle_logout.limit_seconds(), 0)
		self.assertEqual(idle_logout.run_idle_logout(), [])

	def test_logged_out_after_three_hours_not_before(self):
		user = make_user("c4.h1.idle@example.com")
		busy = make_user("c4.h1.busy@example.com")
		now = frappe.utils.now_datetime()
		add_session(user, "c4h1-idle-sid", now)
		add_session(busy, "c4h1-busy-sid", now)
		idle_logout.mark_seen("c4h1-idle-sid", time.time() - 3 * 3600 - 1)  # 3 h 0 min 1 s
		idle_logout.mark_seen("c4h1-busy-sid", time.time() - 3 * 3600 + 60)  # 2 h 59 min
		with (
			patch.object(idle_logout, "notify") as told,
			patch.object(idle_logout, "delete_session", side_effect=delete_without_commit),
		):
			ended = idle_logout.run_idle_logout()
		self.assertIn(user, ended)
		self.assertNotIn(busy, ended)
		self.assertFalse(frappe.db.exists("Sessions", {"sid": "c4h1-idle-sid"}))
		self.assertTrue(frappe.db.exists("Sessions", {"sid": "c4h1-busy-sid"}))
		told.assert_called_once()

	def test_kiosk_tablet_exempt(self):
		tablet = make_user("c4.h1.kiosk@example.com", ["PEPL Kiosk"])
		add_session(tablet, "c4h1-kiosk-sid", frappe.utils.now_datetime())
		idle_logout.mark_seen("c4h1-kiosk-sid", time.time() - 10 * 3600)
		with (
			patch.object(idle_logout, "notify"),
			patch.object(idle_logout, "delete_session", side_effect=delete_without_commit),
		):
			self.assertNotIn(tablet, idle_logout.run_idle_logout())
		self.assertTrue(frappe.db.exists("Sessions", {"sid": "c4h1-kiosk-sid"}))

	def test_request_after_the_idle_time_is_refused(self):
		user = make_user("c4.h1.back@example.com")
		sid = "c4h1-back-raw-sid"
		add_session(user, hash_sid(sid), frappe.utils.now_datetime())
		idle_logout.mark_seen(hash_sid(sid), time.time() - 3 * 3600 - 5)
		session = frappe._dict(user=user, sid=sid)
		with (
			patch.object(frappe.local, "session", session),
			patch.object(idle_logout, "notify") as told,
			patch.object(idle_logout, "delete_session", side_effect=delete_without_commit),
			patch.object(frappe.db, "commit"),
		):
			with self.assertRaises(frappe.SessionExpired):
				idle_logout.before_request()
		told.assert_called_once()
		self.assertFalse(frappe.db.exists("Sessions", {"sid": hash_sid(sid)}))

	def test_request_in_time_is_recorded(self):
		user = make_user("c4.h1.ontime@example.com")
		sid = "c4h1-ontime-raw-sid"
		idle_logout.mark_seen(hash_sid(sid), time.time() - 3600)
		with patch.object(frappe.local, "session", frappe._dict(user=user, sid=sid)):
			idle_logout.before_request()
		self.assertLess(time.time() - idle_logout.seen(hash_sid(sid)), 5)

	def test_mails_go_to_the_person_and_the_system_managers(self):
		user = make_user("c4.h1.mail@example.com")
		manager = make_user("c4.h1.sm@example.com", ["System Manager"])
		with patch("frappe.sendmail") as sent:
			idle_logout.notify(user, 3 * 3600 + 1)
		recipients = [c.kwargs["recipients"] for c in sent.call_args_list]
		self.assertIn([user], recipients)
		self.assertTrue(any(manager in r for r in recipients if r != [user]))

	def test_idle_hours_validated(self):
		from pepl_os.pepl_people import hr_setup

		self.assertEqual(len(hr_setup.validate_params(frappe._dict({"custom_idle_logout_hours": 30}))), 1)
		self.assertEqual(hr_setup.validate_params(frappe._dict({"custom_idle_logout_hours": 3})), [])
