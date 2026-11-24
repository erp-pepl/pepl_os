"""CR3 - PEPL's access plan (Access Planning Pack, answers of 24 Nov 2026).

What PEPL decided, and where it is enforced:

* Decision 4 - Cancel only by the department head (HOD). Every submittable record in CANCEL_RULES can be cancelled
  only by its HOD role (and the System Manager); the right is taken from every other role on each deploy. Every
  cancellation is e-mailed in a daily (or weekly) summary.
* Decision 7 - BOMs are made and changed only by the Production Manager (Manufacturing Manager role); the Foreman
  (Manufacturing User) keeps read.
* Decision 9 - Export to Excel only for the CEO (and the System Manager). Every other role loses Export on every
  DocType on each deploy. Blank import templates still download (Frappe asks only for read there). Tender data keeps
  CR2's rule: only the Tender Access users (who alone can open it) may export it.
* Decisions 3, 8, 1, 2, 11 and the "Exec" / "view only" notes - new Role Profiles and roles (setup/roles.py) and the
  read rights they need (VIEW_GRANTS below).

The three switches and the summary live in PEPL System Parameters -> Access. Rights given by hand in Role Permission
Manager that break a rule are taken away again at the next deploy, as with the delete restriction (Work Package A).
"""

import frappe
from frappe import _
from frappe.permissions import setup_custom_perms
from frappe.utils import add_days, cint, get_datetime, getdate, today

from pepl_os.common import params
from pepl_os.common.jobs import tracked_job
from pepl_os.setup.permissions import CEO_ROLE, ceo_view_doctypes, grant_view, perm_rows

ALWAYS = ("System Manager", "Administrator")

# ---------------- Decision 4: who may cancel ----------------
# DocType -> the HOD roles that may cancel it. Tender data is not here: CR2 decides who works on tenders.
CANCEL_RULES = {
	# Sales
	"Quotation": ("Sales Manager",),
	"Sales Order": ("Sales Manager",),
	"Delivery Note": ("Stock Manager", "Sales Manager"),
	"Sales Invoice": ("Accounts Manager",),
	# Purchase
	"Material Request": ("Purchase Manager", "Stock Manager"),
	"Request for Quotation": ("Purchase Manager",),
	"Supplier Quotation": ("Purchase Manager",),
	"Purchase Order": ("Purchase Manager",),
	"PEPL Quotation Comparison": ("Purchase Manager",),
	"PEPL Payment Run": ("Purchase Manager",),
	# Stores
	"Purchase Receipt": ("Stock Manager",),
	"Stock Entry": ("Stock Manager", "Manufacturing Manager"),
	"Stock Reconciliation": ("Stock Manager",),
	"PEPL Cycle Count": ("Stock Manager",),
	"PEPL Reorder Review": ("Stock Manager",),
	"PEPL Scrap Weighment": ("Stock Manager",),
	"PEPL Scrap Sale": ("Stock Manager",),
	# Production
	"BOM": ("Manufacturing Manager",),
	"Work Order": ("Manufacturing Manager",),
	"Job Card": ("Manufacturing Manager",),
	"Production Plan": ("Manufacturing Manager",),
	"PEPL Shift Production Entry": ("Manufacturing Manager",),
	# Quality
	"Quality Inspection": ("Quality Manager",),
	"PEPL Calibration Record": ("Quality Manager",),
	# Accounts
	"Purchase Invoice": ("Accounts Manager",),
	"Payment Entry": ("Accounts Manager",),
	"Journal Entry": ("Accounts Manager",),
}

# Frappe refuses (in Role Permission Manager) a Cancel right without Write and Submit, so a HOD role that has no row
# on the DocType gets these together. Every PEPL profile holding such a HOD role already has the User role with
# write and submit, so nothing new is opened except Cancel.
HOD_ROW_RIGHTS = ("read", "write", "submit", "cancel")

# ---------------- Decision 7: rights taken away from a role ----------------
# (DocType, role) -> rights removed on each deploy (switch: BOM made by the Production Manager only).
RIGHT_REMOVALS = {
	("BOM", "Manufacturing User"): ("create", "write", "submit", "cancel", "amend", "import"),
}

