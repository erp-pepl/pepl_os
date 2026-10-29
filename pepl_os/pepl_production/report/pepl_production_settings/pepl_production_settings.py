# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-C1 - Production Settings: every Production setting with its value and default - the sheet confirmed with the
Production HOD."""

from frappe import _

from pepl_os.pepl_production import config


def execute(filters=None):
	columns = [
		{"fieldname": "area", "label": _("Area"), "fieldtype": "Data", "width": 170},
		{"fieldname": "setting", "label": _("Setting"), "fieldtype": "Data", "width": 280},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Data", "width": 160},
		{"fieldname": "default", "label": _("Default"), "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 220},
		{"fieldname": "description", "label": _("What it does"), "fieldtype": "Data", "width": 420},
	]
	return columns, config.settings_rows()
