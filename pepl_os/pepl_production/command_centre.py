"""C3a-CC - Production Command Centre: the five cards and the downtime-by-cause report behind one of them.

Cards (each method takes the card's `filters` and returns {"value", "fieldtype", "route", "route_options"}, so
clicking the card opens the list or report that explains the number - the C2-23 pattern):
- Yesterday's OEE: all machines together, each Daily OEE weighted by its planned production time (a machine
  that ran a whole shift counts more than one that ran an hour). Opens yesterday's Daily OEE list.
- Jobs at Delivery Risk: open Job Orders not finished and due within "Stand-up: Days Ahead for Delivery Risk"
  (or late) - the same list the morning stand-up shows. Opens those Job Orders.
- Open Job-Work Quantity Outside: what is still at job workers (C3a-X8 reconciliation). Opens the report.
- Rejection % (7 days): rejected / (good + rejected) on the shift entries of the last 7 days. Opens them.
- Top Downtime Cause (7 days): a cause is a name, which a number card cannot show, so it is a card-sized block:
  the category with the most stopped minutes in the last 7 days, its minutes and share; it opens the report
  "PEPL Downtime by Cause".
"Last 7 days" = the 7 shift dates before today (today's shifts are still running).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from pepl_os.pepl_production import job_work, standup

SPR = "PEPL Shift Production Entry"
OEE = "PEPL OEE Daily"
DAYS = 7
BLOCK = "PEPL Top Downtime Cause"


def _card(value, fieldtype, route, route_options=None):
	return {"value": flt(value), "fieldtype": fieldtype, "route": route, "route_options": route_options or {}}


def window(days=DAYS):
	"""(first, last) shift dates of the last `days` days, today left out."""
	return getdate(add_days(today(), -days)), getdate(add_days(today(), -1))


@frappe.whitelist()
def yesterdays_oee(filters=None):
	"""OEE of all machines yesterday, weighted by planned production time."""
	day = add_days(today(), -1)
	rows = frappe.get_all(OEE, filters={"oee_date": day}, fields=["oee", "planned_production_minutes"])
	weight = sum(cint(r.planned_production_minutes) for r in rows)
	value = (
		sum(flt(r.oee) * cint(r.planned_production_minutes) for r in rows) / weight
		if weight
		else (sum(flt(r.oee) for r in rows) / len(rows) if rows else 0)
	)
	return _card(round(value, 1), "Percent", ["List", OEE], {"oee_date": day})


@frappe.whitelist()
def jobs_at_delivery_risk(filters=None):
	"""Open, unfinished Job Orders due within the stand-up's risk days, or late."""
	rows = standup.job_orders_at_risk(today())
	return _card(
		len(rows),
		"Int",
		["List", "Work Order"],
		{"name": ["in", [r.name for r in rows] or [""]]},
	)


@frappe.whitelist()
def job_work_outside(filters=None):
	"""Quantity still at job workers (stock units, all items)."""
	value = round(sum(flt(r.balance) for r in job_work.reconcile() if flt(r.balance) > 0), 3)
	# a whole number is shown as one (25, not 25.000)
	fieldtype = "Int" if value == int(value) else "Float"
	return _card(value, fieldtype, ["query-report", "PEPL Job-Work Reconciliation"], {"outstanding_only": 1})


@frappe.whitelist()
def rejection_percent(filters=None):
	"""Rejected / (good + rejected) on the submitted shift entries of the last 7 days."""
	first, last = window()
	row = frappe.db.sql(
		f"""select coalesce(sum(total_good_qty), 0), coalesce(sum(total_rejected_qty), 0) from `tab{SPR}`
		where docstatus = 1 and posting_date between %s and %s""",
		(first, last),
	)[0]
	good, rejected = flt(row[0]), flt(row[1])
	value = 100.0 * rejected / (good + rejected) if good + rejected else 0
	return _card(
		round(value, 1),
		"Percent",
		["List", SPR],
		{"posting_date": ["between", [str(first), str(last)]], "docstatus": 1},
	)


def downtime_by_cause(days=DAYS):
	"""[{downtime_category, stop_type, is_breakdown, minutes, stops, share}] of the last `days` days, most first."""
	first, last = window(cint(days) or DAYS)
	rows = frappe.db.sql(
		f"""select d.downtime_category, d.stop_type, max(d.is_breakdown) as is_breakdown,
			sum(d.minutes) as minutes, count(*) as stops, count(distinct s.workstation) as machines
		from `tabPEPL SPR Downtime` d join `tab{SPR}` s on s.name = d.parent
		where s.docstatus = 1 and s.posting_date between %s and %s
		group by d.downtime_category, d.stop_type order by minutes desc, d.downtime_category asc""",
		(first, last),
		as_dict=True,
	)
	total = sum(cint(r.minutes) for r in rows)
	for r in rows:
		r.minutes = cint(r.minutes)
		r.share = round(100.0 * r.minutes / total, 1) if total else 0
	return rows


@frappe.whitelist()
def top_downtime_cause(days=DAYS):
	"""For the card-sized block: the cause with the most stopped minutes in the last 7 days."""
	rows = downtime_by_cause(days)
	if not rows:
		return {"cause": "", "text": _("No stops recorded in the last {0} days").format(cint(days) or DAYS)}
	top = rows[0]
	return {
		"cause": top.downtime_category,
		"minutes": top.minutes,
		"share": top.share,
		"stop_type": top.stop_type,
		"is_breakdown": cint(top.is_breakdown),
		"text": _("{0} min, {1}% of all stopped time ({2} stop(s) on {3} machine(s))").format(
			top.minutes, top.share, top.stops, top.machines
		),
	}


BLOCK_HTML = """<div class="pepl-top-downtime number-widget-box" style="cursor: pointer; padding: 14px 16px;">
	<div class="widget-head"><div class="widget-title" style="font-weight: 600;">…</div></div>
	<div class="pepl-top-cause" style="font-size: 20px; font-weight: 600; margin: 6px 0;"></div>
	<div class="pepl-top-detail text-muted" style="font-size: 12px;"></div>
</div>"""
BLOCK_SCRIPT = """const box = root_element.querySelector(".pepl-top-downtime");
box.querySelector(".widget-title").textContent = __("Top Downtime Cause (7 days)");
box.addEventListener("click", () => frappe.set_route("query-report", "PEPL Downtime by Cause"));
frappe.call("pepl_os.pepl_production.command_centre.top_downtime_cause").then((r) => {
	const d = r.message || {};
	box.querySelector(".pepl-top-cause").textContent = d.cause || "-";
	box.querySelector(".pepl-top-cause").style.color = d.cause ? (d.is_breakdown ? "var(--red-600)" : (d.stop_type === "Unplanned" ? "var(--orange-600)" : "")) : "";
	box.querySelector(".pepl-top-detail").textContent = d.text || "";
});"""


def ensure_top_downtime_block():
	"""Install / migrate: the "Top Downtime Cause (7 days)" card-sized block of the Production Command Centre."""
	values = {"html": BLOCK_HTML, "script": BLOCK_SCRIPT, "style": "", "private": 0}
	if frappe.db.exists("Custom HTML Block", BLOCK):
		doc = frappe.get_doc("Custom HTML Block", BLOCK)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Custom HTML Block", **values})
		doc.insert(ignore_permissions=True, set_name=BLOCK)
	return doc.name
