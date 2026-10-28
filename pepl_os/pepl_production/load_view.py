"""C3a-P2 - The Production Plan load view: each machine's booked hours against its available hours.

For every machine (Workstation) the plan uses, over the days the plan uses it:
- this plan: its rows not yet on a Job Order, laid out exactly as the double-booking check (C3a-X6) lays them out,
  plus the open Job Orders already made from this plan;
- already booked: open Job Orders from elsewhere and the rows of other open Production Plans, counted only for
  the part that falls on those days;
- available: hours a day x jobs it can run at once (Production Capacity) x working days. Hours a day = the
  machine's own Working Hours in ERPNext; when none are set, the planned hours of all active PEPL Shifts.
  Working days leave out the holidays of the machine's Holiday List (else the company's default one).

Load % = (this plan + already booked) / available. Over 100 % is red (more work than hours), from
"Load View: Warning at % of Machine Hours" (System Parameters -> Production, 85) orange, else green. A machine
with no working hours anywhere shows its booked hours in grey.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, formatdate, get_datetime, getdate

from pepl_os.common import params
from pepl_os.pepl_production import machine_booking as mb
from pepl_os.pepl_production.job_order_panel import qty_text

WARNING_FIELD = "custom_load_warning_percent"
DEFAULT_WARNING = 85


def warning_percent():
	value = params.get(WARNING_FIELD, DEFAULT_WARNING)
	return flt(value) if value not in (None, "") else DEFAULT_WARNING


def hours_a_day(workstation):
	"""(hours, where they came from) for one machine and one job slot."""
	own = flt(frappe.db.get_value("Workstation", workstation, "total_working_hours"))
	if own > 0:
		return own, _("machine's working hours")
	minutes = sum(
		cint(m) for m in frappe.get_all("PEPL Shift", filters={"is_active": 1}, pluck="planned_minutes")
	)
	if minutes > 0:
		return minutes / 60.0, _("active shifts")
	return 0.0, ""


def holiday_list(workstation, company=None):
	own = frappe.db.get_value("Workstation", workstation, "holiday_list")
	if own:
		return own
	return frappe.db.get_value("Company", company, "default_holiday_list") if company else None


def working_days(first, last, holidays=None):
	"""Days from first to last (both included), less the holidays of the list (a half day counts half)."""
	first, last = getdate(first), getdate(last)
	days = (last - first).days + 1
	if days <= 0:
		return 0
	if holidays:
		off = frappe.get_all(
			"Holiday",
			filters={
				"parent": holidays,
				"parenttype": "Holiday List",
				"holiday_date": ["between", [first, last]],
			},
			pluck="is_half_day",
		)
		days -= sum(0.5 if cint(half) else 1 for half in off)
	return max(days, 0)


def _minutes(booking, window_start=None, window_end=None):
	start = booking["start"] if window_start is None else max(booking["start"], window_start)
	end = booking["end"] if window_end is None else min(booking["end"], window_end)
	return max((end - start).total_seconds() / 60.0, 0)


def _own_job_orders(plan_name):
	if not plan_name:
		return []
	return frappe.get_all(
		"Work Order",
		filters={"production_plan": plan_name, "docstatus": 1, "status": ["in", mb.OPEN_JOB_ORDER]},
		pluck="name",
	)


def machine_loads(plan):
	"""[{workstation, first, last, days, hours_a_day, source, capacity, own_hours, held_hours, available_hours,
	percent}] for every machine the plan uses, busiest first."""
	gap = mb.gap_minutes()
	own = mb.plan_bookings(plan, gap)
	own_orders = set(_own_job_orders(plan.name))
	machines = {b["workstation"] for b in own}
	if own_orders:
		machines |= set(
			frappe.get_all(
				"Work Order Operation",
				filters={
					"parent": ["in", list(own_orders)],
					"parenttype": "Work Order",
					"workstation": ["is", "set"],
				},
				pluck="workstation",
				distinct=True,
			)
		)
	if not machines:
		return []
	held = []
	for booking in mb.job_order_bookings(machines, gap=gap):
		(own if booking["reference"] in own_orders else held).append(booking)
	held += mb.other_plan_bookings(machines, plan.name, gap)

	loads = []
	for machine in sorted(machines):
		mine = [b for b in own if b["workstation"] == machine]
		if not mine:
			continue
		first = min(b["start"] for b in mine).date()
		# a booking ending exactly at midnight does not use the next day
		last = max(b["end"] - datetime.timedelta(seconds=1) for b in mine).date()
		window_start = get_datetime(first)
		window_end = get_datetime(add_days(last, 1))
		own_minutes = sum(_minutes(b) for b in mine)
		held_minutes = sum(_minutes(b, window_start, window_end) for b in held if b["workstation"] == machine)
		per_day, source = hours_a_day(machine)
		slots = mb.capacity(machine)
		days = working_days(first, last, holiday_list(machine, plan.get("company")))
		available = per_day * slots * days
		booked = (own_minutes + held_minutes) / 60.0
		loads.append(
			frappe._dict(
				workstation=machine,
				first=first,
				last=last,
				days=days,
				hours_a_day=round(per_day, 2),
				source=source,
				capacity=slots,
				own_hours=round(own_minutes / 60.0, 2),
				held_hours=round(held_minutes / 60.0, 2),
				available_hours=round(available, 2),
				percent=round(100.0 * booked / available) if available else None,
				no_hours_reason=""
				if available
				else (
					_("every day is a holiday on the Holiday List")
					if per_day
					else _("no working hours on the machine and no active shift")
				),
			)
		)
	loads.sort(key=lambda x: (x.percent is None, -(x.percent or 0), x.workstation))
	return loads


def _hours(value):
	return qty_text(round(flt(value), 1)) + " h"


def _days_text(load):
	if load.first == load.last:
		return formatdate(load.first)
	return _("{0} to {1}").format(formatdate(load.first), formatdate(load.last))


def panel_rows(plan):
	plan = frappe.get_doc("Production Plan", plan) if isinstance(plan, str) else plan
	loads = machine_loads(plan)
	if not loads:
		return [
			{
				"text": _(
					"No machine time in this plan yet: each row needs a BOM with operations and a Planned Start."
				),
				"colour": "gray",
			}
		]
	warn = warning_percent()
	rows = []
	over = [x for x in loads if x.percent is not None and x.percent > 100]
	near = [x for x in loads if x.percent is not None and warn <= x.percent <= 100]
	if over:
		headline = _("{0} of {1} machine(s) overloaded; busiest {2} at {3}%").format(
			len(over), len(loads), over[0].workstation, over[0].percent
		)
		colour = "red"
	elif near:
		headline = _("{0} of {1} machine(s) at {2}% or more; busiest {3} at {4}%").format(
			len(near), len(loads), qty_text(warn), near[0].workstation, near[0].percent
		)
		colour = "orange"
	elif any(x.percent is not None for x in loads):
		measured = len([x for x in loads if x.percent is not None])
		headline = _("{0} machine(s), all below {1}% of their hours").format(measured, qty_text(warn))
		colour = "green"
	else:
		headline = _("{0} machine(s): no working hours to compare the load with").format(len(loads))
		colour = "gray"
	rows.append({"text": headline, "colour": colour})
	for x in loads:
		booked = _("this plan {0}").format(_hours(x.own_hours))
		if x.held_hours:
			booked += " + " + _("already booked {0}").format(_hours(x.held_hours))
			booked += " = " + _hours(flt(x.own_hours) + flt(x.held_hours))
		if x.percent is None:
			rows.append(
				{
					"text": _("{0}, {1}: {2} ({3})").format(
						x.workstation, _days_text(x), booked, x.no_hours_reason
					),
					"colour": "gray",
				}
			)
			continue
		per_day = _("{0} a day").format(_hours(x.hours_a_day))
		if x.capacity > 1:
			per_day += " x " + _("{0} jobs at once").format(x.capacity)
		text = _("{0}, {1}: {2} of {3} ({4} working day(s), {5} from the {6}) - {7}%").format(
			x.workstation,
			_days_text(x),
			booked,
			_hours(x.available_hours),
			qty_text(x.days),
			per_day,
			x.source,
			x.percent,
		)
		rows.append(
			{
				"text": text,
				"colour": "red" if x.percent > 100 else ("orange" if x.percent >= warn else "green"),
			}
		)
	if plan.get(mb.CLASHES_FIELD):
		rows.append(
			{
				"text": _(
					"Machines double-booked at the same time: see Machine Double-Bookings on this plan"
				),
				"colour": "red",
			}
		)
	return rows


@frappe.whitelist()
def get_production_plan_load(production_plan):
	"""For the Production Plan form."""
	frappe.has_permission("Production Plan", "read", doc=production_plan, throw=True)
	return {"rows": panel_rows(production_plan)}
