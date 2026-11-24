"""CR2 - Tender data open only to the Tender Access users.

PEPL Tender and PEPL CST Cost Sheet records (with every table inside them, their files, comments, change history,
assignments, shares, print / export logs and deleted copies, and the Generated Documents made for a tender) can be
opened only by the users listed in the site configuration, plus Administrator. Nobody else - System Managers and
the CEO included - sees them anywhere: not in lists, forms, reports, searches, links, the API or the PEPL Audit Trail.

The list lives in site_config.json, key `pepl_tender_access_users` (a JSON list of login emails), not in PEPL System
Parameters: System Managers can edit System Parameters, but not the site configuration (bench / Frappe Cloud
dashboard only). An empty or missing list switches the restriction off (every role works as before CR2).

Sales Orders stay open to every role that had them. Their Tender Reference and NIT Number fields move to
permission level 5 (SALES_ORDER_LEVEL), readable only by the role PEPL Tender Access, which this module gives to exactly the listed
users (and takes from anyone else whenever a User is saved, on every migrate and every day).
"""

import frappe
from frappe import _

CONF_KEY = "pepl_tender_access_users"
ACCESS_ROLE = "PEPL Tender Access"

TENDER = "PEPL Tender"
COST_SHEET = "PEPL CST Cost Sheet"
GENERATED = "PEPL Generated Document"  # restricted only when made for a tender (field "tender")
GATED = (TENDER, COST_SHEET)
CHILD_TABLES = (
	"PEPL Tender Item",
	"PEPL Tender Item Competitor",
	"PEPL Tender Bid Document",
	"PEPL Tender PO Schedule",
	"PEPL Tender Source Link",
	"PEPL CST Component",
	"PEPL CST Competitor History",
)

# Records that point at another record: DocType -> (field holding the DocType, field holding the name).
RELATED = {
	"File": ("attached_to_doctype", "attached_to_name"),
	"Version": ("ref_doctype", "docname"),
	"Comment": ("reference_doctype", "reference_name"),
	"ToDo": ("reference_type", "reference_name"),
	"Communication": ("reference_doctype", "reference_name"),
	"Deleted Document": ("deleted_doctype", "deleted_name"),
	"Activity Log": ("reference_doctype", "reference_name"),
	"Access Log": ("export_from", "reference_document"),
	"View Log": ("reference_doctype", "reference_name"),
	"Notification Log": ("document_type", "document_name"),
	"Email Queue": ("reference_doctype", "reference_name"),
	"DocShare": ("share_doctype", "share_name"),
}

# Sales Order fields hidden from everyone but the Tender Access users. Level 5, not 1: ERPNext's own Sales Order
# keeps "Ignore Pricing Rule" at level 1 with read + write for Sales Manager (Check 62 on the bench, 17 Nov 2026).
SALES_ORDER_FIELDS = ("custom_tender_reference", "custom_nit_number")
SALES_ORDER_LEVEL = 5

# Rights of the PEPL Tender Access role.
TENDER_RIGHTS = (
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"print",
	"email",
	"report",
	"export",
)
COST_SHEET_RIGHTS = ("read", "write", "create", "delete", "print", "email", "report", "export")

# pepl_sales API methods that read or change tender / Cost Sheet data without asking Frappe first.
GUARDED_METHODS = {
	"get_tender_summary": "pepl_sales.pepl_sales.doctype.pepl_tender.pepl_tender.get_tender_summary",
	"sync_components_from_product": (
		"pepl_sales.pepl_sales.doctype.pepl_cst_cost_sheet.pepl_cst_cost_sheet.sync_components_from_product"
	),
	"fetch_competitor_history": (
		"pepl_sales.pepl_sales.doctype.pepl_cst_cost_sheet.pepl_cst_cost_sheet.fetch_competitor_history"
	),
	"clone_cost_sheet_for_new_tender": (
		"pepl_sales.pepl_sales.doctype.pepl_cst_cost_sheet.pepl_cst_cost_sheet.clone_cost_sheet_for_new_tender"
	),
	"create_or_update_draft_bom": (
		"pepl_sales.pepl_sales.doctype.pepl_cst_cost_sheet.pepl_cst_cost_sheet.create_or_update_draft_bom"
	),
	"backfill_existing_tender_cost_sheets": (
		"pepl_sales.pepl_sales.tender_cst_sync.backfill_existing_tender_cost_sheets"
	),
	"run_tender_deadline_notifications": "pepl_sales.operational_notifications.run_tender_deadline_notifications",
}

