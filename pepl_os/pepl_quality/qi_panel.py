"""C3b-P1 - The QC Inspection panel: what is measured, against which tolerance, in or out, and with which instrument.

One line per characteristic (reading) of the inspection plan:
  "Diameter 9.9 - 10.1: 10.02, 10.08 (2 readings) - in tolerance"            green
  "Diameter 9.9 - 10.1: 10.02, 10.14 - OUT: 10.14"                           red
  "Thread: expected Go / No-Go OK: not measured yet"                         orange
and, inline, the instrument it was measured with and its calibration:
  "· VC-001 calibrated until 07-05-2027"  /  "· VC-002 is overdue for calibration (due 08-11-2026)" (red)
  "· no instrument named" (grey) when the reading names none.
Then the overall result (Accepted / Rejected, or "to be decided" while a characteristic is not measured), where the
inspection comes from (receipt / delivery line, supplier) and the Calibration Gate in force.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pepl_os.pepl_production.job_order_panel import qty_text
from pepl_os.pepl_quality import calibration

QI = "Quality Inspection"
READINGS = tuple(f"reading_{i}" for i in range(1, 11))

try:  # ERPNext reads a typed reading in the user's number format
	from erpnext.stock.doctype.quality_inspection.quality_inspection import parse_float as _parse
except ImportError:  # pragma: no cover - older ERPNext
	_parse = None


def _number(value):
	if _parse:
		try:
			return _parse(value)
		except Exception:
			pass
	return flt(str(value).replace(",", ""))


def reading_values(reading):
	"""The typed readings of a numeric characteristic, as numbers, in order."""
	return [_number(reading.get(f)) for f in READINGS if (reading.get(f) or "").strip()]


def tolerance_text(reading):
	if cint(reading.get("formula_based_criteria")):
		return _("formula {0}").format(reading.get("acceptance_formula") or "")
	if cint(reading.get("numeric")):
		low, high = reading.get("min_value"), reading.get("max_value")
		return f"{qty_text(low)} - {qty_text(high)}"
	return _("expected {0}").format(reading.get("value") or "-")


def reading_line(reading):
	"""(text, colour) for one characteristic, without the instrument."""
	name = reading.get("specification")
	head = f"{name} {tolerance_text(reading)}"
	if cint(reading.get("manual_inspection")):
		state = reading.get("status") or "Accepted"
		return _("{0}: judged by eye - {1}").format(head, _(state)), "green" if state == "Accepted" else "red"
	if cint(reading.get("numeric")) and not cint(reading.get("formula_based_criteria")):
		values = reading_values(reading)
		if not values:
			return _("{0}: not measured yet").format(head), "orange"
		low, high = flt(reading.get("min_value")), flt(reading.get("max_value"))
		out = [v for v in values if not low <= v <= high]
		shown = ", ".join(qty_text(v) for v in values)
		count = _(" ({0} readings)").format(len(values)) if len(values) > 1 else ""
		if out:
			return _("{0}: {1}{2} - OUT: {3}").format(
				head, shown, count, ", ".join(qty_text(v) for v in out)
			), "red"
		return _("{0}: {1}{2} - in tolerance").format(head, shown, count), "green"
	typed = (reading.get("reading_value") or "").strip()
	if not typed and not cint(reading.get("formula_based_criteria")):
		return _("{0}: not measured yet").format(head), "orange"
	state = reading.get("status") or ""
	return _("{0}: {1} - {2}").format(
		head, typed or _("see readings"), _(state)
	), "green" if state == "Accepted" else "red"


def instrument_text(reading):
	"""(text, colour) for the instrument of a reading."""
	name = reading.get(calibration.READING_FIELD)
	if not name:
		return _("no instrument named"), "gray"
	state, _days, due_on = calibration.instrument_state(name)
	colour = {calibration.VALID: "green", calibration.DUE_SOON: "orange"}.get(state, "red")
	return calibration.state_text(name, state, due_on), colour


def _worse(a, b):
	order = {"gray": 0, "green": 1, "orange": 2, "red": 3}
	return a if order[a] >= order[b] else b


@frappe.whitelist()
def get_inspection_panel(name):
	"""Rows for the "QC Inspection" panel."""
	doc = frappe.get_doc(QI, name)
	doc.check_permission("read")
	rows = []
	source = _("{0} {1}").format(_(doc.reference_type or ""), doc.reference_name or "").strip()
	if doc.get("custom_supplier"):
		source += _(" from {0}").format(doc.custom_supplier)
	rows.append(
		{
			"text": _("{0} inspection of {1}: sample {2}{3}").format(
				_(doc.inspection_type),
				doc.item_code,
				qty_text(doc.sample_size),
				(" · " + source) if source else "",
			),
			"colour": "gray",
		}
	)
	if not doc.get("readings"):
		rows.append(
			{
				"text": _(
					"No inspection plan: set the item's Quality Inspection Template, or judge the lot as a whole."
				),
				"colour": "orange",
			}
		)
	pending = rejected = 0
	for reading in doc.get("readings") or []:
		text, colour = reading_line(reading)
		inst_text, inst_colour = instrument_text(reading)
		pending += colour == "orange"
		rejected += colour == "red"
		rows.append({"text": f"{text} · {inst_text}", "colour": _worse(colour, inst_colour)})
	if doc.docstatus == 1:
		rows.append(
			{
				"text": _("Result: {0}").format(_(doc.status)),
				"colour": "green" if doc.status == "Accepted" else "red",
			}
		)
	elif pending:
		rows.append({"text": _("{0} characteristic(s) still to measure").format(pending), "colour": "orange"})
	else:
		rows.append(
			{
				"text": _("Result on submit: {0}").format(_("Rejected") if rejected else _("Accepted")),
				"colour": "red" if rejected else "green",
			}
		)
	if doc.docstatus == 0 and doc.get("readings"):
		rows.append({"text": _("Calibration gate: {0}").format(_(calibration.gate_mode())), "colour": "gray"})
	return rows
