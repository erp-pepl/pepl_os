"""C3b-Q6 - Vendor scorecard: each supplier's quality score and the composite score with the delivery score.

Over the Vendor Score Period (System Parameters > Purchase, "Vendor Score Period (Days)", the same as the delivery
score of C2-14):
  * Quality score = incoming QC Inspections of the supplier submitted as Accepted ÷ all its submitted incoming QC
    Inspections (lots), in %. No inspection in the period = no quality score yet (the screens show "-").
  * NCRs in the period: the supplier's NCRs that are not cancelled (shown with the score; Quality reads them).
  * Composite score = Delivery score x "Vendor Score Weight: Delivery %" + Quality score x "Vendor Score Weight:
    Quality %" (the two weights add up to 100). When one of the two scores is missing, the composite is the other one.

Written onto the Supplier every morning (job "Vendor quality and composite scores", in PEPL Job Run), at once when an
incoming QC Inspection of the supplier is submitted or cancelled, and on "Run now" (Quality / Purchase Manager). The
RFQ supplier list and the Quotation Comparison show delivery, quality and composite.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from pepl_os.common import params
from pepl_os.common.jobs import tracked_job
from pepl_os.pepl_purchase import letdown

QI = "Quality Inspection"
NCR = "PEPL NCR"
QUALITY_FIELD = "custom_quality_score"
LOTS_FIELD = "custom_quality_scored_lots"
NCRS_FIELD = "custom_supplier_ncrs"
COMPOSITE_FIELD = "custom_composite_score"
UPDATED_FIELD = "custom_scores_updated_on"
DELIVERY_WEIGHT_FIELD = "custom_vendor_weight_delivery"
QUALITY_WEIGHT_FIELD = "custom_vendor_weight_quality"
RUN_ROLES = ("System Manager", "Quality Manager", "Purchase Manager")


def weights():
	"""(delivery, quality) weights as fractions that add up to 1."""
	delivery = params.get_float(DELIVERY_WEIGHT_FIELD, 50)
	quality = params.get_float(QUALITY_WEIGHT_FIELD, 50)
	total = delivery + quality
	if total <= 0:
		return 0.5, 0.5
	return delivery / total, quality / total


def validate_params(doc):
	errors = []
	delivery, quality = doc.get(DELIVERY_WEIGHT_FIELD), doc.get(QUALITY_WEIGHT_FIELD)
	if delivery in (None, "") and quality in (None, ""):
		return errors
	if not 0 <= flt(delivery) <= 100 or not 0 <= flt(quality) <= 100:
		errors.append(_("Vendor Score Weights must each be between 0 and 100."))
	elif abs(flt(delivery) + flt(quality) - 100) > 0.001:
		errors.append(_("Vendor Score Weights for Delivery and Quality must add up to 100."))
	return errors


def _period(as_of=None):
	as_of = getdate(as_of or today())
	return add_days(as_of, -letdown.lookback_days()), as_of


def quality_score(supplier, as_of=None):
	"""(score %, lots inspected). Score is None when no incoming inspection was submitted in the period."""
	since, until = _period(as_of)
	rows = frappe.db.sql(
		f"""select status from `tab{QI}`
		where custom_supplier = %s and inspection_type = 'Incoming' and docstatus = 1
		and report_date > %s and report_date <= %s""",
		(supplier, since, until),
	)
	lots = len(rows)
	if not lots:
		return None, 0
	accepted = sum(1 for (status,) in rows if status == "Accepted")
	return round(accepted * 100.0 / lots, 1), lots


def supplier_ncrs(supplier, as_of=None):
	since, until = _period(as_of)
	return frappe.db.count(
		NCR,
		{
			"supplier": supplier,
			"status": ["!=", "Cancelled"],
			"raised_on": ["between", [add_days(since, 1), until]],
		},
	)


def composite(delivery, quality):
	"""Weighted composite of the scores that exist; None when neither exists."""
	if delivery is None and quality is None:
		return None
	if delivery is None:
		return quality
	if quality is None:
		return delivery
	w_delivery, w_quality = weights()
	return round(delivery * w_delivery + quality * w_quality, 1)


def update_supplier(supplier, as_of=None):
	"""Write the quality score, lots, NCRs and composite onto the Supplier. Returns the values written."""
	q_score, lots = quality_score(supplier, as_of)
	d_score, d_lines = letdown.delivery_score(supplier, as_of)
	values = {
		QUALITY_FIELD: q_score or 0,
		LOTS_FIELD: lots,
		NCRS_FIELD: supplier_ncrs(supplier, as_of),
		COMPOSITE_FIELD: composite(d_score if d_lines else None, q_score if lots else None) or 0,
		UPDATED_FIELD: getdate(as_of or today()),
	}
	frappe.db.set_value("Supplier", supplier, values, update_modified=False)
	return values


def suppliers_to_score():
	names = set(letdown.suppliers_to_score())
	names |= set(
		frappe.get_all(QI, filters={"custom_supplier": ["is", "set"]}, pluck="custom_supplier", distinct=True)
	)
	names |= set(frappe.get_all(NCR, filters={"supplier": ["is", "set"]}, pluck="supplier", distinct=True))
	return sorted(n for n in names if n)


def refresh_scores(as_of=None):
	count = 0
	for supplier in suppliers_to_score():
		if not frappe.db.exists("Supplier", supplier):
			continue
		try:
			update_supplier(supplier, as_of)
			count += 1
		except Exception:
			frappe.log_error(title=f"PEPL: quality score not updated for {supplier}")
	return count


@tracked_job("Vendor quality and composite scores")
def daily_vendor_scores():
	count = refresh_scores()
	return {"records_touched": count, "message": f"{count} supplier quality / composite score(s) updated"}


@frappe.whitelist()
def run_vendor_scores_now():
	"""The daily scoring, now (Quality Manager / Purchase Manager / System Manager)."""
	frappe.only_for(RUN_ROLES)
	return {"records_touched": refresh_scores()}


def on_inspection_change(doc, method=None):
	"""doc_events: Quality Inspection on_submit / on_cancel. An incoming lot updates its supplier's scores at once.

	Returns nothing: Frappe merges what the handlers of one event return, and a dict after another handler's text
	stopped the submit (CI #73, fixed 0.67.1)."""
	supplier = doc.get("custom_supplier")
	if doc.inspection_type != "Incoming" or not supplier or not frappe.db.exists("Supplier", supplier):
		return
	frappe.db.savepoint("pepl_vendor_score")
	try:
		update_supplier(supplier)
	except Exception:
		frappe.db.rollback(save_point="pepl_vendor_score")
		frappe.log_error(title=f"PEPL: quality score not updated for {supplier}")


def card_scores(supplier_row):
	"""(delivery, quality, composite) for the screens: None where there is nothing to score yet."""
	delivery = (
		supplier_row.get("custom_delivery_score")
		if cint(supplier_row.get("custom_delivery_scored_lines"))
		else None
	)
	quality = supplier_row.get(QUALITY_FIELD) if cint(supplier_row.get(LOTS_FIELD)) else None
	both = delivery is not None or quality is not None
	return delivery, quality, (supplier_row.get(COMPOSITE_FIELD) if both else None)
