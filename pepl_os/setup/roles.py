"""A2 - Roles and the seven PEPL Role Profiles.

Profiles are built from standard ERPNext roles plus PEPL roles. Seeding is
additive: missing roles are added to a profile, roles PEPL adds by hand are
never removed. Roles that do not exist on a site (e.g. a module not in use)
are skipped rather than failing the install.
"""

import frappe

# New PEPL roles created by pepl_os. Later cycles add theirs here
# (e.g. "PEPL Weighment", "PEPL Kiosk", "PEPL Tally Ingest").
PEPL_ROLES = ("PEPL CEO",)

# Role Profile -> roles. Names are in PEPL's words, prefixed "PEPL".
ROLE_PROFILES = {
	"PEPL Purchase Manager": ("Purchase Manager", "Purchase User", "Stock User"),
	"PEPL Stores": ("Stock User", "Purchase User"),
	"PEPL Production Manager": ("Manufacturing Manager", "Manufacturing User", "Stock User"),
	"PEPL Foreman": ("Manufacturing User",),
	"PEPL Quality Manager": ("Quality Manager", "Stock User"),
	"PEPL Accounts": ("Accounts Manager", "Accounts User"),
	"PEPL CEO": ("PEPL CEO",),
}


def ensure_roles():
	for role_name in PEPL_ROLES:
		if not frappe.db.exists("Role", role_name):
			frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": 1}).insert(
				ignore_permissions=True
			)


def ensure_role_profiles():
	for profile_name, roles in ROLE_PROFILES.items():
		existing_roles = [r for r in roles if frappe.db.exists("Role", r)]

		if frappe.db.exists("Role Profile", profile_name):
			profile = frappe.get_doc("Role Profile", profile_name)
			have = {row.role for row in profile.roles}
			missing = [r for r in existing_roles if r not in have]
			if not missing:
				continue
			for role in missing:
				profile.append("roles", {"role": role})
			profile.save(ignore_permissions=True)
		else:
			profile = frappe.get_doc(
				{
					"doctype": "Role Profile",
					"role_profile": profile_name,
					"roles": [{"role": r} for r in existing_roles],
				}
			)
			profile.insert(ignore_permissions=True)
