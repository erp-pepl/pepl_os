# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-B3 - Skill Matrix: every operator against every machine group (level 1-4, expired, expiring soon), how many
qualified operators each group has, and what is missing on each operator. See pepl_production/hr_lite.py."""

import frappe
from frappe import _

from pepl_os.pepl_production import hr_lite


def execute(filters=None):
	filters = frappe._dict(filters or {})
	groups, keys, rows, cover_row, thin = hr_lite.matrix(filters)
	columns = [
		{
			"fieldname": "operator",
			"label": _("Operator"),
			"fieldtype": "Link",
			"options": "PEPL Operator",
			"width": 120,
		},
		{"fieldname": "operator_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 80},
		{"fieldname": "default_shift", "label": _("Default Shift"), "fieldtype": "Data", "width": 120},
		{"fieldname": "eligible_shifts", "label": _("Eligible Shifts"), "fieldtype": "Data", "width": 140},
	]
	columns += [{"fieldname": keys[g], "label": g, "fieldtype": "Data", "width": 110} for g in groups]
	columns += [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{"fieldname": "issues", "label": _("To Do"), "fieldtype": "Data", "width": 320},
	]
	data = rows + ([cover_row] if groups else [])
	message = _(
		"Levels: 1 Trainee · 2 Under supervision · 3 Independent · 4 Sets up and trains. Green = at or above the "
		"Minimum Skill Level; orange = below it or expiring within {0} days; red = expired."
	).format(hr_lite.expiry_days())
	if thin:
		message += " " + _("Fewer than {0} qualified operators on: {1}.").format(
			hr_lite.min_cover(), ", ".join(thin)
		)
	return columns, data, frappe.utils.escape_html(message)
