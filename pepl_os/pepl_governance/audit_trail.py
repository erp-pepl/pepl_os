"""A4 - Consolidated Audit Trail: one row per event, from six sources.

Sources (all written by Frappe or pepl_os, nothing new is logged here):
  Version            field changes (old -> new), submit / cancel as docstatus
  Activity Log       logins, logouts, impersonation
  Access Log         prints, exports, downloads
  Deleted Document   deletions
  View Log           record views (DocTypes with track_views)
  PEPL Override Log  every override with its reason
"""

import json

import frappe
from frappe.utils import add_days, get_datetime, getdate

EVENT_FIELD_CHANGE = "Field Change"
EVENT_LOGIN = "Login / Logout"
EVENT_PRINT_EXPORT = "Print / Export"
EVENT_DELETION = "Deletion"
EVENT_VIEW = "View"
EVENT_OVERRIDE = "Override"

EVENT_TYPES = (
	EVENT_FIELD_CHANGE,
	EVENT_LOGIN,
	EVENT_PRINT_EXPORT,
	EVENT_DELETION,
	EVENT_VIEW,
	EVENT_OVERRIDE,
)

ROW_LIMIT_PER_SOURCE = 5000
DOCSTATUS_WORDS = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


def _short(value, limit=140):
	text = "" if value is None else str(value)
	return text if len(text) <= limit else text[: limit - 1] + "…"


def version_details(data):
	"""Turn a Version's JSON into a list of 'field: old → new' strings."""
	try:
		diff = json.loads(data or "{}")
	except (TypeError, ValueError):
		return []

	lines = []
	for field, old, new in diff.get("changed") or []:
		if field == "docstatus":
			lines.append(f"Status: {DOCSTATUS_WORDS.get(old, old)} → {DOCSTATUS_WORDS.get(new, new)}")
		else:
			lines.append(f"{field}: {_short(old)} → {_short(new)}")
	for entry in diff.get("row_changed") or []:
		# [table_field, row_name, row_index, [[field, old, new], ...]]
		table, idx, changes = entry[0], entry[2] if len(entry) > 2 else "", entry[-1] or []
		for field, old, new in changes:
			lines.append(f"{table} row {idx} · {field}: {_short(old)} → {_short(new)}")
	for table, _row in diff.get("added") or []:
		lines.append(f"{table}: row added")
	for table, _row in diff.get("removed") or []:
		lines.append(f"{table}: row removed")
	return lines


def _window(filters):
	from_date = getdate(filters.get("from_date"))
	to_date = getdate(filters.get("to_date"))
	# inclusive to_date: everything before the next day
	return get_datetime(from_date), get_datetime(add_days(to_date, 1))


def _where(filters, time_field, user_field, doctype_field=None, name_field=None):
	start, end = _window(filters)
	where = {time_field: ["between", [start, end]]}
	if filters.get("user"):
		where[user_field] = filters["user"]
	if doctype_field and filters.get("reference_doctype"):
		where[doctype_field] = filters["reference_doctype"]
	if name_field and filters.get("reference_name"):
		where[name_field] = filters["reference_name"]
	return where


def _fetch(doctype, where, fields, time_field):
	return frappe.get_all(
		doctype,
		filters=where,
		fields=fields,
		order_by=f"{time_field} desc",
		limit=ROW_LIMIT_PER_SOURCE,
	)


def _versions(filters):
	rows = []
	for v in _fetch(
		"Version",
		_where(filters, "creation", "owner", "ref_doctype", "docname"),
		["creation", "owner", "ref_doctype", "docname", "data"],
		"creation",
	):
		for detail in version_details(v.data) or ["Changed"]:
			rows.append(
				{
					"time": v.creation,
					"user": v.owner,
					"event_type": EVENT_FIELD_CHANGE,
					"reference_doctype": v.ref_doctype,
					"reference_name": v.docname,
					"detail": detail,
				}
			)
	return rows