# ---------------- Decision 9: who may export ----------------
EXPORT_ROLES = (CEO_ROLE,)
# CR2: tender data is open only to the Tender Access users; they keep its export (nobody else can read it).
EXPORT_EXCEPTIONS = {
	"PEPL Tender": ("PEPL Tender Access",),
	"PEPL CST Cost Sheet": ("PEPL Tender Access",),
}

# ---------------- read access the new roles need ----------------
STOCK_VIEWER = "PEPL Stock Viewer"
QUALITY_EXECUTIVE = "PEPL Quality Executive"
OPS_VIEWER = "PEPL Production Quality Viewer"
SALES_INVOICING = "PEPL Sales Invoicing"

VIEW = ("read", "print", "report")

# What the Stock User role reads (the Quality Manager had it until CR3), as view only.
STOCK_VIEW_DOCTYPES = (
	"Item",
	"Item Group",
	"UOM",
	"Warehouse",
	"Batch",
	"Bin",
	"Stock Ledger Entry",
	"Serial and Batch Bundle",
	"Purchase Receipt",
	"Delivery Note",
	"Stock Entry",
	"Material Request",
	"Purchase Order",
	"Work Order",
	"PEPL Receipt Log",
	"PEPL Capital Equipment",
	"PEPL Cycle Count",
	"PEPL Reorder Review",
	"PEPL Scrap Weighment",
	"PEPL Scrap Sale",
)

PRODUCTION_VIEW_DOCTYPES = (
	"BOM",
	"Work Order",
	"Job Card",
	"Production Plan",
	"Workstation",
	"PEPL Shift",
	"PEPL Operator",
	"PEPL Downtime Category",
	"PEPL Shift Production Entry",
	"PEPL OEE Daily",
	"PEPL Machine Week",
	"PEPL Daily Standup",
)

QUALITY_VIEW_DOCTYPES = (
	"Quality Inspection",
	"Quality Inspection Template",
	"Quality Inspection Parameter",
	"PEPL Instrument",
	"PEPL Calibration Record",
	"PEPL NCR",
	"PEPL CAPA",
	"PEPL Inspection Lot",
)

# The masters an invoice form searches in; select only.
INVOICE_LOOKUPS = (
	"Account",
	"Cost Center",
	"Item Tax Template",
	"Sales Taxes and Charges Template",
	"Payment Terms Template",
	"Mode of Payment",
)

# (role, DocTypes, rights). Additive only, like the CEO's view (Work Package A).
VIEW_GRANTS = (
	(STOCK_VIEWER, STOCK_VIEW_DOCTYPES, VIEW),
	(OPS_VIEWER, PRODUCTION_VIEW_DOCTYPES + QUALITY_VIEW_DOCTYPES, VIEW),
	# Quality Executive: inspects (makes and submits Quality Inspections, never cancels), raises NCRs, records
	# calibrations and lots; reads CAPAs, instruments and plans. Sign-off and closing stay with the Quality Manager.
	(
		QUALITY_EXECUTIVE,
		("Quality Inspection",),
		("read", "write", "create", "submit", "print", "email", "report"),
	),
	(
		QUALITY_EXECUTIVE,
		("PEPL NCR", "PEPL Inspection Lot"),
		("read", "write", "create", "print", "email", "report"),
	),
	(
		QUALITY_EXECUTIVE,
		("PEPL Calibration Record",),
		("read", "write", "create", "submit", "print", "report"),
	),
	(
		QUALITY_EXECUTIVE,
		("PEPL CAPA", "PEPL Instrument", "Quality Inspection Template", "Quality Inspection Parameter"),
		VIEW,
	),
	# Decision 11: raises Sales Invoices (Bisal) without the rest of Accounts; never cancels (the HOD does).
	(SALES_INVOICING, ("Sales Invoice",), ("read", "write", "create", "submit", "print", "email", "report")),
	(SALES_INVOICING, INVOICE_LOOKUPS, ("select",)),
)

