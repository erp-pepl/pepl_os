"""C3a-X8 - Job-work reconciliation: material sent to job workers, received back processed, returned unprocessed.

A job worker's store is a Warehouse with "Job Worker" (a Supplier) filled in. Material at the job worker is the
stock in that store, so every movement in and out of it is counted:

- Sent: any stock moved into the store (a "Send to Subcontractor" or a Material Transfer).
- Received after processing: stock leaving the store by a Subcontracting Receipt (ERPNext consumes the
  supplied material when the processed goods arrive), or by a Stock Entry marked "Received after Processing".
- Returned unprocessed: stock leaving the store by a Stock Entry marked "Returned Unprocessed" (a return
  entry is marked so by default).
- Adjusted: any other change (e.g. a stock count correction) - shown, so nobody hides a loss there.
Balance at the job worker = sent - received - returned - adjusted (the store's stock).

Each Stock Entry that touches a job worker's store says which movement it is (Job-Work Movement, set
automatically for material going out to the job worker; chosen by the user for material coming back). A
"Send to Subcontractor" must go to a job worker's store.

Age: the oldest quantity still outside (first in, first out) gives the days outside. Older than "Job-Work
Return Days" = Overdue; within "Job-Work GST Warning Days" of the one-year limit for inputs sent for job work
(CGST section 143) = GST limit near; a year or more = GST limit passed. Every morning the Production
notification owner gets one ToDo per job worker with overdue material (rule PRD-JW-OVERDUE); it closes by
itself once nothing is overdue.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, today

from pepl_os.common import alerts, params

JOB_WORKER_FIELD = "custom_job_worker"
MOVEMENT_FIELD = "custom_job_work_movement"
SENT, RECEIVED, RETURNED = "Sent to Job Worker", "Received after Processing", "Returned Unprocessed"
MOVEMENTS = (SENT, RECEIVED, RETURNED)
RETURN_DAYS_FIELD = "custom_job_work_return_days"
GST_WARNING_FIELD = "custom_job_work_gst_warning_days"
OWNER_FIELD = "custom_production_notification_owner"
OVERDUE_RULE = "PRD-JW-OVERDUE"
GST_LIMIT_DAYS = 365
CLEAR, OUTSIDE, OVERDUE, GST_NEAR, GST_PASSED = (
	"Clear",
	"Outside",
	"Overdue",
	"GST limit near",
	"GST limit passed",
)


def return_days():
	return max(cint(params.get(RETURN_DAYS_FIELD, 30)), 1)


def gst_warning_days():
	return max(cint(params.get(GST_WARNING_FIELD, 30)), 0)


def job_worker_stores(company=None, supplier=None):
	"""{warehouse: supplier} of the job workers' stores."""
	filters = {JOB_WORKER_FIELD: ["is", "set"], "is_group": 0}
	if company:
		filters["company"] = company
	if supplier:
		filters[JOB_WORKER_FIELD] = supplier
	return {
		w.name: w.get(JOB_WORKER_FIELD)
		for w in frappe.get_all("Warehouse", filters=filters, fields=["name", JOB_WORKER_FIELD])
	}


# Stock Entry rule ---------------------------------------------------------------------------------------


def validate_stock_entry(doc, method=None):
	"""doc_events: Stock Entry validate. Say what each job-work movement is."""
	stores = job_worker_stores(doc.company)
	rows = doc.get("items") or []
	into = [r for r in rows if r.t_warehouse and r.t_warehouse in stores]
	out = [r for r in rows if r.s_warehouse and r.s_warehouse in stores]
	if doc.purpose == "Send to Subcontractor" and rows and not into:
		frappe.throw(
			_(
				"Row {0}: {1} is not a job worker's store. Material sent for job work must go to the job worker's "
				"store: open the Warehouse and fill in 'Job Worker'."
			).format(rows[0].idx, frappe.bold(rows[0].t_warehouse or "-"))
		)
	if not into and not out:
		if doc.get(MOVEMENT_FIELD):
			doc.set(MOVEMENT_FIELD, "")
		return
	if into and out:
		frappe.throw(
			_(
				"One entry cannot both send material to a job worker and bring material back. Make two entries "
				"(rows {0} and {1})."
			).format(into[0].idx, out[0].idx)
		)
	if into:
		doc.set(MOVEMENT_FIELD, SENT)
		return
	if doc.get(MOVEMENT_FIELD) not in (RECEIVED, RETURNED):
		if doc.get("is_return"):
			doc.set(MOVEMENT_FIELD, RETURNED)
		else:
			frappe.throw(
				_(
					"Material is coming back from job worker {0}. Choose Job-Work Movement: '{1}' (processed) or "
					"'{2}'."
				).format(frappe.bold(stores[out[0].s_warehouse]), _(RECEIVED), _(RETURNED)),
				title=_("Job-Work Movement"),
			)


