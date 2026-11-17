"""C3b-Q2 - Instruments and calibration: the instrument master, calibration records, the daily due / overdue alert
and the calibration gate on a QC Inspection.

PEPL Instrument (one record per physical gauge or instrument, named by its ID):
  * Calibration Frequency (days) is required; last calibrated, due date, certificate and the last record are filled
    from its submitted PEPL Calibration Records, never typed;
  * Calibration State: Valid / Due Soon (due within "Calibration: Alert Days") / Overdue / Never Calibrated /
    Not in Use (status other than Active).

PEPL Calibration Record (submitted):
  * date not in the future; Next Due On = date + the instrument's frequency unless typed; a Pass needs the
    certificate (number or file); a Fail needs what was found;
  * on submit the instrument takes the dates and certificate of its latest submitted record; a Fail puts it Out of
    Service, a Pass puts an Out of Service / Under Calibration instrument back to Active; cancelling a record goes
    back to the previous one. A Scrapped instrument takes no record.

Daily job: every instrument in use that is Due Soon, Overdue or Never Calibrated gives the Quality Notification
Owner one ToDo (QA-CAL-DUE; High when overdue or never calibrated), closed by itself once calibrated.

Calibration gate (QC Inspection submit, "Calibration Gate" in System Parameters): a reading taken with an
instrument that is Overdue, Never Calibrated or not in use - Advisory = warning; Soft Block = a reason (QA-CAL-GATE,
Override Log); Hard Block (default) = refused. ISO 9001 7.1.5: an instrument out of calibration is not used.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, formatdate, getdate, today

from pepl_os.common import alerts, params
from pepl_os.common.jobs import tracked_job
from pepl_os.common.overrides import has_recent_override

INSTRUMENT = "PEPL Instrument"
RECORD = "PEPL Calibration Record"
QI = "Quality Inspection"
READING_FIELD = "custom_instrument"
OWNER_FIELD = "custom_quality_notification_owner"
ALERT_FIELD = "custom_calibration_alert_days"
GATE_FIELD = "custom_calibration_gate_mode"
ALERT_RANGE = (0, 365)
FREQUENCY_RANGE = (1, 3650)
DUE_RULE = "QA-CAL-DUE"
GATE_RULE = "QA-CAL-GATE"

ACTIVE, UNDER_CALIBRATION, OUT_OF_SERVICE, SCRAPPED = (
	"Active",
	"Under Calibration",
	"Out of Service",
	"Scrapped",
)
VALID, DUE_SOON, OVERDUE, NEVER, NOT_IN_USE = "Valid", "Due Soon", "Overdue", "Never Calibrated", "Not in Use"
USABLE = (VALID, DUE_SOON)
PASS, PASS_ADJUSTED, FAIL = "Pass", "Pass after Adjustment", "Fail"
ADVISORY, SOFT_BLOCK, HARD_BLOCK = "Advisory", "Soft Block", "Hard Block"
MODES = (ADVISORY, SOFT_BLOCK, HARD_BLOCK)


# Settings ---------------------------------------------------------------------------------------------------


def alert_days():
	return params.get_int(ALERT_FIELD, 15)


def gate_mode():
	mode = params.get(GATE_FIELD, HARD_BLOCK) or HARD_BLOCK
	return mode if mode in MODES else HARD_BLOCK


def validate_params(doc):
	errors = []
	low, high = ALERT_RANGE
	days = doc.get(ALERT_FIELD)
	if days not in (None, "") and not low <= cint(days) <= high:
		errors.append(_("Calibration: Alert Days must be between {0} and {1}.").format(low, high))
	mode = doc.get(GATE_FIELD)
	if mode not in (None, "") and mode not in MODES:
		errors.append(_("Calibration Gate must be Advisory, Soft Block or Hard Block."))
	return errors


# State -------------------------------------------------------------------------------------------------------


def state_of(status, due_on, as_of=None, window=None):
	"""(state, days to due) of an instrument. Days are negative when overdue, None when there is no due date."""
	window = alert_days() if window is None else window
	days = date_diff(getdate(due_on), getdate(as_of or today())) if due_on else None
	if (status or ACTIVE) != ACTIVE:
		return NOT_IN_USE, days
	if days is None:
		return NEVER, None
	if days < 0:
		return OVERDUE, days
	if days <= window:
		return DUE_SOON, days
	return VALID, days


def state_text(name, state, due_on):
	if state == OVERDUE:
		return _("{0} is overdue for calibration (due {1})").format(name, formatdate(due_on))
	if state == NEVER:
		return _("{0} has never been calibrated").format(name)
	if state == NOT_IN_USE:
		return _("{0} is not in use ({1})").format(name, frappe.db.get_value(INSTRUMENT, name, "status"))
	if state == DUE_SOON:
		return _("{0} is due for calibration on {1}").format(name, formatdate(due_on))
	return _("{0} is calibrated until {1}").format(name, formatdate(due_on))


def instrument_state(name, as_of=None):
	values = frappe.db.get_value(INSTRUMENT, name, ["status", "calibration_due_on"], as_dict=True)
	if not values:
		return NOT_IN_USE, None, None
	state, days = state_of(values.status, values.calibration_due_on, as_of)
	return state, days, values.calibration_due_on


# PEPL Instrument -----------------------------------------------------------------------------------------------


def validate_instrument(doc):
	doc.instrument_id = (doc.instrument_id or "").strip()
	low, high = FREQUENCY_RANGE
	if not low <= cint(doc.calibration_frequency_days) <= high:
		frappe.throw(_("Calibration Frequency must be between {0} and {1} days.").format(low, high))
	doc.calibration_state, doc.days_to_due = state_of(doc.status, doc.calibration_due_on)


def latest_record(instrument):
	rows = frappe.get_all(
		RECORD,
		filters={"instrument": instrument, "docstatus": 1},
		fields=["name", "calibration_date", "next_due_on", "certificate", "certificate_no", "result"],
		order_by="calibration_date desc, creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def refresh_from_records(instrument):
	"""The instrument's calibration fields from its latest submitted record (or empty when it has none)."""
	last = latest_record(instrument)
	values = {
		"last_calibrated_on": last.calibration_date if last else None,
		"calibration_due_on": last.next_due_on if last else None,
		"last_certificate": (last.certificate if last else None) or None,
		"last_certificate_no": (last.certificate_no if last else None) or None,
		"last_calibration_record": last.name if last else None,
	}
	status = frappe.db.get_value(INSTRUMENT, instrument, "status")
	values["calibration_state"], values["days_to_due"] = state_of(status, values["calibration_due_on"])
	frappe.db.set_value(INSTRUMENT, instrument, values)
	return values


