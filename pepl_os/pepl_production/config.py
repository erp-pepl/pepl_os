"""C3a-C1 - Production configuration: the settings PEPL confirms, OEE thresholds per factor, standard-time governance
and the downtime category master cleanup.

- Settings review: every Production setting (System Parameters → Production, the pepl_sales production
  parameters, the Manufacturing Settings PEPL OS relies on) with its value, its default and whether it was changed
  - report "PEPL Production Settings", the sheet signed off with the Production HOD.
- OEE thresholds: besides the OEE Target, a target for each factor (Availability, Performance, Quality); the
  Daily OEE names the factors below target, so the stand-up and the Command Centre say *why* a day was poor.
- Standard-time governance: look-back days, minimum runs, median / average, largest change per approval and the
  approving role, read by the learning-standards workflow (Work Package E2). The band a run may differ from its
  standard is the pepl_sales "Cycle Deviation Threshold Low / High", also used by the shift entry aids (C3a-P5).
- Downtime categories: how often each is used, which look like the same stop under another name, which are
  unused; "Merge into" moves every shift-entry row of one category to another of the same kind (stop type and
  breakdown flag), switches the old one off and rebuilds the Daily OEE and Machine Weeks it touched.
"""

import re

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate, today

from pepl_os.common import params

AVAILABILITY_FIELD = "custom_oee_availability_target_percent"
PERFORMANCE_FIELD = "custom_oee_performance_target_percent"
QUALITY_FIELD = "custom_oee_quality_target_percent"
FACTOR_FIELDS = (
	("Availability", AVAILABILITY_FIELD, 90),
	("Performance", PERFORMANCE_FIELD, 95),
	("Quality", QUALITY_FIELD, 99),
)

LOOKBACK_FIELD = "custom_std_time_lookback_days"
MIN_RUNS_FIELD = "custom_std_time_min_runs"
BASIS_FIELD = "custom_std_time_basis"
MAX_CHANGE_FIELD = "custom_std_time_max_change_percent"
APPROVER_FIELD = "custom_std_time_approver_role"
BASES = ("Median", "Average")
DEFAULT_APPROVER = "PEPL Production Manager"
LOOKBACK_RANGE = (7, 365)

CATEGORY = "PEPL Downtime Category"
SPR = "PEPL Shift Production Entry"
DOWNTIME_ROW = "PEPL SPR Downtime"
MERGE_ROLES = ("System Manager", "Manufacturing Manager", "PEPL Production Manager")
REVIEW_DAYS = 90


# Validation ---------------------------------------------------------------------------------------------


def validate_c1_params(doc):
	"""Errors for the C1 settings in a PEPL System Parameters document (called from params.py)."""
	errors = []
	for label, field, _default in FACTOR_FIELDS:
		value = doc.get(field)
		if value not in (None, "") and not 0 < flt(value) <= 100:
			errors.append(_("OEE: {0} Target % must be more than 0 and at most 100.").format(_(label)))
	low, high = LOOKBACK_RANGE
	days = doc.get(LOOKBACK_FIELD)
	if days not in (None, "") and not low <= cint(days) <= high:
		errors.append(_("Standard Time: Look-back Days must be between {0} and {1}.").format(low, high))
	runs = doc.get(MIN_RUNS_FIELD)
	if runs not in (None, "") and cint(runs) < 1:
		errors.append(_("Standard Time: Minimum Runs Before a Suggestion must be at least 1."))
	basis = doc.get(BASIS_FIELD)
	if basis not in (None, "") and basis not in BASES:
		errors.append(_("Standard Time: Suggest From must be Median or Average."))
	change = doc.get(MAX_CHANGE_FIELD)
	if change not in (None, "") and not 0 < flt(change) <= 100:
		errors.append(_("Standard Time: Largest Change per Approval % must be more than 0 and at most 100."))
	return errors


# OEE factor targets -------------------------------------------------------------------------------------


def factor_targets():
	"""{factor: target %} for Availability, Performance and Quality."""
	result = {}
	for label, field, default in FACTOR_FIELDS:
		value = params.get(field, default)
		result[label] = flt(value) if value not in (None, "") else default
	return result


