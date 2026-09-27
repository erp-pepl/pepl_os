"""@tracked_job: every scheduled job leaves a PEPL Job Run row.

Cycle 1 lesson: a job can exist in code and never run. Each run of a tracked
job records start, finish, status, records touched and any error, which is
the evidence (in CI and on live) that the job actually runs.

A job may return:
  * a dict with "records_touched" (int) and optional "message" (str), or
  * an int (records touched), or
  * anything else (records touched = 0).
"""

import functools
import time

import frappe
from frappe.utils import cint, now_datetime

JOB_RUN = "PEPL Job Run"


def _in_test():
	return bool(getattr(frappe, "in_test", False) or frappe.flags.in_test)


def _commit():
	# Keep the run row even when the job fails. Tests roll back on their own.
	if not _in_test():
		frappe.db.commit()


def _rollback():
	if not _in_test():
		frappe.db.rollback()


def _summarise(result):
	if isinstance(result, dict):
		return cint(result.get("records_touched")), str(result.get("message") or "")[:1000]
	if isinstance(result, int) and not isinstance(result, bool):
		return result, ""
	return 0, ""


def _finish(run_name, status, started, records=0, message="", error=""):
	frappe.db.set_value(
		JOB_RUN,
		run_name,
		{
			"status": status,
			"finished_at": now_datetime(),
			"duration_seconds": round(time.monotonic() - started, 3),
			"records_touched": records,
			"message": message,
			"error": error,
		},
		update_modified=False,
	)


def tracked_job(job_name=None):
	"""Decorator for scheduled jobs. Usage: @tracked_job("Refresh purchase trackers")."""

	def decorator(fn):
		method = f"{fn.__module__}.{fn.__name__}"
		label = job_name or method

		@functools.wraps(fn)
		def wrapper(*args, **kwargs):
			run = frappe.get_doc(
				{
					"doctype": JOB_RUN,
					"job_name": label,
					"method": method,
					"status": "Running",
					"started_at": now_datetime(),
				}
			).insert(ignore_permissions=True)
			_commit()

			started = time.monotonic()
			try:
				result = fn(*args, **kwargs)
			except Exception:
				error = frappe.get_traceback()
				_rollback()
				_finish(run.name, "Failed", started, error=error)
				_commit()
				raise

			records, message = _summarise(result)
			_finish(run.name, "Success", started, records=records, message=message)
			_commit()
			return result

		wrapper.pepl_job_method = method
		wrapper.pepl_job_label = label
		return wrapper

	return decorator