# PEPL Calibration Record -----------------------------------------------------------------------------------------


def validate_record(doc):
	instrument = frappe.db.get_value(
		INSTRUMENT, doc.instrument, ["status", "calibration_frequency_days"], as_dict=True
	)
	if not instrument:
		frappe.throw(_("Instrument {0} not found.").format(doc.instrument))
	if instrument.status == SCRAPPED:
		frappe.throw(_("Instrument {0} is Scrapped; it is not calibrated any more.").format(doc.instrument))
	if getdate(doc.calibration_date) > getdate(today()):
		frappe.throw(_("Calibration Date cannot be in the future."))
	if not doc.next_due_on:
		doc.next_due_on = add_days(doc.calibration_date, cint(instrument.calibration_frequency_days))
	if getdate(doc.next_due_on) <= getdate(doc.calibration_date):
		frappe.throw(_("Next Due On must be after the Calibration Date."))


def before_submit_record(doc):
	if doc.result in (PASS, PASS_ADJUSTED) and not (doc.certificate or (doc.certificate_no or "").strip()):
		frappe.throw(
			_("A passed calibration needs its certificate: give the certificate number or attach the file.")
		)
	if doc.result == FAIL and not (doc.errors_found or "").strip():
		frappe.throw(_("A failed calibration needs 'Errors Found': what was wrong with the instrument."))


def on_submit_record(doc):
	status = frappe.db.get_value(INSTRUMENT, doc.instrument, "status")
	if doc.result == FAIL:
		frappe.db.set_value(INSTRUMENT, doc.instrument, "status", OUT_OF_SERVICE)
	elif status in (OUT_OF_SERVICE, UNDER_CALIBRATION):
		frappe.db.set_value(INSTRUMENT, doc.instrument, "status", ACTIVE)
	refresh_from_records(doc.instrument)
	refresh_alert(doc.instrument)


def on_cancel_record(doc):
	refresh_from_records(doc.instrument)
	refresh_alert(doc.instrument)


# Daily alert -------------------------------------------------------------------------------------------------------


def _alert_description(name, instrument_name, state, due_on):
	return _("{0} ({1}). Calibrate it and submit a Calibration Record with the certificate.").format(
		state_text(name, state, due_on), instrument_name or name
	)


