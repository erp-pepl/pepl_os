"""C3a-X3 - Daily OEE per machine, from the submitted Shift Production Entries.

One PEPL OEE Daily record per machine (Workstation) and day (the entries' shift date):

- Planned minutes: the planned minutes of each shift worked on the machine that day (counted once per shift,
  even when two operators shared it).
- Planned Production Time = planned minutes - Planned stops - PM / Calibration stops when the pepl_sales
  parameter "OEE: Exclude PM/Calibration from Planned Time" is on (otherwise PM counts as an unplanned stop).
- Run Time = the minutes of the production blocks.
- Availability = Run Time / Planned Production Time.
- Performance = standard minutes of the pieces made (good + rejected) x the Job Card's standard minutes per
  piece / Run Time of those blocks. Above 100 % usually means the standard time is too loose: OEE then uses
  100 % and the record says so.
- Quality = good / (good + rejected).
- OEE = Availability x Performance x Quality, compared with "OEE Target %" in System Parameters.

The record is rebuilt whenever an entry of that machine and day is submitted or cancelled, and every night
for yesterday (a safety net). With no submitted entry left, the record is removed. Building OEE never stops
the shift entry: a failure is written to the Error Log.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate, now_datetime, today

from pepl_os.common import params
from pepl_os.pepl_production import config

DOCTYPE = "PEPL OEE Daily"
SPR = "PEPL Shift Production Entry"
PLANNED, UNPLANNED, PM = "Planned", "Unplanned", "PM / Calibration"
EXCLUDE_PM_FIELD = "oee_planned_time_excludes_pm"  # owned by pepl_sales
TARGET_FIELD = "custom_oee_target_percent"
DEFAULT_TARGET = 65
MAX_REBUILD_DAYS = 92


def _percent(numerator, denominator):
	return round(100.0 * flt(numerator) / flt(denominator), 2) if flt(denominator) > 0 else 0.0


def target():
	return flt(params.get(TARGET_FIELD, DEFAULT_TARGET))


def record_name(workstation, oee_date):
	return frappe.db.get_value(DOCTYPE, {"workstation": workstation, "oee_date": oee_date}, "name")


def _standard_minutes_per_piece(job_cards):
	"""{job_card: standard minutes per piece} from each Job Card's time required and quantity."""
	if not job_cards:
		return {}
	rows = frappe.get_all(
		"Job Card",
		filters={"name": ["in", list(job_cards)]},
		fields=["name", "time_required", "for_quantity"],
	)
	return {r.name: flt(r.time_required) / flt(r.for_quantity) for r in rows if flt(r.for_quantity) > 0}