RESTRICTED_MESSAGE = "Tender data (PEPL Tender, PEPL CST Cost Sheet) is open only to the Tender Access users."


# ---------------- who may see tender data ----------------
def allowed_users():
	"""The listed login emails, lower case, in the order written. Accepts a JSON list or a comma-separated text."""
	value = frappe.conf.get(CONF_KEY) or []
	if isinstance(value, str):
		value = value.split(",")
	out = []
	for email in value:
		email = (email or "").strip().lower()
		if email and email not in out:
			out.append(email)
	return out


def is_active():
	"""True when the restriction is on (at least one user listed)."""
	return bool(allowed_users())


def can_access(user=None):
	user = user or frappe.session.user
	if user == "Administrator" or not is_active():
		return True
	return (user or "").lower() in allowed_users()


def require_access():
	if not can_access():
		frappe.throw(_(RESTRICTED_MESSAGE), frappe.PermissionError)


def is_restricted(doctype, name=None):
	"""Does this record hold tender data?"""
	if doctype in GATED or doctype in CHILD_TABLES:
		return True
	if doctype == GENERATED and name:
		return bool(frappe.db.get_value(GENERATED, name, "tender"))
	return False


def first_allowed_user():
	for email in allowed_users():
		if frappe.db.get_value("User", email, "enabled"):
			return frappe.db.get_value("User", email, "name")
	return None


# ---------------- Frappe permission hooks ----------------
# Frappe v16 (permissions.has_controller_permissions): a hook can only refuse. Any falsy answer - None included -
# refuses, so these return True ("no objection, the roles decide") or False ("refused").
def has_permission(doc, ptype=None, user=None, debug=False):
	"""PEPL Tender, PEPL CST Cost Sheet, PEPL Generated Document."""
	if can_access(user):
		return True
	if doc.doctype == GENERATED and not doc.get("tender"):
		return True
	return False


def has_related_permission(doc, ptype=None, user=None, debug=False):
	"""File, Version, Comment, ToDo, ... pointing at tender data."""
	fields = RELATED.get(doc.doctype)
	if not fields or can_access(user):
		return True
	return not is_restricted(doc.get(fields[0]), doc.get(fields[1]))


def query_conditions(user=None, doctype=None):
	"""Lists, reports, link searches of PEPL Tender, PEPL CST Cost Sheet and the tables inside them.

	Frappe adds shared records back to a list whatever the conditions say, so sharing is refused (validate_docshare)
	and setup_cr2.py removes earlier shares."""
	return "" if can_access(user) else "1=0"


def generated_document_conditions(user=None, doctype=None):
	if can_access(user):
		return ""
	return f"(ifnull(`tab{GENERATED}`.`tender`, '') = '')"


def related_condition(doctype, user=None):
	if can_access(user):
		return ""
	type_field, name_field = RELATED[doctype]
	table = f"`tab{doctype}`"
	gated = ", ".join(frappe.db.escape(d) for d in (*GATED, *CHILD_TABLES))
	generated = frappe.db.escape(GENERATED)
	return (
		f"(ifnull({table}.`{type_field}`, '') not in ({gated})"
		f" and not (ifnull({table}.`{type_field}`, '') = {generated} and {table}.`{name_field}` in"
		f" (select `name` from `tab{GENERATED}` where ifnull(`tender`, '') != '')))"
	)


def file_conditions(user=None, doctype=None):
	return related_condition("File", user)


def version_conditions(user=None, doctype=None):
	return related_condition("Version", user)


def comment_conditions(user=None, doctype=None):
	return related_condition("Comment", user)


def todo_conditions(user=None, doctype=None):
	return related_condition("ToDo", user)


def communication_conditions(user=None, doctype=None):
	return related_condition("Communication", user)


