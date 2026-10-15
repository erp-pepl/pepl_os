"""Cycle 3a - Server validation of the Production rulebook in PEPL System Parameters."""

import frappe
from frappe import _
from frappe.utils import cint

from pepl_os.pepl_production.masters import PIN_DIGITS_FIELD, PIN_DIGITS_RANGE


def validate_production_params(doc, method=None):
	errors = []
	low, high = PIN_DIGITS_RANGE
	digits = doc.get(PIN_DIGITS_FIELD)
	if digits not in (None, "") and not low <= cint(digits) <= high:
		errors.append(_("Operator PIN Digits must be between {0} and {1}.").format(low, high))
	if errors:
		frappe.throw("<br>".join(errors), title=_("Production rules"))
