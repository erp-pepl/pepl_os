"""C3a-P3 - The Job-Work outstanding panel: what is still outside with a job worker, and how late it is.

Built on the job-work reconciliation (C3a-X8), so the panel and the report always agree.

- Supplier form (a job worker: a Supplier named as "Job Worker" on at least one store): one line per item still
  outside - quantity, since when, and whether it is within the return days, overdue, or near / past the GST
  one-year limit for inputs sent for job work; a headline with the count, the value and the worst status; a
  button to the Job-Work Reconciliation report for this job worker.
- Stock Entry form (an entry that sends material to, or brings it back from, a job worker's store): what is
  outside now for the items of the entry, and - on a draft bringing material back - a red line when it brings
  back more than is outside.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, formatdate, getdate, today

from pepl_os.pepl_production import job_work as jw
from pepl_os.pepl_production.job_order_panel import qty_text

MAX_LINES = 10
COLOUR = {jw.OUTSIDE: "green", jw.OVERDUE: "orange", jw.GST_NEAR: "red", jw.GST_PASSED: "red"}
RANK = {jw.CLEAR: 0, jw.OUTSIDE: 1, jw.OVERDUE: 2, jw.GST_NEAR: 3, jw.GST_PASSED: 4}


def _uom(item_code):
	return frappe.get_cached_value("Item", item_code, "stock_uom") or ""


def _money(value):
	return frappe.format(flt(value), {"fieldtype": "Currency"})


def line_text(r, show_store=False, as_on=None):
	"""One outstanding reconciliation row in plain words."""
	as_on = getdate(as_on or today())
	since = getdate(r.oldest_outside)
	due = getdate(add_days(since, jw.return_days()))
	limit = getdate(add_days(since, jw.GST_LIMIT_DAYS))
	days = cint(r.days_outside)
	head = _("{0}: {1} {2} outside").format(r.item_code, qty_text(r.balance), _uom(r.item_code))
	if show_store:
		head += " " + _("at {0}").format(r.warehouse)
	head += " " + (
		_("since {0} (sent today)").format(formatdate(since))
		if days == 0
		else _("since {0} ({1} days)").format(formatdate(since), days)
	)
	if r.status == jw.GST_PASSED:
		tail = _("GST one-year limit passed on {0}").format(formatdate(limit))
	elif r.status == jw.GST_NEAR:
		tail = _("GST one-year limit on {0}, {1} days left").format(
			formatdate(limit), date_diff(limit, as_on)
		)
	elif r.status == jw.OVERDUE:
		tail = _("{0} days overdue (due back by {1})").format(date_diff(as_on, due), formatdate(due))
	else:
		tail = _("due back by {0}").format(formatdate(due))
	return head + " - " + tail


def outstanding(supplier=None, items=None):
	"""Reconciliation rows still outside, worst first."""
	rows = [r for r in jw.reconcile(supplier=supplier) if flt(r.balance) > 0]
	if items is not None:
		rows = [r for r in rows if r.item_code in items]
	return sorted(rows, key=lambda r: (-RANK.get(r.status, 0), -cint(r.days_outside), r.item_code))


def _lines(rows, show_store=False):
	result = [
		{"text": line_text(r, show_store), "colour": COLOUR.get(r.status, "gray")} for r in rows[:MAX_LINES]
	]
	if len(rows) > MAX_LINES:
		result.append(
			{
				"text": _("... and {0} more: open the Job-Work Reconciliation report").format(
					len(rows) - MAX_LINES
				),
				"colour": "gray",
			}
		)
	return result


def supplier_rows(supplier):
	"""Panel rows for a job worker, or None when the supplier is not a job worker."""
	stores = jw.job_worker_stores(supplier=supplier)
	if not stores:
		return None
	rows = outstanding(supplier)
	if not rows:
		return [{"text": _("Nothing outside with this job worker."), "colour": "green"}]
	late = [r for r in rows if r.status != jw.OUTSIDE]
	worst = rows[0]
	headline = _("{0} item(s) outside, value {1}").format(len(rows), _money(sum(flt(r.value) for r in rows)))
	if late:
		headline += "; " + _("{0} overdue or near the GST limit").format(len(late))
	return [{"text": headline, "colour": COLOUR.get(worst.status, "gray")}, *_lines(rows, len(stores) > 1)]


def stock_entry_rows(doc):
	"""Panel rows for a Stock Entry that touches a job worker's store (empty when it does not)."""
	stores = jw.job_worker_stores(doc.company)
	touched = {}
	back = {}
	for row in doc.get("items") or []:
		for store, coming_back in ((row.t_warehouse, False), (row.s_warehouse, True)):
			if store and store in stores:
				touched.setdefault(stores[store], set()).add(row.item_code)
				if coming_back:
					key = (stores[store], store, row.item_code)
					back[key] = back.get(key, 0) + flt(row.transfer_qty or row.qty)
	result = []
	for supplier in sorted(touched):
		rows = outstanding(supplier, touched[supplier])
		when = _("after this entry") if doc.docstatus == 1 else _("before this entry")
		if rows:
			result.append(
				{
					"text": _("At job worker {0} now ({1}): {2} of these item(s) outside").format(
						supplier, when, len(rows)
					),
					"colour": COLOUR.get(rows[0].status, "gray"),
				}
			)
			result += _lines(rows, True)
		else:
			result.append(
				{
					"text": _("At job worker {0} now ({1}): none of these items is outside").format(
						supplier, when
					),
					"colour": "green",
				}
			)
		if doc.docstatus == 0:
			balance = {(r.job_worker, r.warehouse, r.item_code): flt(r.balance) for r in rows}
			for key, qty in sorted(back.items()):
				if key[0] == supplier and qty > balance.get(key, 0) + 1e-9:
					result.append(
						{
							"text": _(
								"{0}: this entry brings back {1} {2} from {3}, but only {4} is outside"
							).format(
								key[2], qty_text(qty), _uom(key[2]), key[1], qty_text(balance.get(key, 0))
							),
							"colour": "red",
						}
					)
	return result


@frappe.whitelist()
def get_supplier_job_work_panel(supplier):
	"""For the Supplier form: {job_worker, rows}."""
	frappe.has_permission("Supplier", "read", doc=supplier, throw=True)
	rows = supplier_rows(supplier)
	return {"job_worker": rows is not None, "rows": rows or []}


@frappe.whitelist()
def get_stock_entry_job_work_panel(stock_entry):
	"""For the Stock Entry form: {rows} (empty when the entry does not touch a job worker's store)."""
	doc = frappe.get_doc("Stock Entry", stock_entry)
	doc.check_permission("read")
	return {"rows": stock_entry_rows(doc)}
