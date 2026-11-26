"""Cycle 4 - Server validation of System Parameters -> People."""

import frappe
from frappe import _

from pepl_os.pepl_people import hr_setup


def validate_people_params(doc, method=None):
	errors = hr_setup.validate_params(doc)
	if errors:
		frappe.throw("<br>".join(errors), title=_("People rules"))
