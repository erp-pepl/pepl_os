"""C4-H1 - Idle logout (PEPL, 25 / 26 Nov 2026).

A login with no activity for more than Idle Logout (Hours) - 3, i.e. from 3 h 0 min 1 s - is logged out. The person
and every System Manager get an e-mail each time. Logins holding a role in "Idle Logout: Exempt Roles" (the PEPL Kiosk
tablets) are never logged out by this rule. 0 hours switches the rule off.

How activity is measured: Frappe writes a session's "last updated" time only every 10 minutes, so pepl_os records the
time of every request of every session itself (cache key pepl_session_seen, per session). Two guards act on it:
1. On the next request after the idle time (before_request): the session is ended at once and the request answered
   "Session Expired" - so a person who comes back after 3 h 0 min 1 s must log in again.
2. Every minute (scheduler): every session idle past the time is ended, so nobody stays logged in on an unattended
   screen. Without a request time (e.g. cache restarted), Frappe's own last-updated time + 10 minutes is used, so a
   session is never ended early.
Frappe's own Session Expiry (System Settings) must be longer than the PEPL idle time, or Frappe logs people out
first, silently.
Every logout is recorded in the Activity Log ("PEPL: no activity for 3 hours").
"""

import time

import frappe
from frappe import _
from frappe.sessions import delete_session, hash_sid
from frappe.utils import flt, get_datetime, now_datetime

from pepl_os.common import params

SEEN_KEY = "pepl_session_seen"
HOURS_FIELD = "custom_idle_logout_hours"
EXEMPT_FIELD = "custom_idle_logout_exempt_roles"
NOTIFY_FIELD = "custom_idle_logout_notify_system_managers"
DEFAULT_HOURS = 3
DEFAULT_EXEMPT = "PEPL Kiosk"
FRAPPE_DB_LAG = 600  # Frappe updates Sessions.lastupdate at most every 10 minutes


def limit_seconds():
	"""Idle time in seconds; 0 = rule off."""
	return max(0.0, flt(params.get(HOURS_FIELD, DEFAULT_HOURS))) * 3600


def exempt_roles():
	text = params.get(EXEMPT_FIELD, DEFAULT_EXEMPT)
	return [r.strip() for r in str(text if text is not None else DEFAULT_EXEMPT).splitlines() if r.strip()]


def is_exempt(user):
	if user in ("Guest", None, ""):
		return True
	roles = set(frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, pluck="role"))
	return bool(roles & set(exempt_roles()))


def seen(sid_hash):
	value = frappe.cache.hget(SEEN_KEY, sid_hash)
	return flt(value) if value else None


def mark_seen(sid_hash, when=None):
	frappe.cache.hset(SEEN_KEY, sid_hash, when or time.time())


def idle_seconds(last_seen, db_lastupdate, now=None):
	"""Seconds since the last activity. last_seen: epoch seconds of the last request (pepl_os); db_lastupdate:
	Frappe's Sessions.lastupdate (written at most every 10 minutes, so 10 minutes are added to it)."""
	now = now or time.time()
	if last_seen:
		return now - last_seen
	if db_lastupdate:
		return now - (get_datetime(db_lastupdate).timestamp() + FRAPPE_DB_LAG)
	return 0


def hours_text():
	hours = flt(params.get(HOURS_FIELD, DEFAULT_HOURS))
	return str(int(hours)) if hours == int(hours) else str(hours)


def end_session(user, sid_hash, idle):
	"""Log the session out and tell the person and the System Managers."""
	delete_session(sid_hash=sid_hash, user=user, reason=_("PEPL: no activity for {0} hours").format(hours_text()))
	frappe.cache.hdel(SEEN_KEY, sid_hash)
	notify(user, idle)


def system_managers():
	"""Enabled desk logins holding System Manager (Administrator left out)."""
	holders = frappe.get_all(
		"Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent", distinct=True
	)
	return frappe.get_all(
		"User",
		filters={
			"name": ["in", [u for u in holders if u not in ("Administrator", "Guest")] or [""]],
			"enabled": 1,
			"user_type": "System User",
		},
		pluck="name",
		order_by="name",
	)