def deleted_document_conditions(user=None, doctype=None):
	return related_condition("Deleted Document", user)


def activity_log_conditions(user=None, doctype=None):
	return related_condition("Activity Log", user)


def access_log_conditions(user=None, doctype=None):
	return related_condition("Access Log", user)


def view_log_conditions(user=None, doctype=None):
	return related_condition("View Log", user)


def notification_log_conditions(user=None, doctype=None):
	return related_condition("Notification Log", user)


def email_queue_conditions(user=None, doctype=None):
	return related_condition("Email Queue", user)


def docshare_conditions(user=None, doctype=None):
	return related_condition("DocShare", user)


# ---------------- guards on records that would pass tender data to someone else ----------------
def validate_todo(doc, method=None):
	"""An assignment of a tender / Cost Sheet goes only to a Tender Access user.

	A daily alert (made by the system, as Administrator) for a user outside the list goes to the first listed user;
	a person assigning by hand is told no."""
	if not is_active() or not doc.get("allocated_to"):
		return
	if not is_restricted(doc.get("reference_type"), doc.get("reference_name")):
		return
	if can_access(doc.allocated_to):
		return
	if frappe.session.user == "Administrator":
		target = first_allowed_user()
		if target:
			doc.allocated_to = target
			return
	frappe.throw(
		_("{0} cannot be given this assignment. {1}").format(doc.allocated_to, _(RESTRICTED_MESSAGE)),
		frappe.PermissionError,
	)


def validate_docshare(doc, method=None):
	"""A tender / Cost Sheet is never shared with someone outside the list, nor with everyone."""
	if not is_active() or not is_restricted(doc.get("share_doctype"), doc.get("share_name")):
		return
	if doc.get("everyone") or not can_access(doc.get("user")):
		frappe.throw(
			_("This record cannot be shared. {0}").format(_(RESTRICTED_MESSAGE)), frappe.PermissionError
		)


def validate_user(doc, method=None):
	"""The PEPL Tender Access role belongs to exactly the listed users: added to them, removed from anyone else."""
	user = doc.name or doc.get("email")
	if not user or user in ("Administrator", "Guest"):
		return
	wanted = is_active() and (user or "").lower() in allowed_users()
	held = [r for r in doc.get("roles") or [] if r.role == ACCESS_ROLE]
	if wanted and not held and frappe.db.exists("Role", ACCESS_ROLE):
		doc.append("roles", {"role": ACCESS_ROLE})
	elif held and not wanted:
		doc.set("roles", [r for r in doc.get("roles") if r.role != ACCESS_ROLE])


def guard_sales_order_tender(doc, method=None):
	"""Only the Tender Access users create a Sales Order from a tender (PEPL, Aviral ji, 16 Nov 2026): anyone else
	who sets or changes the Tender Reference - by the API, Data Import or code - is refused, not silently blanked.
	Sales Order before_insert (before Frappe blanks the tender fields) and before_validate (saves)."""
	if not is_active() or can_access():
		return
	field = SALES_ORDER_FIELDS[0]
	tender = doc.get(field)
	if not tender:
		return
	before = frappe.db.get_value("Sales Order", doc.name, field) if doc.get("name") else None
	if tender != before:
		frappe.throw(
			_("Only the Tender Access users can make a Sales Order from a tender ({0}). {1}").format(
				tender, _(RESTRICTED_MESSAGE)
			),
			frappe.PermissionError,
		)


# ---------------- set-up: rights, Sales Order fields, the role ----------------
def holders():
	return sorted(
		set(frappe.get_all("Has Role", filters={"role": ACCESS_ROLE, "parenttype": "User"}, pluck="parent"))
		- {"Administrator"}
	)


def sync_access_role():
	"""Save every user who should gain or lose the role (validate_user does the change). Returns what happened."""
	wanted = set(allowed_users()) if is_active() else set()
	have = {u.lower(): u for u in holders()}
	result = {"added": [], "removed": [], "not_a_user": []}
	for email in sorted(wanted | set(have)):
		if email in wanted and email in have:
			continue
		name = have.get(email) or frappe.db.get_value("User", email, "name")
		if not name:
			result["not_a_user"].append(email)
			continue
		frappe.get_doc("User", name).save(ignore_permissions=True)
		result["added" if email in wanted else "removed"].append(name)
	return result