def factors_below(availability, performance, quality):
	"""'Availability 70 % (target 90 %), Quality 95 % (target 99 %)' - the factors of a day below their target."""
	actual = {"Availability": availability, "Performance": performance, "Quality": quality}
	parts = []
	for label, aim in factor_targets().items():
		if flt(actual[label]) < aim - 1e-9:
			parts.append(_("{0} {1} % (target {2} %)").format(_(label), _num(actual[label]), _num(aim)))
	return ", ".join(parts)


def _num(value):
	value = round(flt(value), 2)
	return str(int(value)) if value == int(value) else f"{value:.2f}".rstrip("0").rstrip(".")


# Standard-time governance -------------------------------------------------------------------------------


def std_time_settings():
	"""The governance settings the learning-standards workflow (E2) works within."""
	low, high = LOOKBACK_RANGE
	basis = params.get(BASIS_FIELD, "Median")
	return frappe._dict(
		lookback_days=min(max(cint(params.get(LOOKBACK_FIELD, 90)) or 90, low), high),
		min_runs=max(cint(params.get(MIN_RUNS_FIELD, 5)) or 5, 1),
		basis=basis if basis in BASES else "Median",
		max_change_percent=flt(params.get(MAX_CHANGE_FIELD, 20)) or 20,
		approver_role=params.get(APPROVER_FIELD) or DEFAULT_APPROVER,
		band_low=flt(params.get("cycle_deviation_threshold_low", 0.8)) or 0.8,
		band_high=flt(params.get("cycle_deviation_threshold_high", 1.2)) or 1.2,
	)


# Settings review ----------------------------------------------------------------------------------------

PEPL_SALES_FIELDS = (
	"skill_check_mode",
	"oee_planned_time_excludes_pm",
	"cycle_deviation_threshold_low",
	"cycle_deviation_threshold_high",
	"dn_material_gate_mode",
	"csm_reconciliation_tolerance_kg",
	"standup_email_group",
)
MANUFACTURING_FIELDS = (
	(
		"disable_capacity_planning",
		"1",
		"Capacity planning off: the double-booking check (X6) and the load view (P2) plan the machines",
	),
	("mins_between_operations", "0", "Minutes between operations used when laying out Job Orders (X6, P2)"),
	(
		"overproduction_percentage_for_work_order",
		"0",
		"How much more than a Job Card's quantity a shift entry may report",
	),
)
NO_VALUE = ("Section Break", "Column Break", "Tab Break", "Table", "HTML")


def _same(value, default, fieldtype):
	if default in (None, ""):
		return value in (None, "")
	if fieldtype in ("Check", "Int", "Float", "Percent", "Currency"):
		return abs(flt(value) - flt(default)) < 1e-9
	return str(value or "") == str(default)


def _shown(value, fieldtype):
	if value in (None, ""):
		return "-"
	if fieldtype == "Check":
		return _("Yes") if cint(value) else _("No")
	if fieldtype in ("Int", "Float", "Percent"):
		return _num(value)
	return str(value)


