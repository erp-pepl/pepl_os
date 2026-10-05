# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""PEPL System Health: is every pepl_os job scheduled and actually running?"""

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

APP_PREFIX = "pepl_os."

# Healthy states. "Waiting for First Run": a new job whose first due time has not come yet
# (a monthly job installed after the 1st first runs on the next 1st).
WAITING = "Waiting for First Run"
OK_STATES = ("OK", WAITING)

# A job is "Stale" when its last success is older than this many hours.
STALE_AFTER_HOURS = {
	"all": 1,
	"hourly": 2,
	"hourly_long": 2,
	"daily": 26,
	"daily_long": 26,
	"weekly": 24 * 8,
	"weekly_long": 24 * 8,
	"monthly": 24 * 32,
	"monthly_long": 24 * 32,
	"cron": 26,
}


def get_pepl_jobs():
	"""(frequency, method) for every pepl_os job declared in hooks."""
	jobs = []
	for frequency, entries in (frappe.get_hooks("scheduler_events") or {}).items():
		if isinstance(entries, dict):  # cron: {"expr": [methods]}
			methods = [m for group in entries.values() for m in group]
		else:
			methods = entries
		for method in methods:
			if method.startswith(APP_PREFIX):
				jobs.append((frequency, method))
	return sorted(set(jobs), key=lambda j: j[1])


def _last_run(method, status):
	return frappe.db.get_value(
		"PEPL Job Run",
		{"method": method, "status": status},
		["finished_at", "records_touched", "message"],
		as_dict=True,
		order_by="started_at desc",
	)


def _first_run_not_due(scheduled_job, now):
	"""True when the scheduler has not yet reached this job's first due time."""
	doc = frappe.get_doc("Scheduled Job Type", scheduled_job)
	if doc.last_execution:
		return False
	try:
		return get_datetime(doc.get_next_execution()) > now
	except Exception:
		return False


def job_health(frequency, method, now=None):
	now = get_datetime(now or now_datetime())
	scheduled = frappe.db.get_value(
		"Scheduled Job Type", {"method": method}, ["name", "stopped", "last_execution"], as_dict=True
	)
	success = _last_run(method, "Success")
	failure = _last_run(method, "Failed")

	if not scheduled:
		status = "Not Scheduled"
	elif scheduled.stopped:
		status = "Stopped"
	elif not success and not failure and _first_run_not_due(scheduled.name, now):
		status = WAITING
	elif not success:
		status = "Never Run"
	elif get_datetime(success.finished_at) < add_to_date(now, hours=-STALE_AFTER_HOURS.get(frequency, 26)):
		status = "Stale"
	elif failure and get_datetime(failure.finished_at) > get_datetime(success.finished_at):
		status = "Last Run Failed"
	else:
		status = "OK"

	return {
		"method": method,
		"frequency": frequency,
		"status": status,
		"last_success": success.finished_at if success else None,
		"records_touched": success.records_touched if success else None,
		"message": success.message if success else "",
		"last_failure": failure.finished_at if failure else None,
		"scheduler_last_execution": scheduled.last_execution if scheduled else None,
	}


def _scheduler_enabled():
	try:
		from frappe.utils.scheduler import is_scheduler_disabled

		return not is_scheduler_disabled(verbose=False)
	except Exception:
		return None


def _app_versions():
	versions = {}
	for app in frappe.get_installed_apps():
		try:
			versions[app] = frappe.get_attr(f"{app}.__version__")
		except Exception:
			versions[app] = "?"
	return versions


@frappe.whitelist()
def get_health():
	frappe.only_for("System Manager")
	jobs = [job_health(freq, method) for freq, method in get_pepl_jobs()]
	return {
		"site": frappe.local.site,
		"checked_at": now_datetime(),
		"scheduler_enabled": _scheduler_enabled(),
		"apps": _app_versions(),
		"jobs": jobs,
		"all_ok": all(j["status"] in OK_STATES for j in jobs),
	}
