"""CR1 - Booking PEPL's older Sales Orders and Sales Invoices (dates before the ERPNext go-live).

PEPL books its pending Sales Orders of earlier years (2022 onwards) with their real dates, then the Sales Invoices
already raised against them (already in Tally) with their real invoice dates.

1. Dates: ERPNext accepts a date only inside a Fiscal Year. create_fiscal_years() adds the missing earlier years.
2. System Parameters → Accounts & GST → "Historic Booking: Documents Dated Before" (empty = off). A document dated
   before it is a historic booking:
   - Sales Order: ticked "Historic Booking"; on submit it drafts no Material Request (C2-07) and no Job Orders
     (C3a-X5), and gets no default LD clause (C3a-X11) - the work is long done. LD can still be entered by hand.
     PEPL's trackers (PSD, Document) are still made.
   - Sales Invoice: ticked "Historic Booking"; needs the Tally Invoice No. on submit (one invoice per number, for the
     Tally mirror); its e-Invoice and e-Waybill are "Not Applicable" (they were made, or not, when it was raised);
     with Update Stock, an item with no stock history in that store needs a valuation rate, so it is named in plain
     words before ERPNext refuses. The Payment Tracker is still made (pepl_sales).
3. Negative stock while PEPL books is ERPNext's own Stock Settings → Allow Negative Stock (switched by the consultant).
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_years, cint, cstr, formatdate, getdate

from pepl_os.common import params

CUTOFF_FIELD = "custom_historic_booking_before"
FLAG = "custom_historic_booking"
TALLY_NO = "custom_tally_invoice_no"
NOT_APPLICABLE = "Not Applicable"
SETUP_ROLES = ("System Manager", "Accounts Manager")


def cutoff():
	"""The Historic Booking date, or None when the rule is off."""
	value = params.get(CUTOFF_FIELD)
	return getdate(value) if value else None


def is_historic(date):
	limit = cutoff()
	return bool(limit and date and getdate(date) < limit)


# ---------------- Sales Order ----------------
def validate_sales_order(doc, method=None):
	"""doc_events: Sales Order validate."""
	doc.set(FLAG, 1 if is_historic(doc.transaction_date) else 0)


def is_historic_order(doc):
	"""For the Sales Order submit handlers (Material Request, Job Orders)."""
	return bool(cint(doc.get(FLAG)) or is_historic(doc.get("transaction_date")))


def on_sales_order_submit(doc, method=None):
	if is_historic_order(doc):
		frappe.msgprint(
			_(
				"Historic order (dated before {0}): no Material Request and no Job Orders were drafted. "
				"For a quantity still to be made, use Create → Work Order on this order."
			).format(formatdate(cutoff())),
			indicator="blue",
			alert=True,
		)


# ---------------- Sales Invoice ----------------
def validate_sales_invoice(doc, method=None):
	"""doc_events: Sales Invoice validate."""
	doc.set(FLAG, 1 if is_historic(doc.posting_date) else 0)
	number = cstr(doc.get(TALLY_NO)).strip()
	doc.set(TALLY_NO, number or None)
	if not number:
		return
	other = frappe.db.get_value(
		"Sales Invoice", {TALLY_NO: number, "docstatus": ["<", 2], "name": ["!=", doc.name]}, "name"
	)
	if other:
		frappe.throw(
			_("Tally Invoice No. {0} is already on Sales Invoice {1}.").format(frappe.bold(number), other),
			title=_("Tally Invoice No. used twice"),
		)


def before_submit_sales_invoice(doc, method=None):
	"""doc_events: Sales Invoice before_submit (runs after every validate, before India Compliance's on_submit)."""
	if not cint(doc.get(FLAG)):
		return
	if not doc.get(TALLY_NO):
		frappe.throw(
			_(
				"This invoice is dated before {0} (historic booking). Enter its Tally Invoice No. before submitting."
			).format(formatdate(cutoff())),
			title=_("Tally Invoice No. needed"),
		)
	for field in ("einvoice_status", "e_waybill_status"):
		if doc.meta.has_field(field):
			doc.set(field, NOT_APPLICABLE)
	if cint(doc.get("update_stock")):
		missing = items_without_valuation(doc)
		if missing:
			frappe.throw(
				_(
					"These items have no stock history in their store and no rate to value them at: {0}. "
					"Enter the Valuation Rate on each Item (Item → Inventory → Valuation Rate, the cost per unit in "
					"Tally), then submit again."
				).format(", ".join(frappe.bold(code) for code in missing)),
				title=_("Valuation rate needed"),
			)


def items_without_valuation(doc):
	"""Items of an Update Stock invoice that ERPNext could not value (its own fallbacks, in its order)."""
	missing = []
	for row in doc.items:
		code = row.item_code
		if not code or code in missing or cint(row.get("allow_zero_valuation_rate")):
			continue
		if not frappe.get_cached_value("Item", code, "is_stock_item"):
			continue
		if frappe.db.exists(
			"Stock Ledger Entry", {"item_code": code, "warehouse": row.warehouse, "is_cancelled": 0}
		):
			continue
		rates = frappe.db.get_value("Item", code, ["valuation_rate", "standard_rate"], as_dict=True) or {}
		if rates.get("valuation_rate") or rates.get("standard_rate"):
			continue
		if frappe.db.exists("Item Price", {"item_code": code, "buying": 1}):
			continue
		missing.append(code)
	return missing


# ---------------- Fiscal Years ----------------
@frappe.whitelist()
def create_fiscal_years(from_date):
	"""Create every missing Fiscal Year back to the one holding from_date (same companies as the earliest year).

	Years follow the earliest existing year's start (1 April for PEPL), one year before another. Safe to run again.
	System Console: frappe.call("pepl_os.pepl_accounts.historic.create_fiscal_years", from_date="2022-01-01")
	"""
	frappe.only_for(SETUP_ROLES)
	from_date = getdate(from_date)
	years = frappe.get_all(
		"Fiscal Year", fields=["name", "year_start_date"], order_by="year_start_date asc", limit=1
	)
	if not years:
		frappe.throw(
			_("There is no Fiscal Year yet. Create the current one first (Accounting → Fiscal Year).")
		)
	first = years[0]
	companies = [row.company for row in frappe.get_doc("Fiscal Year", first.name).companies]
	created = []
	start = getdate(first.year_start_date)
	while start > from_date:
		start = add_years(start, -1)
		end = add_days(add_years(start, 1), -1)
		if frappe.db.exists("Fiscal Year", {"year_start_date": start}):
			continue
		label = str(start.year) if (start.month, start.day) == (1, 1) else f"{start.year}-{start.year + 1}"
		if frappe.db.exists("Fiscal Year", label):
			label = f"{label} ({formatdate(start)})"
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": label,
				"year_start_date": start,
				"year_end_date": end,
				"companies": [{"company": company} for company in companies],
			}
		).insert()
		created.append(label)
	return {"created": created, "earliest_start": str(start)}
