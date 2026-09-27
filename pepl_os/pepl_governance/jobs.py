"""Governance scheduled jobs."""

import frappe

from pepl_os.common.jobs import tracked_job


@tracked_job("Daily heartbeat")
def daily_heartbeat():
	"""Proves the scheduler runs pepl_os jobs on this site.

	If the PEPL System Health page shows this job as stale, no other daily
	job of pepl_os is running either: check the site's scheduler first.
	"""
	return {"records_touched": 0, "message": f"Scheduler alive on {frappe.local.site}"}