# Reports the new roles open. A Custom Role replaces a report's own role list in Frappe, so the report's roles are
# copied in first and ours added.
REPORT_ROLES = {
	"Stock Balance": (STOCK_VIEWER,),
	"Stock Ledger": (STOCK_VIEWER,),
	"Stock Projected Qty": (STOCK_VIEWER,),
	"Batch-Wise Balance History": (STOCK_VIEWER,),
	"Warehouse Wise Stock Balance": (STOCK_VIEWER,),
	"Stock Ageing": (STOCK_VIEWER,),
	"PEPL Heat Number Trace": (STOCK_VIEWER,),
	"PEPL CSM Balance by Order": (STOCK_VIEWER,),
	"PEPL Bottleneck": (OPS_VIEWER,),
	"PEPL Downtime by Cause": (OPS_VIEWER,),
	"PEPL Skill Matrix": (OPS_VIEWER,),
	"PEPL Cost of Quality": (OPS_VIEWER,),
}

WORKSPACE_ROLES = {
	"Production Command Centre": (OPS_VIEWER,),
	"Quality Command Centre": (OPS_VIEWER, QUALITY_EXECUTIVE),
}


def set_right(doctype, role, permlevel, if_owner, ptype, value):
	"""Set one right on exactly one rule (role, level, if-owner). Frappe's update_permission_property finds the rule
	without looking at if-owner, so a role with both kinds of rule could have the wrong one changed."""
	setup_custom_perms(doctype)  # copies the standard rules first, as Role Permission Manager does
	name = frappe.db.get_value(
		"Custom DocPerm",
		{"parent": doctype, "role": role, "permlevel": permlevel or 0, "if_owner": 1 if if_owner else 0},
	)
	if not name:
		return False
	doc = frappe.get_doc("Custom DocPerm", name)
	doc.set(ptype, value)
	doc.save(ignore_permissions=True)  # leaves a Permission Log, like Role Permission Manager
	return True


# ---------------- switches ----------------
def cancel_rule_on():
	return params.is_enabled("custom_cancel_only_by_hod", 1)


def bom_rule_on():
	return params.is_enabled("custom_bom_by_production_manager_only", 1)


def export_rule_on():
	return params.is_enabled("custom_restrict_export_to_ceo", 1)


def _lines(fieldname):
	return [line.strip() for line in (params.get(fieldname, "") or "").splitlines() if line.strip()]


# ---------------- Decision 4 ----------------
def may_cancel(doctype, role):
	return role in ALWAYS or role in CANCEL_RULES.get(doctype, ())


def cancel_offenders(doctype):
	"""Roles that can still cancel `doctype` against the rule (level 0)."""
	return sorted(
		{
			r.role
			for r in perm_rows(doctype)
			if r.cancel and not r.permlevel and not may_cancel(doctype, r.role)
		}
	)


def restrict_cancel(doctypes=None, force=False):
	"""Take Cancel from every role that is not the HOD of the record. Returns {doctype: [roles]}."""
	changed = {}
	if not (force or cancel_rule_on()):
		return changed
	for doctype in doctypes or CANCEL_RULES:
		if not frappe.db.exists("DocType", doctype):
			continue
		rows = [
			r for r in perm_rows(doctype) if r.cancel and not r.permlevel and not may_cancel(doctype, r.role)
		]
		for row in rows:
			set_right(doctype, row.role, 0, row.if_owner, "cancel", 0)
		if rows:
			frappe.clear_cache(doctype=doctype)
			changed[doctype] = sorted({r.role for r in rows})
	return changed


def ensure_hod_cancel(doctypes=None, force=False):
	"""Every HOD role of a record can cancel it. Returns the DocTypes changed."""
	changed = []
	if not (force or cancel_rule_on()):
		return changed
	for doctype in doctypes or CANCEL_RULES:
		if not frappe.db.exists("DocType", doctype):
			continue
		for role in CANCEL_RULES[doctype]:
			if not frappe.db.exists("Role", role):
				continue
			row = next(
				(r for r in perm_rows(doctype) if r.role == role and not r.permlevel and not r.if_owner), None
			)
			rights = ("cancel",) if row and row.write and row.submit else HOD_ROW_RIGHTS
			if grant_view(role, [doctype], rights):
				changed.append(f"{doctype}: {role}")
	return changed


# ---------------- Decision 7 ----------------
def removal_offenders():
	"""{(doctype, role): [rights still held against the rule]}."""
	found = {}
	for (doctype, role), rights in RIGHT_REMOVALS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		held = sorted(
			{p for r in perm_rows(doctype) if r.role == role and not r.permlevel for p in rights if r.get(p)}
		)
		if held:
			found[(doctype, role)] = held
	return found


