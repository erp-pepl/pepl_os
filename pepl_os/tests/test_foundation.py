"""Foundation tests (F4-F6). These must stay green for every package."""

import frappe
from frappe.utils import add_days, now_datetime

from pepl_os.common import alerts, expiry, jobs, overrides, params
from pepl_os.pepl_governance.page.pepl_system_health import pepl_system_health as health
from pepl_os.setup.custom_fields import CUSTOM_FIELDS, SYSTEM_PARAMETERS
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

HEARTBEAT = "pepl_os.pepl_governance.jobs.daily_heartbeat"
REF_DOCTYPE, REF_NAME = "User", "Administrator"


@jobs.tracked_job("Test success job")
def _ok_job():
	return {"records_touched": 3, "message": "ok"}


@jobs.tracked_job("Test failing job")
def _bad_job():
	raise ValueError("boom")


def _last_run(method):
	rows = frappe.get_all(
		"PEPL Job Run",
		filters={"method": method},
		fields=["status", "records_touched", "message", "error", "finished_at"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0] if rows else None


class TestExpiry(PEPLTestCase):
	def test_expiry_health_boundaries(self):
		as_of = "2026-10-01"
		self.assertEqual(expiry.health(None, 30, as_of)["status"], expiry.NO_EXPIRY)

		expired = expiry.health("2026-09-30", 30, as_of)
		self.assertEqual((expired["status"], expired["days_to_expiry"]), (expiry.EXPIRED, -1))

		today_ = expiry.health("2026-10-01", 30, as_of)
		self.assertEqual((today_["status"], today_["days_to_expiry"]), (expiry.EXPIRING_SOON, 0))

		edge = expiry.health("2026-10-31", 30, as_of)
		self.assertEqual((edge["status"], edge["days_to_expiry"]), (expiry.EXPIRING_SOON, 30))

		active = expiry.health("2026-11-01", 30, as_of)
		self.assertEqual((active["status"], active["days_to_expiry"]), (expiry.ACTIVE, 31))


class TestOverrides(PEPLTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_reason_is_mandatory(self):
		with self.assertRaises(frappe.ValidationError):
			overrides.log_override("TEST-OVR", REF_DOCTYPE, REF_NAME, "msg", "")

	def test_short_reason_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			overrides.log_override("TEST-OVR", REF_DOCTYPE, REF_NAME, "msg", "too short")

	def test_valid_override_logged_with_user(self):
		name = overrides.log_override(
			"TEST-OVR", REF_DOCTYPE, REF_NAME, "Supplier not approved", "Urgent breakdown spare"
		)
		row = frappe.get_doc("PEPL Override Log", name)
		self.assertEqual(row.user, "Administrator")
		self.assertEqual(row.reason, "Urgent breakdown spare")
		self.assertTrue(overrides.has_recent_override("TEST-OVR", REF_DOCTYPE, REF_NAME))

	def test_require_override_blocks_until_reason_logged(self):
		doc = frappe.get_doc(REF_DOCTYPE, REF_NAME)
		with self.assertRaises(frappe.ValidationError):
			overrides.require_override(doc, "TEST-GATE", "Gate closed.")
		overrides.log_override("TEST-GATE", REF_DOCTYPE, REF_NAME, "Gate closed.", "Approved by MD on phone")
		overrides.require_override(doc, "TEST-GATE", "Gate closed.")  # no error now

	def test_non_writer_cannot_record_override(self):
		frappe.set_user(make_user("pepl.os.noperm@example.com"))
		with self.assertRaises(frappe.PermissionError):
			overrides.record_override("TEST-OVR", REF_DOCTYPE, REF_NAME, "msg", "a long enough reason")


class TestTrackedJobs(PEPLTestCase):
	def test_success_run_recorded(self):
		_ok_job()
		run = _last_run(_ok_job.pepl_job_method)
		self.assertEqual(run.status, "Success")
		self.assertEqual(run.records_touched, 3)
		self.assertTrue(run.finished_at)

	def test_failed_run_recorded_and_error_raised(self):
		with self.assertRaises(ValueError):
			_bad_job()
		run = _last_run(_bad_job.pepl_job_method)
		self.assertEqual(run.status, "Failed")
		self.assertIn("boom", run.error)

	def test_heartbeat_registered_as_daily_job(self):
		self.assertEqual(
			frappe.db.get_value("Scheduled Job Type", {"method": HEARTBEAT}, "frequency"),
			"Daily",
		)

	def test_heartbeat_run_is_recorded(self):
		frappe.get_attr(HEARTBEAT)()
		self.assertEqual(_last_run(HEARTBEAT).status, "Success")


class TestSystemHealth(PEPLTestCase):
	def test_health_lists_heartbeat_ok_after_run(self):
		frappe.get_attr(HEARTBEAT)()
		jobs_by_method = {j["method"]: j for j in health.get_health()["jobs"]}
		self.assertIn(HEARTBEAT, jobs_by_method)
		self.assertEqual(jobs_by_method[HEARTBEAT]["status"], "OK")

	def test_health_marks_stale_job(self):
		frappe.get_attr(HEARTBEAT)()
		future = add_days(now_datetime(), 3)
		self.assertEqual(health.job_health("daily", HEARTBEAT, now=future)["status"], "Stale")


class TestSystemParameters(PEPLTestCase):
	def test_all_pepl_os_fields_exist(self):
		meta = frappe.get_meta(SYSTEM_PARAMETERS)
		for field in CUSTOM_FIELDS[SYSTEM_PARAMETERS]:
			self.assertTrue(meta.has_field(field["fieldname"]), field["fieldname"])

	def test_params_reads_custom_field(self):
		set_param("custom_purchase_notification_owner", "Administrator")
		self.assertEqual(params.get("custom_purchase_notification_owner"), "Administrator")

	def test_missing_value_returns_default(self):
		set_param("custom_quality_notification_owner", None)
		self.assertEqual(params.get("custom_quality_notification_owner", "fallback"), "fallback")


class TestAlerts(PEPLTestCase):
	RULE = "TEST-PEPL-OS"

	def _open_todos(self):
		return frappe.get_all(
			"ToDo",
			filters={
				"status": "Open",
				"reference_type": REF_DOCTYPE,
				"reference_name": REF_NAME,
				"description": ["like", f"%{self.RULE}%"],
			},
			pluck="name",
		)

	def test_raise_todo_is_idempotent_and_closes(self):
		set_param("enable_operational_todos", 1)
		alerts.raise_todo(self.RULE, REF_DOCTYPE, REF_NAME, "First text", allocated_to="Administrator")
		alerts.raise_todo(self.RULE, REF_DOCTYPE, REF_NAME, "Updated text", allocated_to="Administrator")
		self.assertEqual(len(self._open_todos()), 1)

		closed = alerts.close_resolved(self.RULE, REF_DOCTYPE, active_reference_names=[])
		self.assertGreaterEqual(closed, 1)
		self.assertEqual(self._open_todos(), [])

	def test_alerts_respect_master_switch(self):
		set_param("enable_operational_todos", 0)
		result = alerts.raise_todo(self.RULE, REF_DOCTYPE, REF_NAME, "Text", allocated_to="Administrator")
		self.assertEqual(result["action"], "disabled")