# Reconciliation -----------------------------------------------------------------------------------------


def _status(balance, days):
	if balance <= 0:
		return CLEAR
	if days >= GST_LIMIT_DAYS:
		return GST_PASSED
	if days >= GST_LIMIT_DAYS - gst_warning_days():
		return GST_NEAR
	if days > return_days():
		return OVERDUE
	return OUTSIDE


def reconcile(company=None, supplier=None, as_on=None):
	"""One row per job worker and item, as on a date."""
	as_on = getdate(as_on or today())
	stores = job_worker_stores(company, supplier)
	if not stores:
		return []
	entries = frappe.db.sql(
		"""
		select sle.warehouse, sle.item_code, sle.posting_date, sle.actual_qty, sle.voucher_type, sle.voucher_no,
			sle.valuation_rate, se.custom_job_work_movement as movement
		from `tabStock Ledger Entry` sle
		left join `tabStock Entry` se on sle.voucher_type = 'Stock Entry' and se.name = sle.voucher_no
		where sle.is_cancelled = 0 and sle.warehouse in %(stores)s and sle.posting_date <= %(as_on)s
		order by sle.posting_date, sle.posting_time, sle.creation
		""",
		{"stores": list(stores), "as_on": as_on},
		as_dict=True,
	)
	lines = {}
	for e in entries:
		key = (stores[e.warehouse], e.warehouse, e.item_code)
		line = lines.setdefault(
			key,
			{
				"job_worker": key[0],
				"warehouse": key[1],
				"item_code": key[2],
				"sent": 0.0,
				"received": 0.0,
				"returned": 0.0,
				"adjusted": 0.0,
				"sends": [],
				"rate": 0.0,
			},
		)
		qty = flt(e.actual_qty)
		line["rate"] = flt(e.valuation_rate) or line["rate"]
		if qty > 0 and e.voucher_type in ("Stock Entry", "Purchase Receipt", "Subcontracting Receipt"):
			line["sent"] += qty
			line["sends"].append([getdate(e.posting_date), qty])
		elif qty < 0 and e.voucher_type == "Subcontracting Receipt":
			line["received"] -= qty
		elif qty < 0 and e.voucher_type == "Stock Entry":
			line["received" if e.movement == RECEIVED else "returned"] -= qty
		else:
			line["adjusted"] -= qty  # stock count corrections and anything else
	result = []
	for line in lines.values():
		balance = line["sent"] - line["received"] - line["returned"] - line["adjusted"]
		back = line["received"] + line["returned"] + max(line["adjusted"], 0)
		first_out = None
		for day, qty in line.pop("sends"):
			if back >= qty:
				back -= qty
				continue
			first_out = day
			break
		days = date_diff(as_on, first_out) if first_out and balance > 0 else 0
		line.update(
			balance=round(balance, 6),
			value=round(max(balance, 0) * line.pop("rate"), 2),
			oldest_outside=first_out if balance > 0 else None,
			days_outside=days,
			status=_status(balance, days),
		)
		result.append(frappe._dict(line))
	return sorted(result, key=lambda r: (r.job_worker, r.item_code))


@frappe.whitelist()
def job_work_summary(supplier):
	"""For the Supplier form and the panels: what is outside with this job worker."""
	frappe.has_permission("Supplier", "read", doc=supplier, throw=True)
	rows = [r for r in reconcile(supplier=supplier) if r.balance > 0]
	return {"rows": rows, "overdue": [r for r in rows if r.status != OUTSIDE]}


def daily_job_work_alerts():
	"""Scheduler (daily): one ToDo per job worker with overdue material; closed once nothing is overdue."""
	late = {}
	for r in reconcile():
		if r.balance > 0 and r.status in (OVERDUE, GST_NEAR, GST_PASSED):
			late.setdefault(r.job_worker, []).append(r)
	for supplier, rows in late.items():
		parts = [
			_("{0}: {1} outside for {2} days ({3})").format(
				r.item_code, flt(r.balance, 3), r.days_outside, _(r.status)
			)
			for r in rows
		]
		gst = any(r.status in (GST_NEAR, GST_PASSED) for r in rows)
		alerts.raise_todo(
			OVERDUE_RULE,
			"Supplier",
			supplier,
			_("Job work overdue at {0}: {1}. Get it back or record what came back.").format(
				supplier, "; ".join(parts)
			),
			owner_field=OWNER_FIELD,
			priority="High" if gst else "Medium",
		)
	alerts.close_resolved(OVERDUE_RULE, "Supplier", list(late))
	return sorted(late)


@frappe.whitelist()
def run_job_work_alerts_now():
	"""Production Manager: run this morning's job-work check now. Returns the job workers with overdue material."""
	frappe.only_for(("System Manager", "Manufacturing Manager"))
	return daily_job_work_alerts()
