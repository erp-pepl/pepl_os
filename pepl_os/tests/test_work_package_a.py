"""Work Package A tests: A1 access audit, A2 roles and delete rights,
A3 change and view tracking, A4 consolidated audit trail, A5 protection and retention."""

import json

import frappe
from frappe.permissions import add_permission, update_permission_property
from frappe.utils import add_to_date, now_datetime, today

from pepl_os.common.overrides import log_override
from pepl_os.pepl_governance import access_audit, audit_trail
from pepl_os.pepl_governance.report.pepl_audit_trail import pepl_audit_trail
from pepl_os.pepl_governance.retention import apply_log_retention
from pepl_os.setup import permissions, property_setters, roles
from pepl_os.tests.factories import make_rm_group
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

TODAY = {"from_date": today(), "to_date": today()}


# A change-tracked PEPL record type; its masters come from the shared factories.
TRACKED_DOCTYPE = "PEPL RM Group"


def _make_tracked_record(name):
	return make_rm_group(name)


# A1 -----------------------------------------------------------------------


class TestAccessAudit(PEPLTestCase):
	def test_generic_names_flagged(self):
		self.assertTrue(access_audit.looks_generic("stores@parasramka.com"))
		self.assertTrue(access_audit.looks_generic("purchase.dept@parasramka.com"))
		self.assertFalse(access_audit.looks_generic("ramesh.kumar@parasramka.com"))

	def test_two_ips_within_an_hour_flagged(self):
		t = now_datetime()
		self.assertTrue(
			access_audit.multi_ip_logins([(t, "1.1.1.1"), (add_to_date(t, minutes=20), "2.2.2.2")])
		)
		self.assertFalse(access_audit.multi_ip_logins([(t, "1.1.1.1"), (add_to_date(t, hours=3), "2.2.2.2")]))
		self.assertFalse(
			access_audit.multi_ip_logins([(t, "1.1.1.1"), (add_to_date(t, minutes=5), "1.1.1.1")])
		)

	def test_report_lists_users_with_flags(self):
		make_user("stores.pepl.test@example.com")
		rows = {r["user"]: r for r in access_audit.get_rows()}
		self.assertIn("stores.pepl.test@example.com", rows)
		self.assertIn("Generic name", rows["stores.pepl.test@example.com"]["flags"])
		self.assertNotIn("Administrator", rows)


# A2 -----------------------------------------------------------------------


class TestRoleProfiles(PEPLTestCase):
	def test_all_profiles_exist_with_expected_roles(self):
		# Seven Cycle 2+ profiles, the CEO included, and three for the Cycle 1 (Sales) jobs.
		self.assertEqual(len(roles.ROLE_PROFILES), 10)
		for profile, expected in roles.ROLE_PROFILES.items():
			self.assertTrue(frappe.db.exists("Role Profile", profile), profile)
			have = set(frappe.get_all("Has Role", filters={"parent": profile}, pluck="role"))
			for role in expected:
				if frappe.db.exists("Role", role):
					self.assertIn(role, have, f"{profile} is missing {role}")

	def test_pepl_ceo_role_exists(self):
		self.assertTrue(frappe.db.exists("Role", "PEPL CEO"))

	def test_seeding_never_removes_roles_added_by_hand(self):
		profile = frappe.get_doc("Role Profile", "PEPL Foreman")
		profile.append("roles", {"role": "Stock User"})
		profile.save(ignore_permissions=True)
		roles.ensure_role_profiles()
		have = set(frappe.get_all("Has Role", filters={"parent": "PEPL Foreman"}, pluck="role"))
		self.assertIn("Stock User", have)


class TestProfileCorrections(PEPLTestCase):
	def test_stores_no_longer_carries_purchase_user(self):
		self.assertNotIn("Purchase User", roles.ROLE_PROFILES["PEPL Stores"])

	def test_correction_removes_only_the_listed_role(self):
		profile = frappe.get_doc("Role Profile", "PEPL Stores")
		profile.append("roles", {"role": "Purchase User"})
		profile.save(ignore_permissions=True)
		changed = roles.remove_roles_from_profiles(roles.PROFILE_CORRECTIONS_V0_3)
		self.assertEqual(changed, {"PEPL Stores": ["Purchase User"]})
		have = set(frappe.get_all("Has Role", filters={"parent": "PEPL Stores"}, pluck="role"))
		self.assertNotIn("Purchase User", have)
		self.assertIn("Stock User", have)

	def test_correction_is_safe_to_repeat(self):
		roles.remove_roles_from_profiles(roles.PROFILE_CORRECTIONS_V0_3)
		self.assertEqual(roles.remove_roles_from_profiles(roles.PROFILE_CORRECTIONS_V0_3), {})


class TestDeleteRestriction(PEPLTestCase):
	def _grant_delete(self, doctype, role):
		add_permission(doctype, role, 0)
		update_permission_property(doctype, role, 0, "delete", 1, validate=False)
		frappe.clear_cache(doctype=doctype)
		self.assertIn(role, permissions.roles_with_delete(doctype))

	def test_no_delete_for_non_admin_roles_after_install(self):
		offenders = {d: permissions.roles_with_delete(d) for d in permissions.delete_restricted_doctypes()}
		offenders = {d: r for d, r in offenders.items() if r}
		self.assertEqual(offenders, {})

	def test_regranted_delete_is_removed_again(self):
		set_param("custom_enforce_delete_restriction", 1)
		self._grant_delete("Item", "Stock User")
		changed = permissions.restrict_delete(["Item"])
		self.assertEqual(changed, {"Item": ["Stock User"]})
		self.assertEqual(permissions.roles_with_delete("Item"), [])

	def test_switch_off_leaves_permissions_alone(self):
		set_param("custom_enforce_delete_restriction", 0)
		self._grant_delete("Item", "Stock User")
		self.assertEqual(permissions.restrict_delete(["Item"]), {})
		self.assertIn("Stock User", permissions.roles_with_delete("Item"))