def settings_rows():
	"""One row per Production setting: area, setting, value, default, status, what it does."""
	from pepl_os.setup.custom_fields import PRODUCTION_FIELDS

	rows = []
	section = _("Production")
	stored = frappe.get_doc("PEPL System Parameters")
	for f in PRODUCTION_FIELDS:
		if f["fieldtype"] in ("Section Break", "Tab Break"):
			section = f.get("label") or section
			continue
		if f["fieldtype"] in NO_VALUE:
			continue
		value = stored.get(f["fieldname"])
		default = f.get("default")
		rows.append(
			frappe._dict(
				area=section,
				setting=f.get("label"),
				fieldname=f["fieldname"],
				value=_shown(value, f["fieldtype"]),
				default=_shown(default, f["fieldtype"]) if default not in (None, "") else "-",
				status=_("Default, to confirm with PEPL")
				if _same(value, default, f["fieldtype"])
				else _("Changed from default"),
				description=f.get("description") or "",
			)
		)
	meta = frappe.get_meta("PEPL System Parameters")
	for fieldname in PEPL_SALES_FIELDS:
		f = meta.get_field(fieldname)
		if not f:
			continue
		value = stored.get(fieldname)
		rows.append(
			frappe._dict(
				area=_("Production (first tab)"),
				setting=f.label,
				fieldname=fieldname,
				value=_shown(value, f.fieldtype),
				default=_shown(f.default, f.fieldtype) if f.default not in (None, "") else "-",
				status=_("Default, to confirm with PEPL")
				if _same(value, f.default, f.fieldtype)
				else _("Changed from default"),
				description=f.description or "",
			)
		)
	for fieldname, default, description in MANUFACTURING_FIELDS:
		value = frappe.db.get_single_value("Manufacturing Settings", fieldname)
		f = frappe.get_meta("Manufacturing Settings").get_field(fieldname)
		rows.append(
			frappe._dict(
				area=_("Manufacturing Settings"),
				setting=f.label if f else fieldname,
				fieldname=fieldname,
				value=_shown(value, f.fieldtype if f else "Data"),
				default=_shown(default, f.fieldtype if f else "Data"),
				status=_("As PEPL OS expects")
				if _same(value, default, f.fieldtype if f else "Data")
				else _("Different: confirm with PEPL"),
				description=_(description),
			)
		)
	active = frappe.db.count(CATEGORY, {"is_active": 1})
	rows.append(
		frappe._dict(
			area=_("Downtime categories"),
			setting=_("Active downtime categories"),
			fieldname="",
			value=str(active),
			default="16",
			status=_("Review with the Production HOD (PEPL Downtime Category Review)"),
			description=_(
				"The stops operators choose from; the review lists unused and look-alike categories."
			),
		)
	)
	return rows


# Downtime category cleanup ------------------------------------------------------------------------------


def _key(name):
	"""A category name reduced to letters and digits, so 'No-Load', 'No load' and 'no  load' match."""
	return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def category_usage(days=REVIEW_DAYS):
	"""{category: {recent, total, last_used}} from the shift entries (draft and submitted)."""
	since = add_days(today(), -cint(days))
	usage = {}
	for r in frappe.db.sql(
		f"""select d.downtime_category as category, count(*) as total,
			sum(case when s.posting_date >= %(since)s then 1 else 0 end) as recent,
			max(s.posting_date) as last_used
		from `tab{DOWNTIME_ROW}` d join `tab{SPR}` s on s.name = d.parent
		where s.docstatus < 2 group by d.downtime_category""",
		{"since": since},
		as_dict=True,
	):
		usage[r.category] = frappe._dict(total=cint(r.total), recent=cint(r.recent), last_used=r.last_used)
	return usage


def review_rows(days=REVIEW_DAYS):
	"""One row per downtime category with how it is used and what to look at."""
	days = max(cint(days) or REVIEW_DAYS, 1)
	usage = category_usage(days)
	categories = frappe.get_all(
		CATEGORY, fields=["name", "stop_type", "is_breakdown", "is_active"], order_by="name"
	)
	by_key = {}
	for c in categories:
		by_key.setdefault(_key(c.name), []).append(c.name)
	rows = []
	for c in categories:
		u = usage.get(c.name) or frappe._dict(total=0, recent=0, last_used=None)
		notes = []
		twins = [n for n in by_key.get(_key(c.name), []) if n != c.name]
		if twins:
			notes.append(
				_("Looks like the same stop as {0}: merge one into the other").format(", ".join(twins))
			)
		if cint(c.is_active) and not u.total:
			notes.append(_("Never used: switch it off if PEPL does not need it"))
		elif cint(c.is_active) and not u.recent:
			notes.append(_("Not used in the last {0} days").format(days))
		if not cint(c.is_active) and u.recent:
			notes.append(_("Inactive, but used in the last {0} days").format(days))
		rows.append(
			frappe._dict(
				category=c.name,
				stop_type=c.stop_type,
				is_breakdown=cint(c.is_breakdown),
				is_active=cint(c.is_active),
				recent=u.recent,
				total=u.total,
				last_used=u.last_used,
				notes="; ".join(notes),
			)
		)
	return rows


