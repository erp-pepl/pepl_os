# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C4-H1 - People Register: every Employee (Login User or Shop Floor), its login and operator, plus operators and
desk logins without an Employee - with what is missing or wrong. See pepl_people/people.py."""

import frappe
from frappe import _

from pepl_os.pepl_people import people


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "employee_number", "label": _("Employee Number"), "fieldtype": "Data", "width": 110},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Data", "width": 130},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 80},
		{"fieldname": "person_type", "label": _("Person Type"), "fieldtype": "Data", "width": 100},
		{"fieldname": "user_id", "label": _("Login"), "fieldtype": "Link", "options": "User", "width": 190},
		{"fieldname": "login_enabled", "label": _("Login On"), "fieldtype": "Data", "width": 70},
		{"fieldname": "operator", "label": _("Operator"), "fieldtype": "Link", "options": "PEPL Operator", "width": 100},
		{"fieldname": "gaps", "label": _("To Put Right"), "fieldtype": "Data", "width": 300},
	]
	rows = people.register_rows()
	if filters.get("only_gaps"):
		rows = [r for r in rows if r.get("gaps")]
	gaps = len([r for r in rows if r.get("gaps")])
	message = _("{0} rows, {1} with something to put right").format(len(rows), gaps)
	return columns, rows, message