def restrict_rights(force=False):
	"""Take the listed rights away (e.g. BOM from the Foreman). Returns {"doctype / role": [rights]}."""
	changed = {}
	if not (force or bom_rule_on()):
		return changed
	for (doctype, role), held in removal_offenders().items():
		for row in perm_rows(doctype):
			if row.role != role or row.permlevel:
				continue
			for ptype in held:
				if row.get(ptype):
					set_right(doctype, role, 0, row.if_owner, ptype, 0)
		frappe.clear_cache(doctype=doctype)
		changed[f"{doctype} / {role}"] = held
	return changed


# ---------------- Decision 9 ----------------
def export_allowed_roles(doctype=None, base=None):
	if base is None:
		base = set(ALWAYS) | set(EXPORT_ROLES) | set(_lines("custom_export_also_allowed_roles"))
	return set(base) | set(EXPORT_EXCEPTIONS.get(doctype, ()))


def _export_rows(doctypes=None):
	"""Rows granting Export: Custom DocPerm where a DocType has them, else the standard DocPerm."""
	customised = set(frappe.get_all("Custom DocPerm", pluck="parent"))
	filters = {"export": 1}
	if doctypes:
		filters["parent"] = ["in", list(doctypes)]
	fields = ["parent", "role", "permlevel", "if_owner"]
	rows = frappe.get_all("Custom DocPerm", filters=filters, fields=fields)
	rows += [
		r for r in frappe.get_all("DocPerm", filters=filters, fields=fields) if r.parent not in customised
	]
	return rows


def export_offenders(doctypes=None):
	"""{doctype: [roles that can export against the rule]}."""
	found = {}
	base = export_allowed_roles()
	for row in _export_rows(doctypes):
		if row.role not in export_allowed_roles(row.parent, base):
			found.setdefault(row.parent, set()).add(row.role)
	return {d: sorted(r) for d, r in sorted(found.items())}


def restrict_export(doctypes=None, force=False):
	"""Take Export from every role except the CEO and System Manager. Returns {doctype: [roles]}."""
	changed = {}
	if not (force or export_rule_on()):
		return changed
	base = export_allowed_roles()
	for row in _export_rows(doctypes):
		if row.role in export_allowed_roles(row.parent, base):
			continue
		if not frappe.db.exists("DocType", row.parent):
			continue
		set_right(row.parent, row.role, row.permlevel, row.if_owner, "export", 0)
		changed.setdefault(row.parent, set()).add(row.role)
	for doctype in changed:
		frappe.clear_cache(doctype=doctype)
	return {d: sorted(r) for d, r in changed.items()}


def grant_ceo_export(doctypes=None):
	"""The CEO exports every business record they can see (tender data stays out, CR2)."""
	return grant_view(CEO_ROLE, doctypes or ceo_view_doctypes(), ("export",))


# ---------------- new roles' read access, reports, workspaces ----------------
def _has_row(doctype, role):
	return bool(
		frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0})
		or (
			not frappe.db.exists("Custom DocPerm", {"parent": doctype})
			and frappe.db.exists("DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0})
		)
	)


def grant_rights(role, doctypes, rights):
	"""grant_view, except that a new row gets only the rights listed: Frappe's add_permission always ticks Read,
	and a select-only right (e.g. Account for an invoice form) must not open the record itself."""
	changed = []
	for doctype in doctypes:
		if not frappe.db.exists("DocType", doctype):
			continue
		new_row = not _has_row(doctype, role)
		if grant_view(role, [doctype], rights):
			changed.append(doctype)
			if new_row and "read" not in rights:
				set_right(doctype, role, 0, 0, "read", 0)
				frappe.clear_cache(doctype=doctype)
	return changed


def grant_views():
	changed = []
	for role, doctypes, rights in VIEW_GRANTS:
		changed += [f"{d}: {role}" for d in grant_rights(role, doctypes, rights)]
	return changed


