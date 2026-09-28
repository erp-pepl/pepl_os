"""A1 - Access audit: every login account, and which ones look shared.

Read-only. The report PEPL Access Audit shows the output; its Excel export
is the person -> role mapping sheet PEPL signs before A2.
"""

from itertools import pairwise

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime

# Words that usually mean a login belongs to a desk or department, not a person.
GENERIC_NAMES = (
	"account",
	"admin",
	"dispatch",
	"erp",
	"factory",
	"info",
	"office",
	"production",
	"purchase",
	"qc",
	"quality",
	"sales",
	"store",
	"test",
	"user",
)

LOOKBACK_DAYS = 90
SHARED_IP_WINDOW_MINUTES = 60
SKIP_USERS = ("Administrator", "Guest")


def _local_part(email):
	return (email or "").split("@")[0].lower()


def looks_generic(email):
	local = _local_part(email)
	return any(word in local for word in GENERIC_NAMES)


def multi_ip_logins(logins, window_minutes=SHARED_IP_WINDOW_MINUTES):
	"""True when two successful logins from different IPs fall within the window.

	`logins` is a list of (datetime, ip) for one user.
	"""
	ordered = sorted((get_datetime(t), ip) for t, ip in logins if ip)
	for (t1, ip1), (t2, ip2) in pairwise(ordered):
		if ip1 != ip2 and (t2 - t1).total_seconds() <= window_minutes * 60:
			return True
	return False


def _logins_since(since):
	rows = frappe.get_all(
		"Activity Log",
		filters={"operation": "Login", "status": "Success", "creation": [">=", since]},
		fields=["user", "creation", "ip_address"],
		limit_page_length=0,
	)
	by_user = {}
	for row in rows:
		by_user.setdefault(row.user, []).append((row.creation, row.ip_address))
	return by_user


def get_rows(as_of=None):
	as_of = get_datetime(as_of or now_datetime())
	since = add_days(as_of, -LOOKBACK_DAYS)
	logins = _logins_since(since)

	users = frappe.get_all(
		"User",
		filters={"name": ["not in", SKIP_USERS]},
		fields=["name", "full_name", "enabled", "user_type", "last_login", "last_ip"],
		order_by="enabled desc, name asc",
		limit_page_length=0,
	)

	rows = []
	for user in users:
		roles = sorted(
			frappe.get_all("Has Role", filters={"parent": user.name, "parenttype": "User"}, pluck="role")
		)
		profiles = frappe.get_all(
			"User Role Profile", filters={"parent": user.name, "parenttype": "User"}, pluck="role_profile"
		)
		user_logins = logins.get(user.name, [])
		flags = []
		if user.enabled and looks_generic(user.name):
			flags.append("Generic name - likely shared")
		if user.enabled and multi_ip_logins(user_logins):
			flags.append("Two IPs within an hour - likely shared")
		if user.enabled and "System Manager" in roles:
			flags.append("Has System Manager")
		if user.enabled and not user.last_login:
			flags.append("Never logged in")
		elif user.enabled and user.last_login and getdate(user.last_login) < getdate(since):
			flags.append(f"No login in {LOOKBACK_DAYS} days")

		rows.append(
			{
				"user": user.name,
				"full_name": user.full_name,
				"enabled": user.enabled,
				"user_type": user.user_type,
				"role_profiles": ", ".join(sorted(profiles)),
				"roles": ", ".join(roles),
				"last_login": user.last_login,
				"last_ip": user.last_ip,
				"logins_90_days": len(user_logins),
				"distinct_ips_90_days": len({ip for _, ip in user_logins if ip}),
				"flags": "; ".join(flags),
				"proposed_person": "",
				"proposed_role_profile": "",
				"action": "",
			}
		)
	return rows
