"""C3b-P4 - The instrument panel: is it fit to measure today, when is it due, its calibration history and its use.

One panel ("Calibration") at the top of the PEPL Instrument form, in this order:
  "VC-001: Vernier 0-150 (Vernier Caliper) · Active · range 0-150 mm, least count 0.02 mm · at QC room"
  "VC-001 is calibrated until 07-05-2027 (169 day(s) left) · every 365 days"                    green
     due soon: "... is due for calibration on 25-11-2026 (6 day(s) left)" orange; overdue / never: red
  "Last calibration 07-05-2026: Pass · certificate NABL-123 · by Metro Labs (CAL-2026-00004)"
  "Calibration records: 3 (Pass 2, Fail 1) · last Fail 01-02-2026: jaw worn 0.05 mm"
  "Used in 12 submitted QC Inspection(s) in the last 90 days · last MAT-QA-2026-00031 (PIN-10) on 17-11-2026"
  "2 draft QC Inspection(s) name this instrument (MAT-QA-...) - the Calibration Gate (Hard Block) will refuse them"
  "Next: book the calibration before 25-11-2026"  /  "Next: stop using it, calibrate it and submit ..."
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, formatdate, getdate, today

from pepl_os.pepl_quality import calibration as cal

USE_DAYS = 90
DRAFTS_SHOWN = 3


def header_row(doc):
	text = f"{doc.name}: {doc.instrument_name or doc.name}"
	if doc.instrument_type:
		text += f" ({_(doc.instrument_type)})"
	text += " · " + _(doc.status or cal.ACTIVE)
	details = []
	if doc.measuring_range:
		details.append(_("range {0}").format(doc.measuring_range))
	if doc.least_count:
		details.append(_("least count {0}").format(doc.least_count))
	if details:
		text += " · " + ", ".join(details)
	if doc.location:
		text += " · " + _("at {0}").format(doc.location)
	return {"text": text, "colour": "gray"}


def state_row(doc, state, days, due_on):
	text = cal.state_text(doc.name, state, due_on)
	if state == cal.VALID:
		text += " " + _("({0} day(s) left)").format(days)
		colour = "green"
	elif state == cal.DUE_SOON:
		text += " " + _("({0} day(s) left)").format(days)
		colour = "orange"
	elif state == cal.OVERDUE:
		text += " - " + _("{0} day(s) overdue").format(-days)
		colour = "red"
	elif state == cal.NEVER:
		colour = "red"
	else:
		colour = {cal.UNDER_CALIBRATION: "orange", cal.SCRAPPED: "gray"}.get(doc.status, "red")
	if doc.status != cal.SCRAPPED:
		text += " · " + _("every {0} days").format(cint(doc.calibration_frequency_days))
	return {"text": text, "colour": colour}


def records(name):
	return frappe.get_all(
		cal.RECORD,
		filters={"instrument": name, "docstatus": 1},
		fields=["name", "calibration_date", "result", "certificate_no", "agency", "errors_found"],
		order_by="calibration_date desc, creation desc",
	)


def last_row(doc, rows):
	if not rows:
		return {
			"text": _("No calibration record yet"),
			"colour": "gray" if doc.status == cal.SCRAPPED else "orange",
		}
	last = rows[0]
	text = _("Last calibration {0}: {1}").format(formatdate(last.calibration_date), _(last.result))
	if last.certificate_no:
		text += " · " + _("certificate {0}").format(last.certificate_no)
	if last.agency:
		text += " · " + _("by {0}").format(last.agency)
	text += f" ({last.name})"
	return {"text": text, "colour": "red" if last.result == cal.FAIL else "green"}


def history_row(rows):
	if not rows:
		return None
	counts = [
		(result, sum(1 for r in rows if r.result == result))
		for result in (cal.PASS, cal.PASS_ADJUSTED, cal.FAIL)
	]
	text = _("Calibration records: {0} ({1})").format(
		len(rows), ", ".join(f"{_(result)} {n}" for result, n in counts if n)
	)
	fails = [r for r in rows if r.result == cal.FAIL]
	if fails:
		text += " · " + _("last Fail {0}: {1}").format(
			formatdate(fails[0].calibration_date), (fails[0].errors_found or "").strip()[:100] or "-"
		)
	return {"text": text, "colour": "gray"}


def inspections(name):
	"""QC Inspections (not cancelled) with a reading taken with this instrument, newest first."""
	return frappe.db.sql(
		"""
		select qi.name, qi.docstatus, qi.report_date, qi.item_code
		from `tabQuality Inspection Reading` r
		join `tabQuality Inspection` qi on qi.name = r.parent
		where r.parenttype = 'Quality Inspection' and r.custom_instrument = %s and qi.docstatus < 2
		group by qi.name, qi.docstatus, qi.report_date, qi.item_code, qi.creation
		order by qi.report_date desc, qi.creation desc
		""",
		name,
		as_dict=True,
	)


def use_row(used):
	done = [q for q in used if q.docstatus == 1]
	since = getdate(add_days(today(), -USE_DAYS))
	recent = [q for q in done if q.report_date and getdate(q.report_date) >= since]
	if not done:
		return {"text": _("Not used in a submitted QC Inspection yet"), "colour": "gray"}
	last = done[0]
	return {
		"text": _(
			"Used in {0} submitted QC Inspection(s) in the last {1} days · last {2} ({3}) on {4}"
		).format(
			len(recent),
			USE_DAYS,
			last.name,
			last.item_code,
			formatdate(last.report_date) if last.report_date else "-",
		),
		"colour": "gray",
	}


def drafts_row(used, state):
	drafts = [q.name for q in used if q.docstatus == 0]
	if not drafts:
		return None
	names = ", ".join(drafts[:DRAFTS_SHOWN]) + (
		" " + _("and {0} more").format(len(drafts) - DRAFTS_SHOWN) if len(drafts) > DRAFTS_SHOWN else ""
	)
	text = _("{0} draft QC Inspection(s) name this instrument ({1})").format(len(drafts), names)
	if state in cal.USABLE:
		return {"text": text, "colour": "gray"}
	mode = cal.gate_mode()
	effect = {
		cal.ADVISORY: _("will warn when they are submitted"),
		cal.SOFT_BLOCK: _("will ask for a reason when they are submitted"),
		cal.HARD_BLOCK: _("will refuse them"),
	}[mode]
	return {
		"text": text + " - " + _("the Calibration Gate ({0}) {1}").format(_(mode), effect),
		"colour": "red" if mode == cal.HARD_BLOCK else "orange",
	}


def next_row(doc, state, due_on):
	if doc.status == cal.SCRAPPED:
		return {"text": _("Scrapped: it takes no more calibration records"), "colour": "gray"}
	if doc.status == cal.OUT_OF_SERVICE:
		return {
			"text": _("Next: repair it, then submit a passed Calibration Record to bring it back to Active"),
			"colour": "red",
		}
	if doc.status == cal.UNDER_CALIBRATION:
		return {
			"text": _("Next: submit the Calibration Record with the certificate when it comes back"),
			"colour": "orange",
		}
	if state in (cal.OVERDUE, cal.NEVER):
		return {
			"text": _(
				"Next: stop using it, calibrate it and submit a Calibration Record"
				" (or set the status to Under Calibration)"
			),
			"colour": "red",
		}
	if state == cal.DUE_SOON:
		return {
			"text": _("Next: book the calibration before {0}").format(formatdate(due_on)),
			"colour": "orange",
		}
	return None


def panel_rows(doc):
	state, days, due_on = cal.instrument_state(doc.name)
	rows_ = records(doc.name)
	used = inspections(doc.name)
	rows = [
		header_row(doc),
		state_row(doc, state, days, due_on),
		last_row(doc, rows_),
		history_row(rows_),
		use_row(used),
		drafts_row(used, state),
		next_row(doc, state, due_on),
	]
	return [r for r in rows if r]


@frappe.whitelist()
def get_instrument_panel(name):
	"""Rows for the "Calibration" panel of an instrument."""
	doc = frappe.get_doc(cal.INSTRUMENT, name)
	doc.check_permission("read")
	return panel_rows(doc)