def ensure_report_roles():
	"""Add our roles to reports through Custom Role (keeping the report's own roles). Returns the reports changed."""
	changed = []
	for report, roles in REPORT_ROLES.items():
		if not frappe.db.exists("Report", report):
			continue
		name = frappe.db.get_value("Custom Role", {"report": report})
		if name:
			doc = frappe.get_doc("Custom Role", name)
		else:
			own = frappe.get_all("Has Role", filters={"parent": report, "parenttype": "Report"}, pluck="role")
			if not own:
				continue  # a report without roles is open to everyone; a Custom Role would close it
			doc = frappe.new_doc("Custom Role")
			doc.report = report
			doc.ref_doctype = frappe.db.get_value("Report", report, "ref_doctype")
			for role in own:
				doc.append("roles", {"role": role})
		have = {r.role for r in doc.roles}
		missing = [r for r in roles if r not in have and frappe.db.exists("Role", r)]
		if not missing and name:
			continue
		for role in missing:
			doc.append("roles", {"role": role})
		doc.flags.ignore_permissions = True
		doc.save() if name else doc.insert()
		changed.append(report)
	return changed


def ensure_workspace_roles():
	changed = []
	for workspace, roles in WORKSPACE_ROLES.items():
		if not frappe.db.exists("Workspace", workspace):
			continue
		doc = frappe.get_doc("Workspace", workspace)
		have = {r.role for r in doc.roles}
		missing = [r for r in roles if r not in have and frappe.db.exists("Role", r)]
		if not missing:
			continue
		for role in missing:
			doc.append("roles", {"role": role})
		doc.flags.ignore_permissions = True
		doc.save()
		changed.append(workspace)
	return changed


def apply_access_plan():
	"""Everything CR3 sets on a site. Safe to run again; runs on every migrate."""
	return {
		"views": grant_views(),
		"reports": ensure_report_roles(),
		"workspaces": ensure_workspace_roles(),
		"hod_cancel": ensure_hod_cancel(),
		"cancel_removed": restrict_cancel(),
		"rights_removed": restrict_rights(),
		"ceo_export": grant_ceo_export(),
		"export_removed": restrict_export(),
	}


# ---------------- the cancellation summary ----------------
def summary_window(day=None, frequency=None):
	"""(from, to) dates the summary sent on `day` covers, or None when nothing is sent that day."""
	day = getdate(day or today())
	frequency = frequency or params.get("custom_cancellation_summary", "Daily") or "Daily"
	if frequency == "Daily":
		yesterday = add_days(day, -1)
		return yesterday, yesterday
	if frequency == "Weekly" and day.weekday() == 0:  # Monday: the seven days before
		return add_days(day, -7), add_days(day, -1)
	return None


def cancellations(from_date, to_date):
	"""Every record in CANCEL_RULES cancelled between the two dates (inclusive), newest first."""
	start = get_datetime(f"{getdate(from_date)} 00:00:00")
	end = get_datetime(f"{getdate(to_date)} 23:59:59.999999")
	rows = []
	for doctype in CANCEL_RULES:
		if not frappe.db.exists("DocType", doctype):
			continue
		for doc in frappe.get_all(
			doctype,
			filters={"docstatus": 2, "modified": ["between", [start, end]]},
			fields=["name", "modified", "modified_by"],
		):
			rows.append(
				{
					"doctype": doctype,
					"name": doc.name,
					"cancelled_by": doc.modified_by,
					"cancelled_on": doc.modified,
				}
			)
	return sorted(rows, key=lambda r: r["cancelled_on"], reverse=True)


def summary_recipients():
	listed = _lines("custom_cancellation_summary_to")
	if listed:
		return listed
	return sorted(
		set(
			frappe.get_all(
				"Has Role",
				filters={
					"role": CEO_ROLE,
					"parenttype": "User",
					"parent": ["not in", ["Administrator", "Guest"]],
				},
				pluck="parent",
			)
		)
		& set(frappe.get_all("User", filters={"enabled": 1}, pluck="name"))
	)


