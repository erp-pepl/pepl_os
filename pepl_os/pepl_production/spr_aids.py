"""C3a-P5 - Entry aids on the Shift Production Entry: what is missing, what is left, and how fast it ran.

Shown on a saved entry (draft or submitted), next to the X1 "Shift" panel:
- Gaps: the stretches of the shift that no row covers - this entry's production and downtime rows plus the
  rows of the other entries of the same machine, shift and day (two operators may share a shift). The shift's
  break is one of them, so the headline says how long the break is. On a draft, "Add rows for the gaps" adds
  one downtime row per gap, with the times filled in; the operator picks the category.
- Job Cards: for each Job Card on the entry, the target, what is already done (submitted time logs of other
  entries), this entry's good quantity and what is left; red when this entry takes it over the target.
- Speed: for each production row, pieces x the Job Card's standard minutes a piece against the minutes the
  row took. Below "Shift Entry: Slow Below % of Standard Speed" (System Parameters -> Production, 80) the row
  is orange, so a wrong time or quantity is caught while the operator still remembers the shift.
- Open Job Cards on this machine that the entry does not use yet (the next ones to pick).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime

from pepl_os.common import params
from pepl_os.pepl_production import spr
from pepl_os.pepl_production.job_order_panel import qty_text
from pepl_os.pepl_production.masters import SHIFT

SLOW_FIELD = "custom_spr_slow_speed_percent"
DEFAULT_SLOW = 80
MAX_GAPS = 8
MAX_OPEN_CARDS = 5


def slow_percent():
	value = params.get(SLOW_FIELD, DEFAULT_SLOW)
	return flt(value) if value not in (None, "") else DEFAULT_SLOW


def _shift(doc):
	return frappe.db.get_value(
		SHIFT, doc.shift, ["start_time", "end_time", "break_minutes", "planned_minutes"], as_dict=True
	)


def covered(doc):
	"""(start, end) of every row of this entry and of the other entries of the same machine, shift and day."""
	spans = [
		(get_datetime(r.from_datetime), get_datetime(r.to_datetime))
		for r in (doc.get("production") or []) + (doc.get("downtime") or [])
		if r.from_datetime and r.to_datetime
	]
	for table in (spr.PRODUCTION_ROW, spr.DOWNTIME_ROW):
		for r in frappe.db.sql(
			f"""select r.from_datetime, r.to_datetime from `tab{table}` r
			join `tab{spr.DOCTYPE}` s on s.name = r.parent
			where s.workstation = %s and s.shift = %s and s.posting_date = %s and s.docstatus < 2 and s.name != %s""",
			(doc.workstation, doc.shift, doc.posting_date, doc.name or ""),
			as_dict=True,
		):
			if r.from_datetime and r.to_datetime:
				spans.append((get_datetime(r.from_datetime), get_datetime(r.to_datetime)))
	return sorted(spans)


def gaps(doc, shift=None):
	"""[(start, end, minutes)] of the shift not covered by any row (a minute or more)."""
	shift = shift or _shift(doc)
	if not shift:
		return []
	start, end = spr.shift_window(doc.posting_date, shift)
	result, cursor = [], start
	for begin, finish in covered(doc):
		if finish <= cursor:
			continue
		if begin > cursor:
			stop = min(begin, end)
			if stop > cursor:
				result.append((cursor, stop))
		cursor = max(cursor, finish)
		if cursor >= end:
			break
	if cursor < end:
		result.append((cursor, end))
	return [(a, b, spr._minutes(a, b)) for a, b in result if spr._minutes(a, b) >= 1]


def _standard_minutes(job_cards):
	if not job_cards:
		return {}
	return {
		r.name: frappe._dict(per_piece=flt(r.time_required) / flt(r.for_quantity), target=flt(r.for_quantity))
		if flt(r.for_quantity) > 0
		else frappe._dict(per_piece=0, target=0)
		for r in frappe.get_all(
			"Job Card",
			filters={"name": ["in", list(job_cards)]},
			fields=["name", "time_required", "for_quantity", "production_item", "operation"],
		)
	}


def aid_rows(doc):
	rows = []
	shift = _shift(doc)
	open_gaps = gaps(doc, shift) if shift else []
	if shift:
		if open_gaps:
			total = sum(g[2] for g in open_gaps)
			text = _("{0} gap(s) in the shift not covered by any row, {1} min").format(len(open_gaps), total)
			if cint(shift.break_minutes):
				text += " " + _("(the shift's {0}-minute break is one of them)").format(
					cint(shift.break_minutes)
				)
			allowed = cint(shift.break_minutes) + spr.unaccounted_limit()
			rows.append({"text": text, "colour": "orange" if total > allowed else "gray"})
			for a, b, minutes in open_gaps[:MAX_GAPS]:
				rows.append(
					{
						"text": _("Not covered: {0}-{1} ({2} min)").format(
							spr._clock(a), spr._clock(b), minutes
						),
						"colour": "gray",
					}
				)
			if len(open_gaps) > MAX_GAPS:
				rows.append(
					{"text": _("... and {0} more gap(s)").format(len(open_gaps) - MAX_GAPS), "colour": "gray"}
				)
		else:
			rows.append({"text": _("Every minute of the shift is covered by a row"), "colour": "green"})

	production = doc.get("production") or []
	cards = {r.job_card for r in production if r.job_card}
	standard = _standard_minutes(cards)
	extra = spr._overproduction_percent()
	good_here = {}
	for r in production:
		if r.job_card:
			good_here[r.job_card] = good_here.get(r.job_card, 0) + flt(r.good_qty)
	for card in sorted(good_here):
		info = standard.get(card) or frappe._dict(target=0, per_piece=0)
		done = spr.job_card_qty_done(card, doc.name)
		left = info.target - done - good_here[card]
		over = done + good_here[card] > info.target * (1 + extra / 100) + 1e-9
		text = _("Job Card {0}: target {1}, done before {2}, this entry {3} - {4}").format(
			card,
			qty_text(info.target),
			qty_text(done),
			qty_text(good_here[card]),
			_("over the target by {0}").format(qty_text(-left))
			if left < -1e-9
			else (_("finished") if abs(left) <= 1e-9 else _("{0} left").format(qty_text(left))),
		)
		rows.append({"text": text, "colour": "red" if over else ("green" if left <= 1e-9 else "gray")})

	slow = slow_percent()
	for r in production:
		info = standard.get(r.job_card)
		pieces = flt(r.good_qty) + flt(r.rejected_qty)
		if not info or not info.per_piece or not cint(r.minutes) or not pieces:
			continue
		expected = pieces * info.per_piece
		speed = round(100.0 * expected / cint(r.minutes))
		rows.append(
			{
				"text": _(
					"Row {0}: {1} piece(s) x {2} min standard = {3} min; took {4} min - {5}% of standard speed"
				).format(
					r.idx,
					qty_text(pieces),
					qty_text(round(info.per_piece, 2)),
					qty_text(round(expected, 1)),
					cint(r.minutes),
					speed,
				)
				+ (" - " + _("check the time and the quantity") if speed < slow else ""),
				"colour": "orange" if speed < slow else "green",
			}
		)

	if doc.docstatus == 0 and doc.workstation:
		open_cards = frappe.get_all(
			"Job Card",
			filters={"workstation": doc.workstation, "docstatus": 0, "name": ["not in", list(cards) or [""]]},
			fields=["name", "production_item", "operation", "for_quantity", "total_completed_qty"],
			order_by="creation",
			limit=MAX_OPEN_CARDS + 1,
		)
		for c in open_cards[:MAX_OPEN_CARDS]:
			rows.append(
				{
					"text": _("Open on this machine: Job Card {0} - {1}, {2}: {3} of {4} done").format(
						c.name,
						c.production_item,
						c.operation,
						qty_text(c.total_completed_qty),
						qty_text(c.for_quantity),
					),
					"colour": "gray",
				}
			)
		if len(open_cards) > MAX_OPEN_CARDS:
			rows.append({"text": _("... more open Job Cards on this machine"), "colour": "gray"})
	return rows


def gap_rows_to_add(doc):
	"""For the "Add rows for the gaps" button: [{from_time, to_time}] clock times of each gap."""
	return [
		{"from_time": a.strftime("%H:%M:%S"), "to_time": b.strftime("%H:%M:%S")} for a, b, _m in gaps(doc)
	]


@frappe.whitelist()
def get_spr_aids(name):
	"""For the Shift Production Entry form: {rows, gaps}."""
	doc = frappe.get_doc(spr.DOCTYPE, name)
	doc.check_permission("read")
	return {"rows": aid_rows(doc), "gaps": gap_rows_to_add(doc) if doc.docstatus == 0 else []}
