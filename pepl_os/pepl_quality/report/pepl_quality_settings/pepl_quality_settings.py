# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3b-C1 - Quality Settings: every Quality setting with its value and default, the sign-off matrix in practice,
Stock Settings for QC and the master data the rules need - the sheet confirmed with PEPL's Quality Manager."""

from frappe import _

from pepl_os.pepl_quality import config


def execute(filters=None):
	columns = [
		{"fieldname": "area", "label": _("Area"), "fieldtype": "Data", "width": 190},
		{"fieldname": "setting", "label": _("Setting"), "fieldtype": "Data", "width": 300},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Data", "width": 220},
		{"fieldname": "default", "label": _("Default"), "fieldtype": "Data", "width": 160},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 300},
		{"fieldname": "description", "label": _("What it does"), "fieldtype": "Data", "width": 420},
	]
	return columns, config.settings_rows()