def set_sales_order_field_level():
	"""Tender Reference and NIT Number at SALES_ORDER_LEVEL while the restriction is on, back at 0 when it is off."""
	level = SALES_ORDER_LEVEL if is_active() else 0
	changed = []
	for fieldname in SALES_ORDER_FIELDS:
		name = frappe.db.get_value("Custom Field", {"dt": "Sales Order", "fieldname": fieldname}, "name")
		if name and frappe.db.get_value("Custom Field", name, "permlevel") != level:
			frappe.db.set_value("Custom Field", name, "permlevel", level)
			changed.append(fieldname)
	if changed:
		frappe.clear_cache(doctype="Sales Order")
	return changed


def grant_access_rights():
	"""PEPL Tender Access: full rights on PEPL Tender and PEPL CST Cost Sheet; reads and writes the Sales Order's
	tender fields (SALES_ORDER_LEVEL, nobody else). The CEO's view of tender data (Work Package A) is taken away."""
	from frappe.permissions import add_permission, setup_custom_perms, update_permission_property

	from pepl_os.setup.permissions import grant_view

	if not frappe.db.exists("Role", ACCESS_ROLE):
		return []
	changed = grant_view(ACCESS_ROLE, [TENDER], TENDER_RIGHTS) + grant_view(
		ACCESS_ROLE, [COST_SHEET], COST_SHEET_RIGHTS
	)
	for doctype in GATED:
		if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": "PEPL CEO"}):
			frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": "PEPL CEO"})
			frappe.clear_cache(doctype=doctype)
			changed.append(doctype + " (CEO view removed)")
	so = "Sales Order"
	level = SALES_ORDER_LEVEL
	# 0.62.0 / 0.62.1 used level 1, which ERPNext shares with Sales Manager: that row of ours is removed.
	if frappe.db.exists("Custom DocPerm", {"parent": so, "role": ACCESS_ROLE, "permlevel": 1}):
		frappe.db.delete("Custom DocPerm", {"parent": so, "role": ACCESS_ROLE, "permlevel": 1})
		frappe.clear_cache(doctype=so)
		changed.append(so + " (level 1 row removed)")
	# Nobody else may hold the tender fields' level, even if added by hand in Role Permission Manager.
	others = {"parent": so, "permlevel": level, "role": ["!=", ACCESS_ROLE]}
	if frappe.db.exists("Custom DocPerm", others):
		frappe.db.delete("Custom DocPerm", others)
		frappe.clear_cache(doctype=so)
		changed.append(so + f" (other roles removed from level {level})")
	row = frappe.db.get_value(
		"Custom DocPerm",
		{"parent": so, "role": ACCESS_ROLE, "permlevel": level},
		["name", "read", "write"],
		as_dict=True,
	)
	if not (row and row.read and row.write):
		setup_custom_perms(so)
		if not row:
			add_permission(so, ACCESS_ROLE, level)
		for ptype in ("read", "write"):
			update_permission_property(so, ACCESS_ROLE, level, ptype, 1, validate=False)
		frappe.clear_cache(doctype=so)
		changed.append(so + f" (level {level})")
	return changed


def apply_access_setup():
	"""Everything CR2 sets on a site. Safe to run again; runs on every migrate and every day."""
	return {
		"rights": grant_access_rights(),
		"sales_order_fields": set_sales_order_field_level(),
		"role": sync_access_role(),
	}


def daily_sync():
	"""A change of the list in the site configuration takes effect for the role and the Sales Order fields."""
	set_sales_order_field_level()
	sync_access_role()


@frappe.whitelist()
def sync_now():
	"""Apply the list now (after changing the site configuration). System Manager."""
	frappe.only_for(("System Manager",))
	return apply_access_setup()