def refresh_alert(name, as_of=None):
	"""Raise or close the QA-CAL-DUE ToDo of one instrument. Returns True when it needs attention."""
	values = frappe.db.get_value(
		INSTRUMENT, name, ["instrument_name", "status", "calibration_due_on"], as_dict=True
	)
	state, _days = state_of(values.status, values.calibration_due_on, as_of) if values else (NOT_IN_USE, None)
	if values and state in (DUE_SOON, OVERDUE, NEVER):
		alerts.raise_todo(
			DUE_RULE,
			INSTRUMENT,
			name,
			_alert_description(name, values.instrument_name, state, values.calibration_due_on),
			owner_field=OWNER_FIELD,
			priority="Medium" if state == DUE_SOON else "High",
			due_date=values.calibration_due_on,
		)
		return True
	alerts.close_one(DUE_RULE, INSTRUMENT, name)
	return False


def refresh_calibration_alerts(as_of=None):
	"""Every instrument's state and days to due, and the QA-CAL-DUE ToDos."""
	active = []
	touched = 0
	for row in frappe.get_all(
		INSTRUMENT,
		fields=[
			"name",
			"instrument_name",
			"status",
			"calibration_due_on",
			"calibration_state",
			"days_to_due",
		],
	):
		state, days = state_of(row.status, row.calibration_due_on, as_of)
		if (state, days) != (row.calibration_state, row.days_to_due):
			frappe.db.set_value(
				INSTRUMENT, row.name, {"calibration_state": state, "days_to_due": days}, update_modified=False
			)
			touched += 1
		if state in (DUE_SOON, OVERDUE, NEVER):
			alerts.raise_todo(
				DUE_RULE,
				INSTRUMENT,
				row.name,
				_alert_description(row.name, row.instrument_name, state, row.calibration_due_on),
				owner_field=OWNER_FIELD,
				priority="Medium" if state == DUE_SOON else "High",
				due_date=row.calibration_due_on,
			)
			active.append(row.name)
	alerts.close_resolved(DUE_RULE, INSTRUMENT, active)
	return {
		"records_touched": touched,
		"message": _("{0} instrument(s) due, overdue or never calibrated").format(len(active)),
	}


@tracked_job("Instrument calibration due alerts")
def daily_calibration_alerts():
	return refresh_calibration_alerts()


@frappe.whitelist()
def run_calibration_alerts_now():
	"""The daily check, now (Quality Manager / System Manager): states, days to due and ToDos brought up to date."""
	frappe.only_for(("System Manager", "Quality Manager"))
	return refresh_calibration_alerts()


# The calibration gate on a QC Inspection -----------------------------------------------------------------------------


def inspection_gaps(doc):
	"""[(reading, text)] for readings taken with an instrument that may not be used."""
	gaps = []
	for reading in doc.get("readings") or []:
		name = reading.get(READING_FIELD)
		if not name:
			continue
		state, _days, due_on = instrument_state(name)
		if state not in USABLE:
			gaps.append((reading, state_text(name, state, due_on)))
	return gaps


def gap_message(gaps):
	return "<br>".join(
		_("Reading {0} {1}: {2}").format(reading.idx, reading.specification, text) for reading, text in gaps
	)


def before_submit_inspection(doc, method=None):
	"""doc_events: Quality Inspection before_submit. The calibration gate."""
	gaps = inspection_gaps(doc)
	if not gaps:
		return
	message = gap_message(gaps)
	mode = gate_mode()
	if mode == ADVISORY:
		frappe.msgprint(message, title=_("Instrument not calibrated"), indicator="orange")
		return
	if mode == SOFT_BLOCK:
		if has_recent_override(GATE_RULE, doc.doctype, doc.name):
			return
		frappe.throw(
			f"[{GATE_RULE}] " + message + "<br>" + _("A reason is required to continue."),
			title=_("Reason required"),
		)
	frappe.throw(
		_("An instrument out of calibration may not be used:") + "<br>" + message,
		title=_("Instrument not calibrated"),
	)


@frappe.whitelist()
def calibration_gate_check(name):
	"""For the QC Inspection form: the reason dialog message (Soft Block), or None."""
	doc = frappe.get_doc(QI, name)
	doc.check_permission("read")
	gaps = inspection_gaps(doc)
	if not gaps or gate_mode() != SOFT_BLOCK or has_recent_override(GATE_RULE, QI, name):
		return None
	return {
		"rule_code": GATE_RULE,
		"message": frappe.utils.strip_html(gap_message(gaps).replace("<br>", "; ")),
	}
