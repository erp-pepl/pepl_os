"""A2 - Roles and the seven PEPL Role Profiles.

Profiles are built from standard ERPNext roles plus PEPL roles. Seeding is
additive: missing roles are added to a profile, roles PEPL adds by hand are
never removed. Roles that do not exist on a site (e.g. a module not in use)
are skipped rather than failing the install.
"""

import frappe

# New PEPL roles created by pepl_os. Later cycles add theirs here
# (e.g. "PEPL Weighment", "PEPL Kiosk", "PEPL Tally Ingest").
PEPL_ROLES = (
	"PEPL CEO",
	"PEPL Weighment",  # C2-18: the weighbridge / scrap weighment operator
	"PEPL Kiosk",  # C3a-B1: the shop-floor kiosk device (web pages only, no Desk)
	# CR2: given by pepl_os to exactly the users in site_config.json pepl_tender_access_users (never in a profile)
	"PEPL Tender Access",
	# CR3 (PEPL's access plan, 24 Nov 2026): rights in pepl_os.pepl_governance.access_plan.VIEW_GRANTS
	"PEPL Stock Viewer",  # stock, receipts, deliveries: view only (Quality, the Production & Quality Viewer)
	"PEPL Quality Executive",  # inspects and raises NCRs; never signs off, closes or cancels
	"PEPL Production Quality Viewer",  # production and quality records: view only
	"PEPL Sales Invoicing",  # raises Sales Invoices without the rest of Accounts (Decision 11)
)
NO_DESK_ROLES = ("PEPL Kiosk",)
ROLE_HOME_PAGES = {"PEPL Kiosk": "kiosk"}  # C3a-B1: the page a kiosk login opens

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
	# CR3 Decision 1: new Items only by the holders of "PEPL Item Master" (Item Manager left this profile).
	"PEPL Purchase Manager": (
		"Purchase Manager",
		"Purchase User",
		"Purchase Master Manager",
		"Stock User",
	),
	"PEPL Stores": ("Stock User", "PEPL Weighment"),
	# CR3 Decision 3: the Stores HOD - stock correction after a count (Stock Reconciliation), cycle count and
	# reorder review approval, cancels stores records (Decision 4).
	"PEPL Stores Manager": ("Stock Manager", "Stock User", "PEPL Weighment"),
	"PEPL Production Manager": ("Manufacturing Manager", "Manufacturing User", "Stock User"),
	"PEPL Foreman": ("Manufacturing User",),
	# C3a-B1: the login of a kiosk tablet beside the machines (operators sign in on it with code + PIN)
	"PEPL Kiosk": ("PEPL Kiosk",),
	# CR3 Decision 8: Quality sees stock but does not post it (Stock User left this profile).
	"PEPL Quality Manager": ("Quality Manager", "PEPL Stock Viewer"),
	"PEPL Quality Executive": ("PEPL Quality Executive", "PEPL Stock Viewer"),
	"PEPL Accounts": ("Accounts Manager", "Accounts User"),
	# CR3 Decision 4: accounts staff. Books bills, invoices, payments and journals; the Accounts HOD (PEPL Accounts)
	# cancels them.
	"PEPL Accountant": ("Accounts User",),
	# View-everything access for PEPL CEO is granted by pepl_os.setup.permissions.grant_ceo_view.
	# CR2: the CEO no longer sees tenders (only the Tender Access users do)
	"PEPL CEO": ("PEPL CEO",),
	# Cycle 1 (pepl_sales) jobs, so every login can be given a profile.
	# CR2: Sales and Tender are separate jobs. "PEPL Tender Only" is for the Tender Access users; Sales User lets
	# them make the Sales Order from a won tender. A tender opens only for the users listed in site_config.json,
	# whatever profile anyone else is given.
	"PEPL Sales Manager": ("Sales Manager", "Sales User", "Sales Master Manager"),
	"PEPL Sales Executive": ("Sales User",),
	"PEPL Tender Only": ("PEPL Tender Manager", "Sales User"),
	"PEPL Engineering": ("Engineering Manager", "Engineering User"),
	# CR3: view only, for people who follow production and quality without working on it.
	"PEPL Production & Quality Viewer": ("PEPL Production Quality Viewer", "PEPL Stock Viewer"),
	# CR3 add-on profiles: given on top of a person's job profile, for one named right PEPL gave to named people.
	"PEPL Item Master": ("Item Manager",),  # Decision 1: makes new Items (and Warehouses, Item Groups, UOMs)
	"PEPL Supplier Master": ("Purchase Master Manager",),  # Decision 2: adds Suppliers and buying prices
	"PEPL Sales Invoicing": ("PEPL Sales Invoicing",),  # Decision 11: raises Sales Invoices
}

# Add-on profiles are never a person's only profile (the Access Planning Pack lists them separately).
ADD_ON_PROFILES = ("PEPL Item Master", "PEPL Supplier Master", "PEPL Sales Invoicing")

# One-time corrections to profiles already seeded on a site (applied by patch,
# never on every migrate, so a role PEPL adds back by hand stays).
PROFILE_CORRECTIONS_V0_3 = {
	# Stores must not raise or approve Purchase Orders (Purchase User can).
	"PEPL Stores": ("Purchase User",),
}

# CR2 (0.62.0): the CEO's tender view goes; the two Sales & Tender profiles become Sales-only profiles
# (renamed, so the users holding them keep them).
PROFILE_CORRECTIONS_V0_62 = {
	"PEPL CEO": ("PEPL Tender Viewer",),
	"PEPL Sales & Tender Manager": ("PEPL Tender Manager", "PEPL Tender Executive", "PEPL Tender Viewer"),
	"PEPL Sales & Tender Executive": ("PEPL Tender Manager", "PEPL Tender Executive", "PEPL Tender Viewer"),
}
# CR3 (0.79.0): Decision 1 - Items only through PEPL Item Master; Decision 8 - Quality views stock, Stores posts it.
PROFILE_CORRECTIONS_V0_79 = {
	"PEPL Purchase Manager": ("Item Manager",),
	"PEPL Quality Manager": ("Stock User",),
}
PROFILE_RENAMES_V0_62 = {
	"PEPL Sales & Tender Manager": "PEPL Sales Manager",
	"PEPL Sales & Tender Executive": "PEPL Sales Executive",
}


def rename_profiles(renames):
	"""Rename Role Profiles (users keep them). A profile whose new name is already taken keeps its old name.
	Returns {old: new} for the ones renamed."""
	done = {}
	for old, new in renames.items():
		if frappe.db.exists("Role Profile", old) and not frappe.db.exists("Role Profile", new):
			frappe.rename_doc("Role Profile", old, new, force=True, show_alert=False)
			done[old] = new
	return done


def ensure_roles():
	for role_name in PEPL_ROLES:
		if not frappe.db.exists("Role", role_name):
			frappe.get_doc(
				{
					"doctype": "Role",
					"role_name": role_name,
					"desk_access": 0 if role_name in NO_DESK_ROLES else 1,
					"home_page": ROLE_HOME_PAGES.get(role_name, ""),
				}
			).insert(ignore_permissions=True)
		elif ROLE_HOME_PAGES.get(role_name) and not frappe.db.get_value("Role", role_name, "home_page"):
			# a home page set by hand is kept
			frappe.db.set_value("Role", role_name, "home_page", ROLE_HOME_PAGES[role_name])


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
