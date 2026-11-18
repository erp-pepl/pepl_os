"""C3b-C1 - Quality configuration: the Quality Settings sheet confirmed with PEPL's Quality Manager.

Report "PEPL Quality Settings", one row per thing to confirm:
  * every setting on System Parameters → Quality (incoming QC, calibration alert window and gate, the NCR severity
    sign-off matrix and auto-raise rules with the rejection-rate threshold, CAPA, dispatch gate, vendor score weights)
    with its value, its default and whether it was changed ("Default, to confirm with PEPL" / "Changed from default");
  * the Quality Notification Owner and the Vendor Score Period it relies on;
  * the sign-off matrix in practice: for every role in it, the users who hold it - a role nobody holds means NCRs of
    that severity can never be closed;
  * ERPNext Stock Settings for QC (Warn, so PEPL's gates decide);
  * the master data the rules work on: items inspected on receipt / before delivery and how many have no inspection
    plan; instruments in use and how many are overdue or never calibrated.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from pepl_os.common import params
from pepl_os.pepl_quality import calibration, dispatch, incoming_qc, ncr

DEFAULT_STATUS = "Default, to confirm with PEPL"
CHANGED_STATUS = "Changed from default"
NO_VALUE = ("Section Break", "Column Break", "Tab Break", "Table", "HTML")
SCORE_PERIOD_FIELD = "custom_vendor_score_lookback_days"
NOT_A_PERSON = ("Administrator", "Guest")


def _num(value):
	value = round(flt(value), 2)
	return str(int(value)) if value == int(value) else f"{value:.2f}".rstrip("0").rstrip(".")


def _shown(value, fieldtype):
	if value in (None, ""):
		return "-"
	if fieldtype == "Check":
		return _("Yes") if cint(value) else _("No")
	if fieldtype in ("Int", "Float", "Percent"):
		return _num(value)
	if fieldtype == "Small Text":
		return ", ".join(p.strip() for p in cstr(value).replace(",", "\n").splitlines() if p.strip()) or "-"
	return str(value)


def _same(value, default, fieldtype):
	if default in (None, ""):
		return value in (None, "")
	if fieldtype in ("Check", "Int", "Float", "Percent"):
		return value not in (None, "") and abs(flt(value) - flt(default)) < 1e-9
	if fieldtype == "Small Text":
		return _shown(value, fieldtype) == _shown(default, fieldtype)
	return cstr(value) == cstr(default)


def quality_fields():
	from pepl_os.setup.custom_fields import (
		CALIBRATION_FIELDS,
		CAPA_FIELDS,
		DISPATCH_FIELDS,
		NCR_FIELDS,
		QUALITY_FIELDS,
		VENDOR_SCORE_FIELDS,
	)

	return [
		*QUALITY_FIELDS,
		*CALIBRATION_FIELDS,
		*NCR_FIELDS,
		*CAPA_FIELDS,
		*DISPATCH_FIELDS,
		*VENDOR_SCORE_FIELDS,
	]


def _row(area, setting, fieldname, value, default, status, description=""):
	return frappe._dict(
		area=area,
		setting=setting,
		fieldname=fieldname,
		value=value,
		default=default,
		status=status,
		description=description,
	)


def parameter_rows():
	"""Every setting on the Quality tab with its value, default and status."""
	stored = frappe.get_doc(params.SYSTEM_PARAMETERS)
	rows = []
	area = _("Quality")
	for f in quality_fields():
		if f["fieldtype"] in ("Section Break", "Tab Break"):
			area = _(f.get("label") or area)
			continue
		if f["fieldtype"] in NO_VALUE:
			continue
		value, default = stored.get(f["fieldname"]), f.get("default")
		if f["fieldname"] == incoming_qc.CLASSES_FIELD and not cstr(value).strip():
			status = _("Empty: to set with PEPL (which stock classes are inspected on receipt)")
		elif _same(value, default, f["fieldtype"]):
			status = _(DEFAULT_STATUS)
		else:
			status = _(CHANGED_STATUS)
		rows.append(
			_row(
				area,
				_(f.get("label")),
				f["fieldname"],
				_shown(value, f["fieldtype"]),
				_shown(default, f["fieldtype"]),
				status,
				_(f.get("description") or ""),
			)
		)
	return rows


def owner_rows():
	owner = params.get(ncr.OWNER_FIELD)
	fallback = params.get("notification_fallback_owner")
	if owner:
		status = _("Set")
	elif fallback:
		status = _("Not set: Quality ToDos go to the Notification Fallback Owner ({0})").format(fallback)
	else:
		status = _("Not set: Quality ToDos are not raised. Set it with PEPL")
	period = params.get_int(SCORE_PERIOD_FIELD, 365) or 365
	return [
		_row(
			_("Owners"),
			_("Quality Notification Owner"),
			ncr.OWNER_FIELD,
			owner or "-",
			"-",
			status,
			_(
				"Gets the Quality ToDos: calibration due, NCRs and CAPAs raised by the system, missing inspection plans."
			),
		),
		_row(
			_("Vendor Scorecard"),
			_("Vendor Score Period (Days)"),
			SCORE_PERIOD_FIELD,
			str(period),
			"365",
			_(DEFAULT_STATUS) if period == 365 else _(CHANGED_STATUS),
			_(
				"The quality score counts incoming inspections of the last this many days (shared with the delivery score)."
			),
		),
	]


def role_holders(role):
	"""Enabled system users (not Administrator) who hold the role."""
	return frappe.db.sql_list(
		"""
		select distinct u.name from `tabHas Role` r join `tabUser` u on u.name = r.parent
		where r.parenttype = 'User' and r.role = %s and u.enabled = 1 and u.user_type = 'System User'
			and u.name not in %s
		order by u.name
		""",
		(role, NOT_A_PERSON),
	)


def unheld_roles(doc=None):
	"""{role: [severities]} of the sign-off matrix (from `doc`, else the saved parameters) that no user holds."""
	signs = {}
	for severity in ncr.SEVERITIES:
		value = doc.get(ncr.SIGNOFF_FIELDS[severity]) if doc is not None else None
		roles = ncr.roles_in(value) if value not in (None, "") else ncr.required_roles(severity)
		for role in roles:
			signs.setdefault(role, []).append(severity)
	return {
		role: severities
		for role, severities in signs.items()
		if frappe.db.exists("Role", role) and not role_holders(role)
	}


def warn_unheld_roles(doc):
	"""On saving a change to the sign-off matrix: say which of its roles nobody holds (a warning; the save goes on)."""
	before = doc.get_doc_before_save() if not doc.is_new() else None
	fields = ncr.SIGNOFF_FIELDS.values()
	if before is not None and all(cstr(before.get(f)) == cstr(doc.get(f)) for f in fields):
		return
	for role, severities in unheld_roles(doc).items():
		frappe.msgprint(
			_(
				"NCR sign-off: no user holds the role {0} yet, so {1} NCRs cannot be closed until someone does."
			).format(role, " / ".join(_(s) for s in severities)),
			title=_("Quality settings"),
			indicator="orange",
		)


def signoff_rows():
	"""For every role of the sign-off matrix: the severities it signs and who holds it."""
	signs = {}
	for severity in ncr.SEVERITIES:
		for role in ncr.required_roles(severity):
			signs.setdefault(role, []).append(severity)
	rows = []
	for role, severities in signs.items():
		users = role_holders(role) if frappe.db.exists("Role", role) else []
		if users:
			shown = ", ".join(users[:5]) + (
				_(" and {0} more").format(len(users) - 5) if len(users) > 5 else ""
			)
			value, status = _("{0} user(s): {1}").format(len(users), shown), _("Ready")
		else:
			value = _("nobody")
			status = _("No user holds this role: {0} NCRs can never be closed").format(
				" / ".join(_(s) for s in severities)
			)
		rows.append(
			_row(
				_("Sign-off matrix in practice"),
				_("{0} signs {1} NCRs").format(role, ", ".join(_(s) for s in severities)),
				"",
				value,
				"-",
				status,
				_("Users who can press 'Sign off' for this role (Administrator not counted)."),
			)
		)
	return rows


def stock_settings_rows():
	meta = frappe.get_meta("Stock Settings")
	rows = []
	for field in incoming_qc.STOCK_SETTINGS_ACTIONS:
		value = frappe.db.get_single_value("Stock Settings", field)
		f = meta.get_field(field)
		rows.append(
			_row(
				_("Stock Settings"),
				_(f.label) if f else field,
				field,
				value or "-",
				"Warn",
				_("As PEPL OS expects")
				if value == "Warn"
				else _("Different: ERPNext stops before PEPL's gate asks"),
				_(
					"Warn lets the Incoming QC and Dispatch gates decide (Advisory / Soft Block / Hard Block)."
				),
			)
		)
	return rows


def _inspected_items(flag):
	return frappe.get_all(
		"Item",
		filters={flag: 1, "disabled": 0},
		fields=["name", "quality_inspection_template"],
	)


def master_rows():
	rows = []
	for label, flag, what in (
		(
			_("Items inspected on receipt"),
			incoming_qc.FLAG,
			_("a QC Inspection is made with every receipt line"),
		),
		(_("Items inspected before delivery"), dispatch.FLAG, _("a final inspection is needed at dispatch")),
	):
		items = _inspected_items(flag)
		bare = [i.name for i in items if not i.quality_inspection_template]
		if not items:
			status = _("None yet: to set with PEPL")
		elif bare:
			status = _("{0} without an inspection plan: {1}").format(
				len(bare), ", ".join(bare[:5]) + (" …" if len(bare) > 5 else "")
			)
		else:
			status = _("Ready: every one has an inspection plan")
		rows.append(
			_row(
				_("Master data"),
				label,
				flag,
				str(len(items)),
				"-",
				status,
				_("Ticked items: {0}.").format(what),
			)
		)
	instruments = frappe.get_all(
		calibration.INSTRUMENT,
		filters={"status": ["!=", calibration.SCRAPPED]},
		fields=["name", "status", "calibration_due_on"],
	)
	not_fit = [
		i.name
		for i in instruments
		if calibration.state_of(i.status, i.calibration_due_on)[0] in (calibration.OVERDUE, calibration.NEVER)
	]
	if not instruments:
		status = _("None yet: enter PEPL's instrument list")
	elif not_fit:
		status = _("{0} overdue or never calibrated: {1}").format(
			len(not_fit), ", ".join(not_fit[:5]) + (" …" if len(not_fit) > 5 else "")
		)
	else:
		status = _("Ready: all calibrated")
	rows.append(
		_row(
			_("Master data"),
			_("Instruments (not scrapped)"),
			"",
			str(len(instruments)),
			"-",
			status,
			_("Gauges and instruments with their calibration records (PEPL Instrument)."),
		)
	)
	return rows


RED_STARTS = ("No user holds", "Different", "Not set: Quality ToDos are not raised")
GREEN_STARTS = (CHANGED_STATUS, "Set", "Ready", "As PEPL OS expects")


def colour_of(status):
	"""green = done or already decided; orange = to confirm or to complete with PEPL; red = will not work as it is."""
	status = cstr(status)
	if status.startswith(tuple(_(s) for s in RED_STARTS)):
		return "red"
	if status.startswith(tuple(_(s) for s in GREEN_STARTS)):
		return "green"
	return "orange"


def settings_rows():
	"""The whole Quality Settings sheet; each row carries its colour."""
	rows = parameter_rows() + owner_rows() + signoff_rows() + stock_settings_rows() + master_rows()
	for row in rows:
		row.colour = colour_of(row.status)
	return rows
