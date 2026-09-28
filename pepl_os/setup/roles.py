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

# Role Profile -> roles. One profile = one job at PEPL. Names are in PEPL's
# words, prefixed "PEPL". A user may hold more than one profile; Frappe then
# gives the user every role of every profile, and removes roles that are in
# none of them. So each profile must carry everything that job needs.
#
# Why each role is there (ERPNext v16 standard permissions):
#   Purchase Master Manager  create Suppliers and Item Prices (Purchase Manager can only edit them)
#   Item Manager             create Items and Warehouses (no other role can)
#   Stock User               read stock, raise Material Requests, receive goods (GRN), move stock
#   Sales Master Manager     create Item Prices / Price Lists for selling
#   PEPL Tender *            the Cycle 1 tender screens (pepl_sales)
#   Engineering *            product master, drawings, vendor approval (pepl_sales)
ROLE_PROFILES = {
	# Cycle 2 onwards
	"PEPL Purchase Manager": (
		"Purchase Manager",
		"Purchase User",
		"Purchase Master Manager",
		"Item Manager",
		"Stock User",
	),
	"PEPL Stores": ("Stock User",),
	"PEPL Production Manager": ("Manufacturing Manager", "Manufacturing User", "Stock User"),
	"PEPL Foreman": ("Manufacturing User",),
	"PEPL Quality Manager": ("Quality Manager", "Stock User"),
	"PEPL Accounts": ("Accounts Manager", "Accounts User"),
	# View-everything access for PEPL CEO is granted by pepl_os.setup.permissions.grant_ceo_view.
	"PEPL CEO": ("PEPL CEO", "PEPL Tender Viewer"),
	# Cycle 1 (pepl_sales) jobs, so every login can be given a profile
	"PEPL Sales & Tender Manager": (
		"Sales Manager",
		"Sales User",
		"Sales Master Manager",
		"PEPL Tender Manager",
	),
	"PEPL Sales & Tender Executive": ("Sales User", "PEPL Tender Executive"),
	"PEPL Engineering": ("Engineering Manager", "Engineering User"),
}

# One-time corrections to profiles already seeded on a site (applied by patch,
# never on every migrate, so a role PEPL adds back by hand stays).
PROFILE_CORRECTIONS_V0_3 = {
	# Stores must not raise or approve Purchase Orders (Purchase User can).
	"PEPL Stores": ("Purchase User",),
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


def remove_roles_from_profiles(corrections):
	"""Remove listed roles from listed profiles. Returns what changed."""
	changed = {}
	for profile_name, roles in corrections.items():
		if not frappe.db.exists("Role Profile", profile_name):
			continue
		profile = frappe.get_doc("Role Profile", profile_name)
		keep = [row for row in profile.roles if row.role not in roles]
		if len(keep) == len(profile.roles):
			continue
		removed = sorted({row.role for row in profile.roles} - {row.role for row in keep})
		profile.set("roles", [{"role": row.role} for row in keep])
		profile.save(ignore_permissions=True)
		changed[profile_name] = removed
	return changed
