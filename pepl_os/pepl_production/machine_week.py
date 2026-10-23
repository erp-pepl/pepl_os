"""C3a-X4 - Weekly MTBF, MTTR and CPC (cost per component) per machine, from the submitted Shift Production Entries.

One PEPL Machine Week record per machine (Workstation) and week (Monday to Sunday, by shift date):

- MTBF (mean time between failures) = run hours ÷ breakdowns. MTTR (mean time to repair) = breakdown minutes ÷
  breakdowns. A breakdown is a downtime row whose Downtime Category is marked "Machine Breakdown". A week
  without a breakdown shows no MTBF / MTTR and says so.
- CPC: the week's cost of the machine and what it made.
  machine cost = run hours x the Machine-Hour Rate of the machine's group (System Parameters → Production
  Costing; the machine's own Hour Rate when its group has none); consumables = the value of the Material
  Issues posted by the week's shift entries; material = BOM raw-material cost a piece x pieces made (good and
  rejected); overhead = Overhead (%) on all three. Machine and consumables are shared between the items made
  in proportion to their run minutes; each item's CPC = its total cost ÷ its good pieces (rejects are paid for
  by the good ones). The machine's own CPC is its conversion cost (machine + consumables + overhead) ÷ good
  pieces.

Built when a shift entry is submitted or cancelled, and every Monday for the week before (a safety net).
Never stops the shift entry: a failure goes to the Error Log.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate, now_datetime, today

from pepl_os.common import params

DOCTYPE = "PEPL Machine Week"
SPR = "PEPL Shift Production Entry"
SYSTEM_PARAMETERS = "PEPL System Parameters"
RATES_FIELD = "custom_machine_hour_rates"
OVERHEAD_FIELD = "custom_overhead_percent"
MAX_REBUILD_DAYS = 371


def week_start(day):
	day = getdate(day)
	return add_days(day, -day.weekday())


def record_name(workstation, monday):
	return frappe.db.get_value(DOCTYPE, {"workstation": workstation, "week_start": getdate(monday)}, "name")


def machine_rate(workstation):
	"""(rate per hour, where it came from) for the machine."""
	group = frappe.db.get_value("Workstation", workstation, "workstation_type")
	if group:
		for row in frappe.get_all(
			"PEPL Machine Hour Rate",
			filters={"parent": SYSTEM_PARAMETERS, "parentfield": RATES_FIELD},
			fields=["machine_group", "rate_per_hour"],
		):
			if (row.machine_group or "").strip().lower() == group.strip().lower():
				return flt(row.rate_per_hour), _("Machine-Hour Rates: {0}").format(row.machine_group.strip())
	own = flt(frappe.db.get_value("Workstation", workstation, "hour_rate"))
	if own:
		return own, _("Machine's own Hour Rate")
	return 0.0, ""


def _material_per_piece(bom_no):
	if not bom_no:
		return 0.0
	bom = frappe.db.get_value("BOM", bom_no, ["raw_material_cost", "quantity"], as_dict=True)
	return flt(bom.raw_material_cost) / flt(bom.quantity) if bom and flt(bom.quantity) else 0.0


def compute(workstation, monday):
	"""The week's figures for one machine, or None when it has no submitted entry that week."""
	monday = getdate(monday)
	sunday = add_days(monday, 6)
	entries = frappe.get_all(
		SPR,
		filters={"workstation": workstation, "posting_date": ["between", [monday, sunday]], "docstatus": 1},
		fields=["name", "company", "workstation_type"],
	)
	if not entries:
		return None
	names = [e.name for e in entries]
	blocks = frappe.get_all(
		"PEPL SPR Production",
		filters={"parent": ["in", names], "parenttype": SPR},
		fields=["job_card", "production_item", "minutes", "good_qty", "rejected_qty"],
	)
	breakdowns = frappe.get_all(
		"PEPL SPR Downtime",
		filters={"parent": ["in", names], "parenttype": SPR, "is_breakdown": 1},
		fields=["minutes"],
	)
	run = sum(cint(b.minutes) for b in blocks)
	count = len(breakdowns)
	down = sum(cint(b.minutes) for b in breakdowns)

	rate, rate_source = machine_rate(workstation)
	overhead_percent = flt(params.get(OVERHEAD_FIELD, 0))
	machine_cost = run / 60.0 * rate
	consumables_cost = sum(
		flt(v)
		for v in frappe.get_all(
			"Stock Entry",
			filters={"custom_shift_production_entry": ["in", names], "docstatus": 1},
			pluck="total_outgoing_value",
		)
	)

	cards = list({b.job_card for b in blocks if b.job_card})
	boms = (
		{
			c.name: c.bom_no
			for c in frappe.get_all("Job Card", filters={"name": ["in", cards]}, fields=["name", "bom_no"])
		}
		if cards
		else {}
	)
	items = {}
	for b in blocks:
		item = b.production_item or frappe.db.get_value("Job Card", b.job_card, "production_item")
		row = items.setdefault(
			item,
			{"item_code": item, "good_qty": 0.0, "rejected_qty": 0.0, "run_minutes": 0, "material_cost": 0.0},
		)
		row["good_qty"] += flt(b.good_qty)
		row["rejected_qty"] += flt(b.rejected_qty)
		row["run_minutes"] += cint(b.minutes)
		row["material_cost"] += _material_per_piece(boms.get(b.job_card)) * (
			flt(b.good_qty) + flt(b.rejected_qty)
		)

	item_rows = []
	for row in sorted(items.values(), key=lambda r: r["item_code"] or ""):
		share = row["run_minutes"] / run if run else 0
		row["machine_cost"] = machine_cost * share
		row["consumables_cost"] = consumables_cost * share
		base = row["material_cost"] + row["machine_cost"] + row["consumables_cost"]
		row["overhead_cost"] = base * overhead_percent / 100.0
		row["total_cost"] = base + row["overhead_cost"]
		row["cost_per_piece"] = row["total_cost"] / row["good_qty"] if row["good_qty"] else 0.0
		for key in (
			"material_cost",
			"machine_cost",
			"consumables_cost",
			"overhead_cost",
			"total_cost",
			"cost_per_piece",
		):
			row[key] = round(row[key], 2)
		item_rows.append(row)

	good = sum(flt(b.good_qty) for b in blocks)
	conversion = (machine_cost + consumables_cost) * (1 + overhead_percent / 100.0)
	notes = []
	if not count:
		notes.append(_("No breakdown this week: MTBF and MTTR are not calculated."))
	if run and not rate:
		notes.append(
			_("No machine-hour rate for this machine: set it in System Parameters → Machine-Hour Rates.")
		)
	return {
		"workstation": workstation,
		"week_start": monday,
		"week_end": getdate(sunday),
		"workstation_type": entries[0].workstation_type
		or frappe.db.get_value("Workstation", workstation, "workstation_type"),
		"company": entries[0].company,
		"entries": len(entries),
		"run_minutes": run,
		"breakdown_count": count,
		"breakdown_minutes": down,
		"mtbf_hours": round(run / 60.0 / count, 2) if count else 0,
		"mttr_minutes": round(down / count, 2) if count else 0,
		"good_qty": good,
		"rejected_qty": sum(flt(b.rejected_qty) for b in blocks),
		"rate_per_hour": rate,
		"rate_source": rate_source,
		"overhead_percent": overhead_percent,
		"machine_cost": round(machine_cost, 2),
		"consumables_cost": round(consumables_cost, 2),
		"conversion_cost": round(conversion, 2),
		"cpc": round(conversion / good, 2) if good else 0,
		"items": item_rows,
		"notes": "\n".join(notes),
		"computed_on": now_datetime(),
	}


