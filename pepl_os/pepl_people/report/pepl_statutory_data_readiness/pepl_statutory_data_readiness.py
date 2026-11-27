# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C4-H5 - Statutory Data Readiness: per Employee, the PF / ESIC / PAN / Aadhaar / bank details on file and what is
still missing. HR Manager and System Manager only (the same people who see permission level 6)."""

import frappe
from frappe import _

from pepl_os.pepl_people import statutory


def execute(filters=None):
	filters = frappe._dict(filters or {})
	frappe.only_for(statutory.LEVEL_ROLES)
	columns = [
		{
			"fieldname": "name",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "employee_number", "label": _("Employee Number"), "fieldtype": "Data", "width": 110},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Data", "width": 120},
		{"fieldname": "custom_pf_applicable", "label": _("PF"), "fieldtype": "Check", "width": 50},
		{"fieldname": "custom_uan", "label": _("UAN"), "fieldtype": "Data", "width": 120},
		{"fieldname": "custom_esic_applicable", "label": _("ESIC"), "fieldtype": "Check", "width": 60},
		{"fieldname": "custom_esic_ip_number", "label": _("ESIC IP"), "fieldtype": "Data", "width": 110},
		{"fieldname": "pan_number", "label": _("PAN"), "fieldtype": "Data", "width": 110},
		{"fieldname": "custom_aadhaar_masked", "label": _("Aadhaar"), "fieldtype": "Data", "width": 130},
		{"fieldname": "missing", "label": _("Still Missing"), "fieldtype": "Data", "width": 300},
	]
	rows = statutory.readiness_rows(filters.get("status") or "Active")
	if filters.get("only_missing"):
		rows = [r for r in rows if r.get("missing")]
	complete = len([r for r in rows if not r.get("missing")])
	return columns, rows, _("{0} of {1} complete").format(complete, len(rows))