def notify(user, idle):
	"""E-mail to the person and to every System Manager (PEPL: every time). Never raises."""
	when = now_datetime().strftime("%d-%m-%Y %H:%M")
	minutes = int(idle // 60)
	name = frappe.db.get_value("User", user, "full_name") or user
	try:
		frappe.sendmail(
			recipients=[user],
			subject=_("You were logged out of ERPNext (no activity for {0} hours)").format(hours_text()),
			message=_(
				"Dear {0},<br><br>Your ERPNext login was not used for {1} minutes, so it was logged out at {2} "
				"(PEPL rule: logout after {3} hours without activity). Please log in again when you need it."
			).format(name, minutes, when, hours_text()),
			now=False,
		)
		managers = [u for u in system_managers() if u != user]
		if managers and params.is_enabled(NOTIFY_FIELD, 1):
			frappe.sendmail(
				recipients=managers,
				subject=_("Idle logout: {0}").format(name),
				message=_(
					"{0} ({1}) was logged out at {2} after {3} minutes without activity (PEPL rule: {4} hours)."
				).format(name, user, when, minutes, hours_text()),
				now=False,
			)
	except Exception:
		frappe.log_error(title="PEPL: idle logout e-mail not sent")


# ---------------- 1. on every request ----------------
def before_request():
	"""hooks before_request: end a session that has been idle past the limit; otherwise record this request."""
	try:
		user = frappe.session.user
		sid = frappe.session.sid
		if not sid or user == "Guest" or sid == "Guest":
			return
		sid_hash = hash_sid(sid)
		limit = limit_seconds()
		last = seen(sid_hash)
		if limit and last and time.time() - last > limit and not is_exempt(user):
			end_session(user, sid_hash, time.time() - last)
			frappe.db.commit()
		else:
			mark_seen(sid_hash)
			return
	except Exception:
		frappe.log_error(title="PEPL: idle check failed (request let through)")
		return
	raise frappe.SessionExpired(_("Logged out after {0} hours without activity. Please log in again.").format(hours_text()))


# ---------------- 2. every minute ----------------
def run_idle_logout():
	"""scheduler (every minute): end every session idle past the limit. Returns the users logged out."""
	limit = limit_seconds()
	if not limit:
		return []
	ended = []
	now = time.time()
	for row in frappe.db.sql(
		"select user, sid, lastupdate from `tabSessions` where user not in ('Guest', '')", as_dict=True
	):
		idle = idle_seconds(seen(row.sid), row.lastupdate, now)
		if idle > limit and not is_exempt(row.user):
			end_session(row.user, row.sid, idle)
			ended.append(row.user)
	return ended


@frappe.whitelist()
def idle_status():
	"""Read-only facts for Check 81: the rule, Frappe's own expiry, and every open session's idle minutes."""
	frappe.only_for("System Manager")
	frappe_expiry = frappe.db.get_single_value("System Settings", "session_expiry") or "170:00"
	parts = [int(p) for p in str(frappe_expiry).split(":")[:2]] + [0, 0]
	sessions = []
	now = time.time()
	for row in frappe.db.sql(
		"select user, sid, lastupdate from `tabSessions` where user not in ('Guest', '')", as_dict=True
	):
		sessions.append(
			{
				"user": row.user,
				"idle_minutes": int(idle_seconds(seen(row.sid), row.lastupdate, now) // 60),
				"exempt": is_exempt(row.user),
				"request_time_known": bool(seen(row.sid)),
			}
		)
	return {
		"hours": limit_seconds() / 3600,
		"exempt_roles": exempt_roles(),
		"notify_system_managers": params.is_enabled(NOTIFY_FIELD, 1),
		"frappe_expiry": frappe_expiry,
		"frappe_expiry_hours": parts[0] + parts[1] / 60,
		"system_managers": system_managers(),
		"sessions": sessions,
		"scheduled": bool(
			frappe.db.exists("Scheduled Job Type", {"method": "pepl_os.pepl_people.idle_logout.run_idle_logout"})
		),
	}