# A3 -----------------------------------------------------------------------


class TestTracking(PEPLTestCase):
	def test_track_changes_on_all_in_use_doctypes(self):
		for doctype in property_setters.TRACK_CHANGES_DOCTYPES:
			if frappe.db.exists("DocType", doctype):
				self.assertTrue(frappe.get_meta(doctype).track_changes, doctype)

	def test_track_views_on_sensitive_doctypes(self):
		for doctype in property_setters.TRACK_VIEWS_DOCTYPES:
			if frappe.db.exists("DocType", doctype):
				self.assertTrue(frappe.get_meta(doctype).track_views, doctype)

	def test_change_is_attributed_to_the_user(self):
		record = _make_tracked_record("PEPL-WPA-TRACK")
		record.typical_wastage_percent = 7
		# Frappe v16 skips Versions in tests unless asked (document.py: ignore_version = frappe.in_test).
		record.save(ignore_permissions=True, ignore_version=False)
		version = frappe.get_all(
			"Version",
			filters={"ref_doctype": TRACKED_DOCTYPE, "docname": record.name},
			fields=["owner", "data"],
			order_by="creation desc",
			limit=1,
		)[0]
		self.assertEqual(version.owner, frappe.session.user)
		self.assertIn("typical_wastage_percent", version.data)


# A4 -----------------------------------------------------------------------


class TestAuditTrail(PEPLTestCase):
	def test_version_details_parsing(self):
		data = json.dumps(
			{
				"changed": [["gst_number", "19AAA", "19BBB"], ["docstatus", 0, 1]],
				"row_changed": [["items", "row-1", 2, [["qty", 5, 7]]]],
				"added": [["items", {}]],
				"removed": [],
			}
		)
		lines = audit_trail.version_details(data)
		self.assertIn("gst_number: 19AAA → 19BBB", lines)
		self.assertIn("Status: Draft → Submitted", lines)
		self.assertIn("items row 2 · qty: 5 → 7", lines)
		self.assertIn("items: row added", lines)

	def _make_one_event_of_each_kind(self):
		record = _make_tracked_record("PEPL-WPA-TRAIL")
		record.typical_wastage_percent = 9
		# Frappe v16 skips Versions in tests unless asked (document.py: ignore_version = frappe.in_test).
		record.save(ignore_permissions=True, ignore_version=False)
		user = frappe.session.user
		frappe.get_doc(
			{
				"doctype": "Activity Log",
				"subject": "PEPL test login",
				"user": user,
				"operation": "Login",
				"status": "Success",
				"ip_address": "10.0.0.7",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Access Log",
				"user": user,
				"export_from": TRACKED_DOCTYPE,
				"file_type": "CSV",
				"report_name": TRACKED_DOCTYPE,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Deleted Document",
				"deleted_doctype": "ToDo",
				"deleted_name": "PEPL-TEST-DEL",
				"data": "{}",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "View Log",
				"viewed_by": user,
				"reference_doctype": TRACKED_DOCTYPE,
				"reference_name": record.name,
			}
		).insert(ignore_permissions=True)
		log_override(
			"TEST-TRAIL", TRACKED_DOCTYPE, record.name, "Test override", "Approved by MD for the test"
		)

	def test_merges_all_six_sources(self):
		self._make_one_event_of_each_kind()
		rows, _ = audit_trail.get_events({**TODAY, "user": frappe.session.user})
		self.assertEqual({r["event_type"] for r in rows}, set(audit_trail.EVENT_TYPES))

	def test_event_type_filter(self):
		self._make_one_event_of_each_kind()
		rows, _ = audit_trail.get_events({**TODAY, "event_type": audit_trail.EVENT_OVERRIDE})
		self.assertTrue(rows)
		self.assertEqual({r["event_type"] for r in rows}, {audit_trail.EVENT_OVERRIDE})

	def test_newest_first(self):
		self._make_one_event_of_each_kind()
		rows, _ = audit_trail.get_events(TODAY)
		times = [r["time"] for r in rows]
		self.assertEqual(times, sorted(times, reverse=True))

	def test_dates_required(self):
		with self.assertRaises(frappe.ValidationError):
			audit_trail.get_events({"from_date": today()})

	def test_report_returns_columns_and_rows(self):
		self._make_one_event_of_each_kind()
		columns, rows, _message = pepl_audit_trail.execute(TODAY)
		self.assertEqual(
			[c["fieldname"] for c in columns],
			["time", "user", "event_type", "reference_doctype", "reference_name", "detail"],
		)
		self.assertTrue(rows)


# A5 -----------------------------------------------------------------------


class TestTrailProtection(PEPLTestCase):
	def test_trail_logs_not_deletable_by_non_admin(self):
		for doctype in permissions.LOG_DOCTYPES:
			if frappe.db.exists("DocType", doctype):
				self.assertEqual(permissions.roles_with_delete(doctype), [], doctype)

	def _activity_log_days(self):
		settings = frappe.get_doc("Log Settings")
		for row in settings.logs_to_clear:
			if row.ref_doctype == "Activity Log":
				return row.days
		return None

	def test_retention_raises_login_history_period(self):
		set_param("custom_audit_log_retention_days", 1095)
		apply_log_retention()
		self.assertEqual(self._activity_log_days(), 1095)

	def test_retention_never_lowers(self):
		set_param("custom_audit_log_retention_days", 1095)
		apply_log_retention()
		set_param("custom_audit_log_retention_days", 30)
		apply_log_retention()
		self.assertEqual(self._activity_log_days(), 1095)