def summary_html(rows, from_date, to_date):
	period = frappe.format(getdate(from_date), {"fieldtype": "Date"})
	if getdate(from_date) != getdate(to_date):
		period += " to " + frappe.format(getdate(to_date), {"fieldtype": "Date"})
	names = {r["cancelled_by"] for r in rows}
	full = dict(
		frappe.get_all(
			"User", filters={"name": ["in", list(names)]}, fields=["name", "full_name"], as_list=True
		)
	)
	lines = "".join(
		"<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
			_(r["doctype"]),
			frappe.utils.escape_html(r["name"]),
			frappe.utils.escape_html(full.get(r["cancelled_by"]) or r["cancelled_by"]),
			frappe.format(r["cancelled_on"], {"fieldtype": "Datetime"}),
		)
		for r in rows
	)
	return (
		f"<p>{len(rows)} record(s) cancelled in PEPL OS, {period}. Each one stays in the system marked Cancelled; "
		"the Audit Trail shows who did it and why.</p>"
		"<table border='1' cellpadding='4' cellspacing='0'>"
		"<tr><th>Record type</th><th>Record</th><th>Cancelled by</th><th>On</th></tr>"
		f"{lines}</table>"
	)


def send_summary(day=None):
	"""Build and e-mail the summary due on `day`. Returns what was sent (nothing when no record was cancelled)."""
	window = summary_window(day)
	if not window:
		return {"sent_to": [], "rows": 0, "reason": "not due today"}
	rows = cancellations(*window)
	if not rows:
		return {"sent_to": [], "rows": 0, "reason": "nothing cancelled"}
	to = summary_recipients()
	if not to:
		return {"sent_to": [], "rows": len(rows), "reason": "no recipient (PEPL CEO login or Summary To)"}
	period = frappe.format(window[0], {"fieldtype": "Date"})
	try:
		frappe.sendmail(
			recipients=to,
			subject=_("PEPL OS cancellations - {0} ({1})").format(period, len(rows)),
			message=summary_html(rows, *window),
		)
	except frappe.OutgoingEmailError:
		frappe.clear_last_message()
		frappe.log_error(title="PEPL: cancellation summary not e-mailed (no outgoing e-mail account)")
		return {"sent_to": [], "rows": len(rows), "reason": "no outgoing e-mail account"}
	return {"sent_to": to, "rows": len(rows), "reason": ""}


@tracked_job("Cancellation summary")
def daily_cancellation_summary():
	"""Scheduler (daily): the Daily summary every morning, the Weekly one on Mondays."""
	if (params.get("custom_cancellation_summary", "Daily") or "Daily") == "Off":
		return {"records_touched": 0, "message": "switched off"}
	result = send_summary()
	return {
		"records_touched": result["rows"],
		"message": result["reason"] or "sent to " + ", ".join(result["sent_to"]),
	}


# ---------------- for Check 79 ----------------
# (profile, DocType, right, expected) - the pack's decisions as they should read on the site.
EXAMPLES = (
	("PEPL Purchase Manager", "Item", "create", False),  # D1
	("PEPL Item Master", "Item", "create", True),  # D1
	("PEPL Supplier Master", "Supplier", "create", True),  # D2
	("PEPL Stores Manager", "Stock Reconciliation", "submit", True),  # D3
	("PEPL Stores", "Stock Reconciliation", "create", False),  # D3
	("PEPL Stores", "Purchase Receipt", "submit", True),  # D8: Stores posts
	("PEPL Stores", "Purchase Receipt", "cancel", False),  # D4
	("PEPL Stores Manager", "Purchase Receipt", "cancel", True),  # D4
	("PEPL Purchase Manager", "Purchase Order", "cancel", True),  # D4
	("PEPL Foreman", "Work Order", "cancel", False),  # D4
	("PEPL Production Manager", "Work Order", "cancel", True),  # D4
	("PEPL Sales Executive", "Sales Order", "cancel", False),  # D4
	("PEPL Sales Manager", "Sales Order", "cancel", True),  # D4
	("PEPL Foreman", "BOM", "read", True),  # D7
	("PEPL Foreman", "BOM", "create", False),  # D7
	("PEPL Production Manager", "BOM", "create", True),  # D7
	("PEPL Quality Manager", "Purchase Receipt", "read", True),  # D8
	("PEPL Quality Manager", "Purchase Receipt", "create", False),  # D8
	("PEPL Quality Manager", "Stock Entry", "create", False),  # D8
	("PEPL Quality Manager", "Quality Inspection", "cancel", True),
	("PEPL Quality Executive", "Quality Inspection", "submit", True),
	("PEPL Quality Executive", "Quality Inspection", "cancel", False),
	("PEPL Production & Quality Viewer", "Work Order", "read", True),
	("PEPL Production & Quality Viewer", "Work Order", "write", False),
	("PEPL Accountant", "Purchase Invoice", "submit", True),
	("PEPL Accountant", "Purchase Invoice", "cancel", False),  # D4
	("PEPL Accounts", "Purchase Invoice", "cancel", True),  # D4
	("PEPL Accounts", "Sales Invoice", "export", False),  # D9
	("PEPL CEO", "Sales Invoice", "export", True),  # D9
	("PEPL CEO", "Sales Invoice", "write", False),  # D6
	("PEPL Sales Invoicing", "Sales Invoice", "submit", True),  # D11
	("PEPL Sales Invoicing", "Sales Invoice", "cancel", False),  # D4
	("PEPL Sales Manager", "PEPL Tender", "read", False),  # CR2 roles: only Tender Only carries tender roles
)