@frappe.whitelist()
def get_downtime_category_review(name):
	"""For the Downtime Category form: how it is used and what to look at."""
	frappe.has_permission(CATEGORY, "read", doc=name, throw=True)
	row = next((r for r in review_rows() if r.category == name), None)
	if not row:
		return {"rows": []}
	used = (
		_("Used {0} time(s) in the last {1} days, {2} in all; last on {3}").format(
			row.recent, REVIEW_DAYS, row.total, frappe.utils.formatdate(row.last_used)
		)
		if row.total
		else _("Never used on a shift entry")
	)
	rows = [{"text": used, "colour": "green" if row.recent else "gray"}]
	if row.notes:
		rows.append({"text": row.notes, "colour": "orange"})
	return {"rows": rows, "can_merge": bool(set(MERGE_ROLES) & set(frappe.get_roles()))}


@frappe.whitelist()
def merge_downtime_category(source, target):
	"""Move every shift-entry row of `source` to `target` (same kind of stop), switch `source` off, rebuild the
	Daily OEE and Machine Weeks of the shifts it touched. Production Manager only."""
	frappe.only_for(MERGE_ROLES)
	if not source or not target or source == target:
		frappe.throw(_("Choose another category to merge into."))
	a = frappe.db.get_value(CATEGORY, source, ["name", "stop_type", "is_breakdown"], as_dict=True)
	b = frappe.db.get_value(
		CATEGORY, target, ["name", "stop_type", "is_breakdown", "is_active"], as_dict=True
	)
	if not a or not b:
		frappe.throw(_("Both categories must exist."))
	if a.stop_type != b.stop_type or cint(a.is_breakdown) != cint(b.is_breakdown):
		frappe.throw(
			_(
				"{0} is {1}{2}; {3} is {4}{5}. Only categories of the same kind can be merged: merging would change "
				"the OEE and MTBF / MTTR of past shifts."
			).format(
				source,
				_(a.stop_type),
				", " + _("Machine Breakdown") if cint(a.is_breakdown) else "",
				target,
				_(b.stop_type),
				", " + _("Machine Breakdown") if cint(b.is_breakdown) else "",
			),
			title=_("Different kind of stop"),
		)
	if not cint(b.is_active):
		frappe.throw(
			_("{0} is inactive: switch it on first, or merge into an active category.").format(target)
		)
	touched = frappe.db.sql(
		f"""select distinct s.workstation, s.posting_date, s.docstatus
		from `tab{DOWNTIME_ROW}` d join `tab{SPR}` s on s.name = d.parent
		where d.downtime_category = %s and s.docstatus < 2""",
		source,
		as_dict=True,
	)
	moved = frappe.db.sql(
		f"""select count(*) from `tab{DOWNTIME_ROW}` where downtime_category = %s""", source
	)[0][0]
	frappe.db.sql(
		f"""update `tab{DOWNTIME_ROW}` set downtime_category = %s where downtime_category = %s""",
		(target, source),
	)
	note = _("Merged into {0} on {1} by {2}; {3} shift-entry row(s) moved.").format(
		target, frappe.utils.formatdate(nowdate()), frappe.session.user, cint(moved)
	)
	old = frappe.get_doc(CATEGORY, source)
	old.is_active = 0
	old.description = ((old.description or "") + "\n" + note).strip()
	old.flags.ignore_permissions = True
	old.save()

	from pepl_os.pepl_production import machine_week, oee

	rebuilt = set()
	for t in touched:
		if t.docstatus != 1 or (t.workstation, getdate(t.posting_date)) in rebuilt:
			continue
		rebuilt.add((t.workstation, getdate(t.posting_date)))
		oee.build_day(t.workstation, t.posting_date)
		machine_week.build_week(t.workstation, t.posting_date)
	return {"moved": cint(moved), "rebuilt_days": len(rebuilt), "message": note}