def compute(workstation, oee_date):
	"""The day's figures for one machine, or None when it has no submitted entry that day."""
	entries = frappe.get_all(
		SPR,
		filters={"workstation": workstation, "posting_date": oee_date, "docstatus": 1},
		fields=["name", "shift", "company", "workstation_type"],
		order_by="name",
	)
	if not entries:
		return None
	names = [e.name for e in entries]
	shifts = sorted({e.shift for e in entries})
	planned = sum(cint(frappe.db.get_value("PEPL Shift", s, "planned_minutes")) for s in shifts)

	stops = frappe.get_all(
		"PEPL SPR Downtime",
		filters={"parent": ["in", names], "parenttype": SPR},
		fields=["minutes", "stop_type", "is_breakdown"],
	)
	planned_stop = sum(cint(s.minutes) for s in stops if s.stop_type == PLANNED)
	pm = sum(cint(s.minutes) for s in stops if s.stop_type == PM)
	unplanned = sum(cint(s.minutes) for s in stops if s.stop_type not in (PLANNED, PM))
	breakdowns = [s for s in stops if cint(s.is_breakdown)]
	exclude_pm = params.is_enabled(EXCLUDE_PM_FIELD, 1)
	planned_production = max(planned - planned_stop - (pm if exclude_pm else 0), 0)
	unplanned_stop = unplanned + (0 if exclude_pm else pm)

	blocks = frappe.get_all(
		"PEPL SPR Production",
		filters={"parent": ["in", names], "parenttype": SPR},
		fields=["job_card", "minutes", "good_qty", "rejected_qty"],
	)
	standard = _standard_minutes_per_piece({b.job_card for b in blocks if b.job_card})
	run = sum(cint(b.minutes) for b in blocks)
	good = sum(flt(b.good_qty) for b in blocks)
	rejected = sum(flt(b.rejected_qty) for b in blocks)
	timed = [b for b in blocks if standard.get(b.job_card)]
	ideal = sum((flt(b.good_qty) + flt(b.rejected_qty)) * standard[b.job_card] for b in timed)
	timed_run = sum(cint(b.minutes) for b in timed)

	availability = _percent(run, planned_production)
	performance = _percent(ideal, timed_run)
	quality = _percent(good, good + rejected)
	oee = round(availability * min(performance, 100.0) * quality / 10000.0, 2)
	aim = target()

	notes = []
	if performance > 100:
		notes.append(
			_("Performance is above 100 %: the standard time of a Job Card looks too loose; OEE uses 100 %.")
		)
	if len(timed) < len(blocks):
		notes.append(
			_(
				"{0} production block(s) have no standard time on their Job Card and are left out of Performance."
			).format(len(blocks) - len(timed))
		)
	return {
		"workstation": workstation,
		"oee_date": getdate(oee_date),
		"workstation_type": entries[0].workstation_type
		or frappe.db.get_value("Workstation", workstation, "workstation_type"),
		"company": entries[0].company,
		"shifts": ", ".join(shifts),
		"entries": len(entries),
		"planned_minutes": planned,
		"planned_stop_minutes": planned_stop,
		"pm_minutes": pm,
		"planned_production_minutes": planned_production,
		"unplanned_stop_minutes": unplanned_stop,
		"breakdown_count": len(breakdowns),
		"breakdown_minutes": sum(cint(s.minutes) for s in breakdowns),
		"run_minutes": run,
		"unexplained_minutes": max(planned - run - planned_stop - pm - unplanned, 0),
		"ideal_minutes": round(ideal, 2),
		"blocks_without_standard": len(blocks) - len(timed),
		"good_qty": good,
		"rejected_qty": rejected,
		"availability": availability,
		"performance": performance,
		"quality": quality,
		"oee": oee,
		"target": aim,
		"below_target": 1 if oee < aim else 0,
		"factors_below_target": config.factors_below(availability, performance, quality),  # C3a-C1
		"notes": "\n".join(notes),
		"computed_on": now_datetime(),
	}


def build_day(workstation, oee_date):
	"""Create, update or remove the record of one machine and day. Returns its name or None."""
	values = compute(workstation, oee_date)
	existing = record_name(workstation, oee_date)
	if values is None:
		if existing:
			frappe.delete_doc(DOCTYPE, existing, ignore_permissions=True, force=True)
		return None
	doc = frappe.get_doc(DOCTYPE, existing) if existing else frappe.new_doc(DOCTYPE)
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.save()
	return doc.name


def on_entry_change(doc):
	"""Called from the shift entry's on_submit and on_cancel. Never stops the entry."""
	frappe.db.savepoint("pepl_oee")
	try:
		build_day(doc.workstation, doc.posting_date)
	except Exception:
		frappe.db.rollback(save_point="pepl_oee")
		frappe.log_error(title=f"PEPL: OEE not updated for {doc.workstation} on {doc.posting_date}")


def build_date(oee_date):
	"""Every machine with a submitted entry on that day, plus records that may need removing."""
	machines = set(
		frappe.get_all(
			SPR, filters={"posting_date": oee_date, "docstatus": 1}, pluck="workstation", distinct=True
		)
	)
	machines |= set(frappe.get_all(DOCTYPE, filters={"oee_date": oee_date}, pluck="workstation"))
	return [name for name in (build_day(m, oee_date) for m in sorted(machines)) if name]


def daily_oee():
	"""Scheduler (daily): yesterday's OEE for every machine."""
	return build_date(add_days(today(), -1))


@frappe.whitelist()
def rebuild_oee(from_date, to_date=None):
	"""Rebuild the records of a date range (e.g. after correcting entries). Production Manager only."""
	frappe.only_for(("System Manager", "Manufacturing Manager"))
	to_date = to_date or from_date
	days = date_diff(to_date, from_date)
	if days < 0 or days >= MAX_REBUILD_DAYS:
		frappe.throw(_("Choose a range of 1 to {0} days.").format(MAX_REBUILD_DAYS))
	built = []
	for offset in range(days + 1):
		built += build_date(add_days(from_date, offset))
	return {"records": len(built)}