def _logins(filters):
	where = _where(filters, "creation", "user", "reference_doctype", "reference_name")
	where["operation"] = ["in", ["Login", "Logout", "Impersonate"]]
	return [
		{
			"time": a.creation,
			"user": a.user,
			"event_type": EVENT_LOGIN,
			"reference_doctype": None,
			"reference_name": None,
			"detail": f"{a.operation} {a.status or ''} from {a.ip_address or 'unknown IP'}".strip(),
		}
		for a in _fetch(
			"Activity Log",
			where,
			["creation", "user", "operation", "status", "ip_address"],
			"creation",
		)
	]


def _access(filters):
	rows = []
	is_doctype = {}
	for a in _fetch(
		"Access Log",
		_where(filters, "creation", "user", "export_from", "reference_document"),
		["creation", "user", "export_from", "reference_document", "file_type", "report_name", "method"],
		"creation",
	):
		what = a.file_type or a.method or "Access"
		target = a.report_name or a.reference_document or ""
		rows.append(
			{
				"time": a.creation,
				"user": a.user,
				"event_type": EVENT_PRINT_EXPORT,
				"reference_doctype": a.export_from
				if is_doctype.setdefault(
					a.export_from, bool(frappe.db.exists("DocType", a.export_from or ""))
				)
				else None,
				"reference_name": a.reference_document,
				"detail": f"{what} {a.export_from or ''} {target}".strip(),
			}
		)
	return rows


def _deletions(filters):
	return [
		{
			"time": d.creation,
			"user": d.owner,
			"event_type": EVENT_DELETION,
			"reference_doctype": d.deleted_doctype,
			"reference_name": d.deleted_name,
			"detail": f"Deleted {d.deleted_doctype} {d.deleted_name}" + (" (restored)" if d.restored else ""),
		}
		for d in _fetch(
			"Deleted Document",
			_where(filters, "creation", "owner", "deleted_doctype", "deleted_name"),
			["creation", "owner", "deleted_doctype", "deleted_name", "restored"],
			"creation",
		)
	]


def _views(filters):
	return [
		{
			"time": v.creation,
			"user": v.viewed_by,
			"event_type": EVENT_VIEW,
			"reference_doctype": v.reference_doctype,
			"reference_name": v.reference_name,
			"detail": "Opened",
		}
		for v in _fetch(
			"View Log",
			_where(filters, "creation", "viewed_by", "reference_doctype", "reference_name"),
			["creation", "viewed_by", "reference_doctype", "reference_name"],
			"creation",
		)
	]


def _overrides(filters):
	return [
		{
			"time": o.creation,
			"user": o.user,
			"event_type": EVENT_OVERRIDE,
			"reference_doctype": o.reference_doctype,
			"reference_name": o.reference_name,
			"detail": f"{o.rule_code}: {_short(o.reason, 300)}",
		}
		for o in _fetch(
			"PEPL Override Log",
			_where(filters, "creation", "user", "reference_doctype", "reference_name"),
			["creation", "user", "rule_code", "reason", "reference_doctype", "reference_name"],
			"creation",
		)
	]


SOURCES = {
	EVENT_FIELD_CHANGE: _versions,
	EVENT_LOGIN: _logins,
	EVENT_PRINT_EXPORT: _access,
	EVENT_DELETION: _deletions,
	EVENT_VIEW: _views,
	EVENT_OVERRIDE: _overrides,
}


def get_events(filters):
	"""All events in the window, newest first. Returns (rows, truncated_sources)."""
	filters = frappe._dict(filters or {})
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw("From Date and To Date are required.")

	wanted = [filters.event_type] if filters.get("event_type") else list(EVENT_TYPES)
	rows, truncated = [], []
	for event_type in wanted:
		found = SOURCES[event_type](filters)
		if len(found) >= ROW_LIMIT_PER_SOURCE:
			truncated.append(event_type)
		rows.extend(found)

	rows.sort(key=lambda r: get_datetime(r["time"]), reverse=True)
	return rows, truncated
