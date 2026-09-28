# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""PEPL Access Audit: every login account, flags for shared or risky logins.

Export to Excel, fill in the three "Proposed" columns with PEPL, and that
sheet is the signed person -> role mapping used to create named users.
"""

from frappe import _

from pepl_os.pepl_governance.access_audit import LOOKBACK_DAYS, get_rows


def execute(filters=None):
	rows = get_rows()
	flagged = sum(1 for r in rows if r["flags"])
	message = _("{0} accounts, {1} flagged. Login history covers the last {2} days.").format(
		len(rows), flagged, LOOKBACK_DAYS
	)
	return get_columns(), rows, message


def get_columns():
	return [
		{"fieldname": "user", "label": _("Login"), "fieldtype": "Link", "options": "User", "width": 220},
		{"fieldname": "full_name", "label": _("Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "enabled", "label": _("Enabled"), "fieldtype": "Check", "width": 80},
		{"fieldname": "user_type", "label": _("User Type"), "fieldtype": "Data", "width": 110},
		{"fieldname": "flags", "label": _("Flags"), "fieldtype": "Data", "width": 300},
		{"fieldname": "role_profiles", "label": _("Role Profiles"), "fieldtype": "Data", "width": 160},
		{"fieldname": "roles", "label": _("Roles"), "fieldtype": "Small Text", "width": 300},
		{"fieldname": "last_login", "label": _("Last Login"), "fieldtype": "Datetime", "width": 160},
		{"fieldname": "last_ip", "label": _("Last IP"), "fieldtype": "Data", "width": 120},
		{"fieldname": "logins_90_days", "label": _("Logins (90 d)"), "fieldtype": "Int", "width": 100},
		{"fieldname": "distinct_ips_90_days", "label": _("IPs (90 d)"), "fieldtype": "Int", "width": 90},
		{"fieldname": "proposed_person", "label": _("Proposed: Person"), "fieldtype": "Data", "width": 160},
		{
			"fieldname": "proposed_role_profile",
			"label": _("Proposed: Role Profile"),
			"fieldtype": "Data",
			"width": 170,
		},
		{
			"fieldname": "action",
			"label": _("Action (Keep / Create / Retire)"),
			"fieldtype": "Data",
			"width": 190,
		},
	]
