"""C3b-CC - Quality Command Centre: the six cards, each opening what explains its number.

Number cards (each method takes the card's `filters` and returns {"value", "fieldtype", "route", "route_options"} -
the C2-23 pattern):
- CAPAs Overdue for Verification: CAPAs Awaiting Verification whose effectiveness check day has passed (C3b-B3).
- Instruments Due Within 30 Days: instruments in use (Active) due for calibration within 30 days, overdue ones
  included. (Never calibrated instruments have no due date; the shortcut "Never calibrated" lists them.)
- First-Pass Yield (7 days): good pieces / (good + rejected) on the submitted shift entries of the 7 shift dates
  before today, in %.
- Customer Rejections (30 days): NCRs with source Customer (returns, complaints) raised in the last 30 days, not
  cancelled.
- Cost of Quality (month): this month's total of the report PEPL Cost of Quality (C3b-B2), in rupees.
One card-sized block, because a number card shows one number:
- Open NCRs by Severity: Critical · Major · Minor of the NCRs Open or Under Review; each opens its list.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from pepl_os.pepl_production import command_centre as production
from pepl_os.pepl_quality import calibration, capa, coq, ncr

SPR = "PEPL Shift Production Entry"
DUE_DAYS = 30
CUSTOMER_DAYS = 30
OPEN_NCR = (ncr.OPEN, ncr.UNDER_REVIEW)
BLOCK = "PEPL Open NCRs by Severity"


def _card(value, fieldtype, route, route_options=None):
	return {"value": flt(value), "fieldtype": fieldtype, "route": route, "route_options": route_options or {}}


@frappe.whitelist()
def capas_overdue_for_verification(filters=None):
	"""CAPAs awaiting their effectiveness check, the check day passed."""
	filters_ = {"status": capa.AWAITING, "verification_due_on": ["<", today()]}
	return _card(frappe.db.count(capa.CAPA, filters_), "Int", ["List", capa.CAPA], filters_)


@frappe.whitelist()
def instruments_due_within_30_days(filters=None):
	"""Active instruments due for calibration on or before today + 30 days (overdue included)."""
	until = str(add_days(today(), DUE_DAYS))
	filters_ = {"status": calibration.ACTIVE, "calibration_due_on": ["<=", until]}
	return _card(
		frappe.db.count(calibration.INSTRUMENT, filters_), "Int", ["List", calibration.INSTRUMENT], filters_
	)


def first_pass_yield_value(days=7):
	"""(good, rejected, yield %) on the submitted shift entries of the window (today left out)."""
	first, last = production.window(days)
	row = frappe.db.sql(
		f"""select coalesce(sum(total_good_qty), 0), coalesce(sum(total_rejected_qty), 0) from `tab{SPR}`
		where docstatus = 1 and posting_date between %s and %s""",
		(first, last),
	)[0]
	good, rejected = flt(row[0]), flt(row[1])
	value = 100.0 * good / (good + rejected) if good + rejected else 0
	return good, rejected, round(value, 1)


@frappe.whitelist()
def first_pass_yield(filters=None):
	"""Good / (good + rejected) on the shift entries of the last 7 days, in %."""
	first, last = production.window()
	return _card(
		first_pass_yield_value()[2],
		"Percent",
		["List", SPR],
		{"posting_date": ["between", [str(first), str(last)]], "docstatus": 1},
	)


@frappe.whitelist()
def customer_rejections(filters=None):
	"""NCRs from customers raised in the last 30 days (not cancelled)."""
	filters_ = {
		"source": ncr.CUSTOMER,
		"status": ["!=", ncr.CANCELLED],
		"raised_on": [">=", str(add_days(today(), -CUSTOMER_DAYS))],
	}
	return _card(frappe.db.count(ncr.NCR, filters_), "Int", ["List", ncr.NCR], filters_)


@frappe.whitelist()
def cost_of_quality_month(filters=None):
	"""This month's Cost of Quality (rupees)."""
	day = getdate(today())
	return _card(
		coq.month_total(day),
		"Currency",
		["query-report", "PEPL Cost of Quality"],
		{"from_date": str(day.replace(day=1)), "group_by": "Item"},
	)


@frappe.whitelist()
def open_ncrs_by_severity():
	"""For the card-sized block: open NCRs (Open / Under Review) per severity."""
	counts = {s: 0 for s in ncr.SEVERITIES}
	for severity, n in frappe.db.sql(
		f"select severity, count(*) from `tab{ncr.NCR}` where status in %s group by severity", (OPEN_NCR,)
	):
		if severity in counts:
			counts[severity] = int(n)
	return {
		"total": sum(counts.values()),
		"severities": [{"severity": s, "count": counts[s]} for s in reversed(ncr.SEVERITIES)],
		"text": _("Open or Under Review"),
	}


BLOCK_HTML = """<div class="pepl-open-ncrs number-widget-box" style="padding: 14px 16px;">
	<div class="widget-head"><div class="widget-title" style="font-weight: 600;">…</div></div>
	<div class="pepl-ncr-counts" style="display: flex; gap: 22px; margin: 6px 0;"></div>
	<div class="pepl-ncr-detail text-muted" style="font-size: 12px;"></div>
</div>"""
BLOCK_SCRIPT = """const box = root_element.querySelector(".pepl-open-ncrs");
box.querySelector(".widget-title").textContent = __("Open NCRs by Severity");
const colours = { Critical: "var(--red-600)", Major: "var(--orange-600)", Minor: "var(--gray-700)" };
frappe.call("pepl_os.pepl_quality.command_centre.open_ncrs_by_severity").then((r) => {
	const d = r.message || { severities: [] };
	const counts = box.querySelector(".pepl-ncr-counts");
	counts.innerHTML = "";
	d.severities.forEach((s) => {
		const el = document.createElement("div");
		el.style.cursor = "pointer";
		el.innerHTML = `<div style="font-size: 20px; font-weight: 600; color: ${s.count ? colours[s.severity] : ""}">${s.count}</div>
			<div class="text-muted" style="font-size: 12px;">${__(s.severity)}</div>`;
		el.addEventListener("click", () =>
			frappe.set_route("List", "PEPL NCR", { severity: s.severity, status: ["in", ["Open", "Under Review"]] })
		);
		counts.appendChild(el);
	});
	box.querySelector(".pepl-ncr-detail").textContent = __("{0} NCR(s) {1}", [d.total || 0, d.text || ""]);
});"""


def ensure_open_ncr_block():
	"""Install / migrate: the "Open NCRs by Severity" card-sized block of the Quality Command Centre."""
	values = {"html": BLOCK_HTML, "script": BLOCK_SCRIPT, "style": "", "private": 0}
	if frappe.db.exists("Custom HTML Block", BLOCK):
		doc = frappe.get_doc("Custom HTML Block", BLOCK)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Custom HTML Block", **values})
		doc.insert(ignore_permissions=True, set_name=BLOCK)
	return doc.name
