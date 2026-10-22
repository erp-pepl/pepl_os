"""Cycle 3a - Server validation of the Production rulebook in PEPL System Parameters."""

import frappe
from frappe import _
from frappe.utils import cint

from pepl_os.pepl_production import machine_booking
from pepl_os.pepl_production.masters import PIN_DIGITS_FIELD, PIN_DIGITS_RANGE
from pepl_os.pepl_production.spr import GRACE_FIELD, GRACE_RANGE, UNACCOUNTED_FIELD


def validate_production_params(doc, method=None):
	errors = []
	low, high = PIN_DIGITS_RANGE
	digits = doc.get(PIN_DIGITS_FIELD)
	if digits not in (None, "") and not low <= cint(digits) <= high:
		errors.append(_("Operator PIN Digits must be between {0} and {1}.").format(low, high))
	low, high = GRACE_RANGE
	grace = doc.get(GRACE_FIELD)
	if grace not in (None, "") and not low <= cint(grace) <= high:
		errors.append(_("Shift Entry Grace Minutes must be between {0} and {1}.").format(low, high))
	unexplained = doc.get(UNACCOUNTED_FIELD)
	if unexplained not in (None, "") and cint(unexplained) < 0:
		errors.append(_("Shift Entry Minutes Allowed Unexplained cannot be negative."))
	booking_mode = doc.get(machine_booking.MODE_FIELD)
	if booking_mode not in (None, "") and booking_mode not in machine_booking.MODES:
		errors.append(_("Machine Double-Booking Mode must be Advisory, Soft Block or Hard Block."))
	if errors:
		frappe.throw("<br>".join(errors), title=_("Production rules"))