def example_results():
	from pepl_os.pepl_governance.access_matrix import rights_for

	out = []
	for profile, doctype, ptype, expected in EXAMPLES:
		if not (frappe.db.exists("Role Profile", profile) and frappe.db.exists("DocType", doctype)):
			continue
		got = bool(rights_for(profile, doctype)[ptype])
		out.append({"label": f"{profile} / {doctype} / {ptype}", "expected": expected, "got": got})
	return out


def _reports_missing_roles():
	"""{report: [our roles it does not open for]}."""
	missing = {}
	for report, roles in REPORT_ROLES.items():
		if not frappe.db.exists("Report", report):
			continue
		name = frappe.db.get_value("Custom Role", {"report": report})
		have = (
			set(
				frappe.get_all(
					"Has Role", filters={"parenttype": "Custom Role", "parent": name}, pluck="role"
				)
			)
			if name
			else set()
		)
		lacking = [r for r in roles if r not in have and frappe.db.exists("Role", r)]
		if lacking:
			missing[report] = lacking
	return missing


@frappe.whitelist()
def preview_cancellations(days=7):
	"""System Manager: the records cancelled in the last `days` days (what the summary lists)."""
	frappe.only_for(("System Manager",))
	return cancellations(add_days(today(), -cint(days)), today())


@frappe.whitelist()
def access_plan_status():
	"""What Check 79 reads. Read-only."""
	frappe.only_for(("System Manager",))
	from pepl_os.setup.roles import ROLE_PROFILES

	profiles = {}
	for profile, roles in ROLE_PROFILES.items():
		have = set(
			frappe.get_all(
				"Has Role", filters={"parent": profile, "parenttype": "Role Profile"}, pluck="role"
			)
		)
		profiles[profile] = {
			"exists": bool(frappe.db.exists("Role Profile", profile)),
			"missing": sorted(r for r in roles if r not in have and frappe.db.exists("Role", r)),
			"extra": sorted(have - set(roles)),
		}
	hod_missing = {}
	for doctype, roles in CANCEL_RULES.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		lacking = [
			role
			for role in roles
			if frappe.db.exists("Role", role)
			and not any(r.role == role and r.cancel and not r.permlevel for r in perm_rows(doctype))
		]
		if lacking:
			hod_missing[doctype] = lacking
	return {
		"switches": {
			"cancel_only_by_hod": cancel_rule_on(),
			"bom_by_production_manager_only": bom_rule_on(),
			"restrict_export_to_ceo": export_rule_on(),
			"summary": params.get("custom_cancellation_summary", "Daily") or "Daily",
		},
		"profiles": profiles,
		"cancel_offenders": {
			d: cancel_offenders(d)
			for d in CANCEL_RULES
			if frappe.db.exists("DocType", d) and cancel_offenders(d)
		},
		"hod_cannot_cancel": hod_missing,
		"right_offenders": {f"{d} / {r}": v for (d, r), v in removal_offenders().items()},
		"export_offenders": export_offenders(),
		"ceo_export_missing": [
			d
			for d in ceo_view_doctypes()
			if not any(r.role == CEO_ROLE and r.export and not r.permlevel for r in perm_rows(d))
		],
		"reports_missing_roles": _reports_missing_roles(),
		"examples": example_results(),
		"summary_recipients": summary_recipients(),
		"scheduled": "pepl_os.pepl_governance.access_plan.daily_cancellation_summary"
		in (frappe.get_hooks("scheduler_events").get("daily") or []),
	}