def build_week(workstation, any_day):
	"""Create, update or remove the record of one machine and week. Returns its name or None."""
	monday = week_start(any_day)
	values = compute(workstation, monday)
	existing = record_name(workstation, monday)
	if values is None:
		if existing:
			frappe.delete_doc(DOCTYPE, existing, ignore_permissions=True, force=True)
		return None
	doc = frappe.get_doc(DOCTYPE, existing) if existing else frappe.new_doc(DOCTYPE)
	items = values.pop("items")
	doc.update(values)
	doc.set("items", items)
	doc.flags.ignore_permissions = True
	doc.save()
	return doc.name


def on_entry_change(doc):
	"""Called from the shift entry's on_submit and on_cancel. Never stops the entry."""
	frappe.db.savepoint("pepl_machine_week")
	try:
		build_week(doc.workstation, doc.posting_date)
	except Exception:
		frappe.db.rollback(save_point="pepl_machine_week")
		frappe.log_error(title=f"PEPL: machine week not updated for {doc.workstation} ({doc.posting_date})")


def build_weeks(monday):
	monday = week_start(monday)
	sunday = add_days(monday, 6)
	machines = set(
		frappe.get_all(
			SPR,
			filters={"posting_date": ["between", [monday, sunday]], "docstatus": 1},
			pluck="workstation",
			distinct=True,
		)
	)
	machines |= set(frappe.get_all(DOCTYPE, filters={"week_start": monday}, pluck="workstation"))
	return [name for name in (build_week(m, monday) for m in sorted(machines)) if name]


def weekly_machine_figures():
	"""Scheduler (Monday): the week just ended, for every machine."""
	return build_weeks(add_days(week_start(today()), -7))


@frappe.whitelist()
def rebuild_machine_weeks(from_date, to_date=None):
	"""Rebuild the weeks touching a date range (e.g. after a rate change). Production Manager only."""
	frappe.only_for(("System Manager", "Manufacturing Manager"))
	to_date = to_date or from_date
	days = date_diff(to_date, from_date)
	if days < 0 or days >= MAX_REBUILD_DAYS:
		frappe.throw(_("Choose a range of 1 to {0} days.").format(MAX_REBUILD_DAYS))
	built, monday = [], week_start(from_date)
	while getdate(monday) <= getdate(to_date):
		built += build_weeks(monday)
		monday = add_days(monday, 7)
	return {"records": len(built)}
