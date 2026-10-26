"""C3a-X10 - The Daily Stand-up: yesterday on the shop floor, on one page, every morning.

Each morning (07:45) a PEPL Daily Standup record is built for the day before and e-mailed to the members of the
pepl_sales "Standup Email Group". It holds:

1. Shop floor yesterday - each machine's Daily OEE (A, P, Q, OEE, good, rejected, breakdowns), lowest OEE first.
2. Top stops yesterday - downtime minutes by Downtime Category from the submitted shift entries.
3. Machines without a shift entry - machines that had an entry in the last 30 days but none yesterday.
4. Job Orders at delivery risk - open Job Orders due within "Stand-up: Days Ahead for Delivery Risk" (default 3)
   and not finished; overdue ones first.
5. Job work overdue - from the job-work reconciliation (Overdue / GST limit).

The record keeps the headline numbers too, so the Command Centre (Phase 4) can read them. Building again for
the same day updates the record. Phase 5 (B7) turns this into an exception-only stand-up.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, escape_html, flt, getdate, now_datetime, today

from pepl_os.common import params
from pepl_os.pepl_production import job_work, oee

DOCTYPE = "PEPL Daily Standup"
SPR = "PEPL Shift Production Entry"
GROUP_FIELD = "standup_email_group"  # owned by pepl_sales
RISK_DAYS_FIELD = "custom_standup_risk_days"
ACTIVE_DAYS = 30
OPEN_JOB_ORDER = ("Not Started", "In Process")


def risk_days():
	return max(cint(params.get(RISK_DAYS_FIELD, 3)), 0)


def recipients():
	group = params.get(GROUP_FIELD)
	if not group:
		return []
	return sorted(
		set(
			frappe.get_all(
				"Email Group Member", filters={"email_group": group, "unsubscribed": 0}, pluck="email"
			)
		)
	)


# The sections ------------------------------------------------------------------------------------------


def machine_days(day):
	return frappe.get_all(
		oee.DOCTYPE,
		filters={"oee_date": day},
		fields=[
			"workstation",
			"availability",
			"performance",
			"quality",
			"oee",
			"below_target",
			"good_qty",
			"rejected_qty",
			"breakdown_count",
			"unplanned_stop_minutes",
			"planned_stop_minutes",
			"run_minutes",
		],
		order_by="oee asc, workstation asc",
	)


def top_stops(day, limit=5):
	return frappe.db.sql(
		f"""select d.downtime_category, d.stop_type, sum(d.minutes) as minutes, count(*) as stops
		from `tabPEPL SPR Downtime` d join `tab{SPR}` s on s.name = d.parent
		where s.docstatus = 1 and s.posting_date = %s
		group by d.downtime_category, d.stop_type order by minutes desc limit {cint(limit)}""",
		day,
		as_dict=True,
	)


def machines_without_entry(day):
	active = set(
		frappe.get_all(
			SPR,
			filters={
				"docstatus": 1,
				"posting_date": ["between", [add_days(day, -ACTIVE_DAYS), add_days(day, -1)]],
			},
			pluck="workstation",
			distinct=True,
		)
	)
	reported = set(
		frappe.get_all(SPR, filters={"docstatus": 1, "posting_date": day}, pluck="workstation", distinct=True)
	)
	return sorted(active - reported)


def job_orders_at_risk(day):
	horizon = add_days(today(), risk_days())
	rows = frappe.get_all(
		"Work Order",
		filters={
			"docstatus": 1,
			"status": ["in", OPEN_JOB_ORDER],
			"expected_delivery_date": ["<=", horizon],
		},
		fields=[
			"name",
			"production_item",
			"qty",
			"produced_qty",
			"expected_delivery_date",
			"sales_order",
			"status",
		],
		order_by="expected_delivery_date asc, name asc",
	)
	result = []
	for r in rows:
		if flt(r.produced_qty) >= flt(r.qty):
			continue
		r.overdue = getdate(r.expected_delivery_date) < getdate(today())
		r.pending = flt(r.qty) - flt(r.produced_qty)
		result.append(r)
	return result


def job_work_overdue():
	return [r for r in job_work.reconcile() if r.balance > 0 and r.status != job_work.OUTSIDE]


# The page ---------------------------------------------------------------------------------------------


def _table(headers, rows):
	head = "".join(
		f"<th style='text-align:left;padding:4px 8px;border-bottom:1px solid #ccc'>{h}</th>" for h in headers
	)
	body = "".join(
		"<tr>"
		+ "".join(f"<td style='padding:4px 8px;border-bottom:1px solid #eee'>{c}</td>" for c in row)
		+ "</tr>"
		for row in rows
	)
	return f"<table style='border-collapse:collapse;font-size:13px'><tr>{head}</tr>{body}</table>"


def _section(title, content, empty):
	return f"<h4 style='margin:16px 0 6px'>{escape_html(title)}</h4>" + (
		content or f"<p>{escape_html(empty)}</p>"
	)


def render(day, machines, stops, missing, risk, outside):
	e = escape_html
	parts = [
		f"<h3>{e(_('Daily Stand-up for {0}').format(frappe.format(getdate(day), {'fieldtype': 'Date'})))}</h3>"
	]
	parts.append(
		_section(
			_("1. Shop floor yesterday"),
			_table(
				[_("Machine"), "A %", "P %", "Q %", "OEE %", _("Good"), _("Rejected"), _("Breakdowns")],
				[
					[
						e(m.workstation) + (" &#9888;" if m.below_target else ""),
						flt(m.availability, 1),
						flt(m.performance, 1),
						flt(m.quality, 1),
						f"<b>{flt(m.oee, 1)}</b>",
						flt(m.good_qty, 3),
						flt(m.rejected_qty, 3),
						cint(m.breakdown_count),
					]
					for m in machines
				],
			)
			if machines
			else "",
			_("No machine has a submitted shift entry for this day."),
		)
	)
	parts.append(
		_section(
			_("2. Top stops"),
			_table(
				[_("Stop"), _("Type"), _("Minutes"), _("Times")],
				[
					[e(s.downtime_category), e(s.stop_type or ""), cint(s.minutes), cint(s.stops)]
					for s in stops
				],
			)
			if stops
			else "",
			_("No stops recorded."),
		)
	)
	parts.append(
		_section(
			_("3. Machines without a shift entry"),
			"<p>" + ", ".join(e(m) for m in missing) + "</p>" if missing else "",
			_("Every machine that worked in the last 30 days has its entry."),
		)
	)
	parts.append(
		_section(
			_("4. Job Orders at delivery risk (due within {0} days)").format(risk_days()),
			_table(
				[_("Job Order"), _("Item"), _("Pending"), _("Due"), _("Sales Order")],
				[
					[
						e(r.name)
						+ (" <b style='color:#c00'>" + e(_("overdue")) + "</b>" if r.overdue else ""),
						e(r.production_item),
						flt(r.pending, 3),
						frappe.format(r.expected_delivery_date, {"fieldtype": "Date"}),
						e(r.sales_order or ""),
					]
					for r in risk
				],
			)
			if risk
			else "",
			_("No Job Order is due soon or late."),
		)
	)
	parts.append(
		_section(
			_("5. Job work overdue"),
			_table(
				[_("Job Worker"), _("Item"), _("Outside"), _("Days"), _("Status")],
				[
					[e(r.job_worker), e(r.item_code), flt(r.balance, 3), cint(r.days_outside), e(_(r.status))]
					for r in outside
				],
			)
			if outside
			else "",
			_("Nothing overdue at job workers."),
		)
	)
	return "".join(parts)


def build(day=None):
	"""Create or update the stand-up for a day (default yesterday). Returns the record."""
	day = getdate(day or add_days(today(), -1))
	machines = machine_days(day)
	stops = top_stops(day)
	missing = machines_without_entry(day)
	risk = job_orders_at_risk(day)
	outside = job_work_overdue()
	good = sum(flt(m.good_qty) for m in machines)
	rejected = sum(flt(m.rejected_qty) for m in machines)
	name = frappe.db.get_value(DOCTYPE, {"standup_date": day})
	doc = frappe.get_doc(DOCTYPE, name) if name else frappe.new_doc(DOCTYPE)
	doc.update(
		{
			"standup_date": day,
			"machines_reported": len(machines),
			"machines_below_target": sum(1 for m in machines if m.below_target),
			"average_oee": round(sum(flt(m.oee) for m in machines) / len(machines), 2) if machines else 0,
			"good_qty": good,
			"rejected_qty": rejected,
			"rejection_percent": round(100.0 * rejected / (good + rejected), 2) if good + rejected else 0,
			"downtime_minutes": sum(cint(s.minutes) for s in top_stops(day, limit=1000)),
			"top_stop": stops[0].downtime_category if stops else "",
			"breakdowns": sum(cint(m.breakdown_count) for m in machines),
			"machines_without_entry": len(missing),
			"job_orders_at_risk": len(risk),
			"job_orders_overdue": sum(1 for r in risk if r.overdue),
			"job_work_overdue": len(outside),
			"summary": render(day, machines, stops, missing, risk, outside),
			"built_on": now_datetime(),
		}
	)
	doc.flags.ignore_permissions = True
	doc.save()
	return doc


def send(doc):
	"""E-mail the stand-up to the Standup Email Group. Returns the recipients."""
	to = recipients()
	if not to:
		return []
	try:
		frappe.sendmail(
			recipients=to,
			subject=_("PEPL Daily Stand-up - {0}").format(
				frappe.format(getdate(doc.standup_date), {"fieldtype": "Date"})
			),
			message=doc.summary,
			reference_doctype=DOCTYPE,
			reference_name=doc.name,
		)
	except frappe.OutgoingEmailError:
		# No outgoing e-mail account on the site yet: the stand-up is still on the record.
		frappe.clear_last_message()
		frappe.log_error(title="PEPL: Daily Stand-up not e-mailed (no outgoing e-mail account)")
		doc.db_set("emailed_to", _("Not e-mailed: set up an outgoing Email Account"), update_modified=False)
		return []
	doc.db_set({"emailed_to": ", ".join(to), "emailed_on": now_datetime()}, update_modified=False)
	return to


def daily_standup():
	"""Scheduler (07:45 every day): yesterday's stand-up, built and e-mailed."""
	doc = build()
	send(doc)
	return doc.name


@frappe.whitelist()
def build_standup_now(day=None, email=0):
	"""Production Manager: build (and optionally e-mail) the stand-up for a day now."""
	frappe.only_for(("System Manager", "Manufacturing Manager"))
	doc = build(day)
	sent = send(doc) if cint(email) else []
	return {"name": doc.name, "emailed_to": sent}
