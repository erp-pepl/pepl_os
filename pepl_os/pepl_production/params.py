"""Cycle 3a - Server validation of the Production rulebook in PEPL System Parameters."""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pepl_os.pepl_production import (
	bottleneck,
	config,
	costing,
	hr_lite,
	job_work,
	kiosk,
	ld,
	ld_exposure,
	load_view,
	machine_booking,
	oee,
	standup,
)
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
	load = doc.get(load_view.WARNING_FIELD)
	if load not in (None, "") and not 0 < flt(load) <= 100:
		errors.append(_("Load View: Warning at % of Machine Hours must be more than 0 and at most 100."))
	aim = doc.get(oee.TARGET_FIELD)
	if aim not in (None, "") and not 0 < flt(aim) <= 100:
		errors.append(_("OEE Target % must be more than 0 and at most 100."))
	errors += config.validate_c1_params(doc)
	errors += hr_lite.validate_params(doc)  # C3a-B3
	wait = doc.get(bottleneck.WARNING_FIELD)
	if wait not in (None, "") and flt(wait) <= 0:
		errors.append(_("Bottleneck: Wait Warning Hours must be more than 0."))  # C3a-B4
	ahead = doc.get(ld_exposure.LOOK_AHEAD_FIELD)
	if ahead not in (None, "") and not 0 <= cint(ahead) <= 365:
		errors.append(_("LD: Look-Ahead Days must be between 0 and 365."))  # C3a-B5
	for field, label, bounds in (
		(kiosk.TRIES_FIELD, _("Kiosk: Wrong PIN Tries"), kiosk.TRIES_RANGE),
		(kiosk.LOCK_FIELD, _("Kiosk: Lock Minutes"), kiosk.LOCK_RANGE),
		(kiosk.SESSION_FIELD, _("Kiosk: Session Minutes"), kiosk.SESSION_RANGE),
	):
		value = doc.get(field)
		if value not in (None, "") and not bounds[0] <= cint(value) <= bounds[1]:
			errors.append(_("{0} must be between {1} and {2}.").format(label, bounds[0], bounds[1]))
	days = doc.get(job_work.RETURN_DAYS_FIELD)
	if days not in (None, "") and cint(days) < 1:
		errors.append(_("Job-Work Return Days must be at least 1."))
	warning = doc.get(job_work.GST_WARNING_FIELD)
	if warning not in (None, "") and not 0 <= cint(warning) < job_work.GST_LIMIT_DAYS:
		errors.append(_("Job-Work GST Warning Days must be between 0 and 364."))
	ahead = doc.get(standup.RISK_DAYS_FIELD)
	if ahead not in (None, "") and cint(ahead) < 0:
		errors.append(_("Stand-up: Days Ahead for Delivery Risk cannot be negative."))
	for field, label in (
		(ld.DEFAULT_RATE_FIELD, _("LD: Default Rate %")),
		(ld.DEFAULT_CAP_FIELD, _("LD: Default Cap %")),
		(costing.WARNING_FIELD, _("Costing: Variance Warning %")),
	):
		value = doc.get(field)
		if value not in (None, "") and not 0 < flt(value) <= 100:
			errors.append(_("{0} must be more than 0 and at most 100.").format(label))
	if errors:
		frappe.throw("<br>".join(errors), title=_("Production rules"))