@frappe.whitelist()
def access_status():
	"""What Check 62 reads: is the restriction on, who is listed, who holds the role."""
	frappe.only_for(("System Manager",))
	listed = allowed_users()
	return {
		"active": is_active(),
		"listed": listed,
		"not_a_user": [e for e in listed if not frappe.db.exists("User", e)],
		"disabled": [
			e for e in listed if frappe.db.exists("User", e) and not frappe.db.get_value("User", e, "enabled")
		],
		"role_holders": holders(),
		"sales_order_field_levels": {
			f: frappe.db.get_value("Custom Field", {"dt": "Sales Order", "fieldname": f}, "permlevel")
			for f in SALES_ORDER_FIELDS
		},
		"sales_order_guard": all(
			f"{__name__}.guard_sales_order_tender"
			in (frappe.get_hooks("doc_events").get("Sales Order", {}).get(event) or [])
			for event in ("before_insert", "before_validate")
		),
		"guarded_methods": all(
			original in frappe.get_hooks("override_whitelisted_methods")
			for original in GUARDED_METHODS.values()
		),
	}


@frappe.whitelist()
def what_user_sees(user):
	"""For Check 62: how many tender records `user` would see, and whether they may open one. Only a Tender Access
	user (or Administrator) may ask, so the answer itself gives nothing away."""
	require_access()
	frappe.only_for(("System Manager",))
	counts = {}
	for doctype in (*GATED, "Version", "Comment", "File", "ToDo"):
		try:
			if doctype in GATED:
				names = frappe.get_list(doctype, user=user, pluck="name", limit_page_length=0)
			else:
				field = RELATED[doctype][0]
				names = frappe.get_list(
					doctype, filters={field: ["in", GATED]}, user=user, pluck="name", limit_page_length=0
				)
			counts[doctype] = len(names)
		except frappe.PermissionError:
			counts[doctype] = 0
		frappe.clear_last_message()
	sample = frappe.get_all(TENDER, pluck="name", limit=1)
	# frappe.has_permission (v16) has no print_logs (only frappe.permissions.has_permission has); with throw off it
	# prints nothing. 0.79.5: print_logs=False here stopped Check 62 with a TypeError on a site with tenders.
	opens = bool(sample) and bool(frappe.has_permission(TENDER, "read", doc=sample[0], user=user))
	order = None
	if frappe.db.has_column("Sales Order", SALES_ORDER_FIELDS[0]):
		order = (
			frappe.get_all(
				"Sales Order", filters={SALES_ORDER_FIELDS[0]: ["is", "set"]}, pluck="name", limit=1
			)
			or [None]
		)[0]
	return {
		"user": user,
		"allowed": can_access(user),
		"counts": counts,
		"opens_a_tender": opens,
		"tender_sales_order": order,
		"opens_tender_sales_order": bool(order)
		and bool(frappe.has_permission("Sales Order", "read", doc=order, user=user)),
	}


# ---------------- reports that read tender data directly ----------------
def filter_events(rows):
	"""PEPL Audit Trail: events about tender data only for Tender Access users."""
	if can_access():
		return rows
	return [r for r in rows if not is_restricted(r.get("reference_doctype"), r.get("reference_name"))]


# ---------------- pepl_sales API methods, guarded ----------------
def _guarded(key, kwargs):
	require_access()
	kwargs.pop("cmd", None)
	return frappe.call(GUARDED_METHODS[key], **kwargs)


@frappe.whitelist()
def get_tender_summary(**kwargs):
	return _guarded("get_tender_summary", kwargs)


@frappe.whitelist()
def sync_components_from_product(**kwargs):
	return _guarded("sync_components_from_product", kwargs)


@frappe.whitelist()
def fetch_competitor_history(**kwargs):
	return _guarded("fetch_competitor_history", kwargs)


@frappe.whitelist()
def clone_cost_sheet_for_new_tender(**kwargs):
	return _guarded("clone_cost_sheet_for_new_tender", kwargs)


@frappe.whitelist()
def create_or_update_draft_bom(**kwargs):
	return _guarded("create_or_update_draft_bom", kwargs)


@frappe.whitelist()
def backfill_existing_tender_cost_sheets(**kwargs):
	return _guarded("backfill_existing_tender_cost_sheets", kwargs)


@frappe.whitelist()
def run_tender_deadline_notifications(**kwargs):
	return _guarded("run_tender_deadline_notifications", kwargs)
