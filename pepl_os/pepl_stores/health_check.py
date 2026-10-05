"""Cycle 2 health check - the brief's Phase 1 audit of the Cycle 2 chain, run on live data.

The C2-01 audit (audit.py) checked the data before Cycle 2 was built. This one checks that the
Cycle 2 automation is doing its job on live records, as the brief's Phase 1 asks:

  1  every submitted PO has a Purchase Tracker, and the tracker's quantities equal the PO's
  2  every Purchase Receipt line has a Receipt Log row; heat numbers and test certificates captured
  3  suppliers used on POs are approved; approvals with expired documents
  4  Quotation Comparison usage and override reasons
  5  every scheduled job actually runs (the Cycle 1 lesson)
  6  valuation per stock class; receipt rate carried into valuation
  7  Outstanding Vendor Bills against the ledger; MSME bills flagged and dated correctly

Read-only: nothing is written. System Manager downloads it from PEPL System Health
("Download Cycle 2 health check"). Every row is a finding with empty Owner and Fix columns;
a clean system gives zero findings on every sheet.
"""

import frappe
from frappe.utils import add_days, cint, flt, getdate, today

from pepl_os.pepl_stores import audit, stock_tree

DEFAULT_SINCE = audit.DEFAULT_SINCE
QTY_TOLERANCE = 0.001
RATE_TOLERANCE_PERCENT = 1.0
MONEY_TOLERANCE = 1.0
MIN_REASON = 10

PO = "Purchase Order"
PR = "Purchase Receipt"
PI = "Purchase Invoice"
TRACKER = "PEPL Purchase Tracker"
TRACKER_LINE = "PEPL Purchase Tracker Line"
RECEIPT_LOG = "PEPL Receipt Log"
APPROVAL = "PEPL Supplier Approval"
OVERRIDE_LOG = "PEPL Override Log"
APPROVED_STATES = ("Approved", "Conditionally Approved")
GATE_RULE = "SUP-NOT-APPROVED"


def _exists(doctype):
	return bool(frappe.db.exists("DocType", doctype))


# 1 Purchase Trackers ----------------------------------------------------------------------


def _trackers(since):
	rows = []
	if not _exists(TRACKER):
		return [{"check": "PEPL Purchase Tracker DocType missing", "document": "", "detail": ""}]
	for po in frappe.db.sql(
		"""select po.name, po.supplier from `tabPurchase Order` po
		left join `tabPEPL Purchase Tracker` t on t.purchase_order = po.name
		where po.docstatus = 1 and po.transaction_date >= %s and t.name is null
		order by po.name""",
		since,
		as_dict=True,
	):
		rows.append(
			{
				"check": "Submitted PO without a Purchase Tracker",
				"document": po.name,
				"detail": f"Supplier {po.supplier}",
			}
		)
	for line in frappe.db.sql(
		"""select t.name as tracker, t.purchase_order, l.idx, l.item_code,
			l.ordered_qty, l.received_qty, poi.qty as po_qty, poi.received_qty as po_received
		from `tabPEPL Purchase Tracker Line` l
		join `tabPEPL Purchase Tracker` t on t.name = l.parent
		join `tabPurchase Order Item` poi on poi.name = l.po_item
		join `tabPurchase Order` po on po.name = poi.parent
		where po.docstatus = 1 and po.transaction_date >= %s
			and (abs(l.ordered_qty - poi.qty) > %s or abs(l.received_qty - poi.received_qty) > %s)
		order by t.name, l.idx""",
		(since, QTY_TOLERANCE, QTY_TOLERANCE),
		as_dict=True,
	):
		rows.append(
			{
				"check": "Tracker quantity differs from the PO",
				"document": line.tracker,
				"detail": f"{line.purchase_order} row {line.idx} {line.item_code}: tracker ordered "
				f"{flt(line.ordered_qty)} / received {flt(line.received_qty)}, PO ordered "
				f"{flt(line.po_qty)} / received {flt(line.po_received)}",
			}
		)
	for t in frappe.get_all(
		TRACKER,
		filters={"status": ["not in", ("Completed", "Cancelled")]},
		fields=["name", "purchase_order", "last_computed_on"],
	):
		if not t.last_computed_on or getdate(t.last_computed_on) < getdate(add_days(today(), -1)):
			rows.append(
				{
					"check": "Open tracker not recomputed in the last day",
					"document": t.name,
					"detail": f"{t.purchase_order}: last computed {t.last_computed_on or 'never'}",
				}
			)
	return rows


# 2 Receipt Log and heat numbers ------------------------------------------------------------


def _receipt_log(since):
	rows = []
	if not _exists(RECEIPT_LOG):
		return [{"check": "PEPL Receipt Log DocType missing", "document": "", "item": "", "detail": ""}]
	for line in frappe.db.sql(
		"""select pri.parent, pri.idx, pri.item_code from `tabPurchase Receipt Item` pri
		join `tabPurchase Receipt` pr on pr.name = pri.parent
		left join `tabPEPL Receipt Log` rl on rl.pr_item = pri.name
		where pr.docstatus = 1 and ifnull(pr.is_return, 0) = 0 and pr.posting_date >= %s and rl.name is null
		order by pri.parent, pri.idx""",
		since,
		as_dict=True,
	):
		rows.append(
			{
				"check": "Receipt line without a Receipt Log row",
				"document": line.parent,
				"item": line.item_code,
				"detail": f"Row {line.idx}",
			}
		)
	tracked_field = (
		"custom_heat_tracked" if frappe.get_meta("Item").has_field("custom_heat_tracked") else None
	)
	for log in frappe.get_all(
		RECEIPT_LOG,
		filters={"status": "Active", "received_on": [">=", since]},
		fields=["name", "purchase_receipt", "item_code", "heat_number", "batch_no", "test_certificate"],
	):
		if not tracked_field or not cint(frappe.get_cached_value("Item", log.item_code, tracked_field)):
			continue
		missing = []
		if not (log.heat_number or log.batch_no):
			missing.append("heat number")
		if not log.test_certificate:
			missing.append("test certificate")
		if missing:
			rows.append(
				{
					"check": "Heat-tracked receipt missing " + " and ".join(missing),
					"document": log.purchase_receipt,
					"item": log.item_code,
					"detail": log.name,
				}
			)
	return rows


# 3 Supplier approval -----------------------------------------------------------------------


def _supplier_approval(since):
	rows = []
	for s in frappe.db.sql(
		"""select po.supplier, count(*) as po_count, max(s.custom_approval_state) as state
		from `tabPurchase Order` po join `tabSupplier` s on s.name = po.supplier
		where po.docstatus = 1 and po.transaction_date >= %s
		group by po.supplier order by po.supplier""",
		since,
		as_dict=True,
	):
		if s.state in APPROVED_STATES:
			continue
		overrides = 0
		if _exists(OVERRIDE_LOG):
			pos = frappe.get_all(
				PO,
				filters={"docstatus": 1, "supplier": s.supplier, "transaction_date": [">=", since]},
				pluck="name",
			)
			overrides = frappe.db.count(
				OVERRIDE_LOG, {"rule_code": GATE_RULE, "reference_doctype": PO, "reference_name": ["in", pos]}
			)
		rows.append(
			{
				"check": "Supplier not approved, a reason logged on every PO"
				if s.po_count <= overrides
				else "Supplier on submitted POs is not approved",
				"supplier": s.supplier,
				"detail": f"State {s.state or 'none'}; {s.po_count} PO(s) since {since}; {overrides} override reason(s) logged",
			}
		)
	if _exists(APPROVAL):
		for a in frappe.get_all(
			APPROVAL,
			filters={"state": ["in", APPROVED_STATES], "earliest_expiry": ["<", today()]},
			fields=["name", "supplier", "earliest_expiry", "state"],
		):
			rows.append(
				{
					"check": "Approved supplier with an expired document",
					"supplier": a.supplier,
					"detail": f"{a.name}: earliest expiry {a.earliest_expiry}, state still {a.state}",
				}
			)
	return rows


# 4 Quotation Comparison and overrides ------------------------------------------------------


def _comparison_and_overrides(since):
	rows = []
	field = (
		"custom_quotation_comparison"
		if frappe.get_meta(PO).has_field("custom_quotation_comparison")
		else None
	)
	if field:
		total = frappe.db.count(PO, {"docstatus": 1, "transaction_date": [">=", since]})
		without = frappe.get_all(
			PO,
			filters={"docstatus": 1, "transaction_date": [">=", since], field: ["is", "not set"]},
			fields=["name", "supplier", "grand_total"],
			order_by="name",
		)
		rows.append(
			{
				"check": "Usage",
				"reference": "",
				"detail": f"{total - len(without)} of {total} submitted POs since {since} came from a Quotation Comparison",
			}
		)
		for po in without:
			rows.append(
				{
					"check": "PO raised without a Quotation Comparison",
					"reference": po.name,
					"detail": f"{po.supplier}, {flt(po.grand_total, 2)}",
				}
			)
	if _exists(OVERRIDE_LOG):
		for r in frappe.db.sql(
			"""select rule_code, count(*) as n from `tabPEPL Override Log`
			where creation >= %s group by rule_code order by n desc""",
			since,
			as_dict=True,
		):
			rows.append(
				{"check": "Overrides logged", "reference": r.rule_code, "detail": f"{r.n} since {since}"}
			)
		for o in frappe.get_all(
			OVERRIDE_LOG,
			filters={"creation": [">=", since]},
			fields=["name", "rule_code", "reference_doctype", "reference_name", "reason"],
		):
			if len((o.reason or "").strip()) < MIN_REASON:
				rows.append(
					{
						"check": "Override without a proper reason",
						"reference": f"{o.reference_doctype} {o.reference_name}",
						"detail": f"{o.name} ({o.rule_code}): '{o.reason or ''}'",
					}
				)
	return rows


# 5 Scheduled jobs --------------------------------------------------------------------------


def _jobs():
	from pepl_os.pepl_governance.page.pepl_system_health.pepl_system_health import get_pepl_jobs, job_health

	rows = []
	for frequency, method in get_pepl_jobs():
		h = job_health(frequency, method)
		if h["status"] == "OK":
			continue
		# A new monthly job before its first 1st of the month is information, not a finding.
		rows.append(
			{
				"check": f"Job {h['status']}",
				"job": method,
				"detail": f"{frequency}; last success {h['last_success'] or 'never'}; "
				f"last failure {h['last_failure'] or 'none'}",
			}
		)
	return rows


# 6 Valuation per stock class ---------------------------------------------------------------


def _valuation(since):
	rows = []
	by_class = {}
	for b in frappe.db.sql(
		"""select b.item_code, i.item_group, i.is_customer_provided_item, sum(b.stock_value) as value,
			sum(b.actual_qty) as qty
		from `tabBin` b join `tabItem` i on i.name = b.item_code
		group by b.item_code, i.item_group, i.is_customer_provided_item""",
		as_dict=True,
	):
		stock_class = stock_tree.stock_class_of(b.item_group) or "Outside the classes"
		by_class[stock_class] = by_class.get(stock_class, 0.0) + flt(b.value)
		if (stock_class == stock_tree.CSM or cint(b.is_customer_provided_item)) and abs(
			flt(b.value)
		) > MONEY_TOLERANCE:
			rows.append(
				{
					"check": "Customer material carrying value",
					"item": b.item_code,
					"detail": f"Stock value {flt(b.value, 2)} (must be zero)",
				}
			)
		if stock_class == stock_tree.CAPITAL and flt(b.qty):
			rows.append(
				{
					"check": "Capital Equipment item held in stock",
					"item": b.item_code,
					"detail": f"Qty {flt(b.qty)}, value {flt(b.value, 2)}",
				}
			)
	for stock_class in sorted(by_class):
		rows.append(
			{
				"check": "Stock value by class",
				"item": stock_class,
				"detail": f"{flt(by_class[stock_class], 2)}",
			}
		)
	for line in frappe.db.sql(
		"""select pri.parent, pri.idx, pri.item_code, pri.valuation_rate, pri.base_net_rate,
			pri.conversion_factor, pri.landed_cost_voucher_amount, pri.item_tax_amount
		from `tabPurchase Receipt Item` pri join `tabPurchase Receipt` pr on pr.name = pri.parent
		where pr.docstatus = 1 and ifnull(pr.is_return, 0) = 0 and pr.posting_date >= %s
			and ifnull(pri.is_free_item, 0) = 0 and pri.base_net_rate > 0""",
		since,
		as_dict=True,
	):
		if frappe.get_cached_value("Item", line.item_code, "is_customer_provided_item"):
			continue
		per_stock_unit = flt(line.base_net_rate) / (flt(line.conversion_factor) or 1)
		if flt(line.landed_cost_voucher_amount) or flt(line.item_tax_amount):
			continue  # landed cost or a valuation tax (e.g. freight) legitimately lifts the valuation
		diff = abs(flt(line.valuation_rate) - per_stock_unit)
		if per_stock_unit and diff / per_stock_unit * 100 > RATE_TOLERANCE_PERCENT:
			rows.append(
				{
					"check": "Receipt rate not carried into valuation",
					"item": line.item_code,
					"detail": f"{line.parent} row {line.idx}: purchase rate {flt(per_stock_unit, 2)} "
					f"per stock unit, valuation rate {flt(line.valuation_rate, 2)}",
				}
			)
	return rows


# 7 Vendor bill reports against the source ---------------------------------------------------


def _reports(company):
	from pepl_os.pepl_purchase.payments import msme_basis_date, msme_days, outstanding_vendor_bills

	rows = []
	report = {
		r.supplier: flt(r.total) for r in outstanding_vendor_bills({"company": company} if company else None)
	}
	ledger = {
		r.party: flt(r.balance)
		for r in frappe.db.sql(
			f"""select party, sum(credit_in_account_currency - debit_in_account_currency) as balance
			from `tabGL Entry` where party_type = 'Supplier' and is_cancelled = 0
			{"and company = %(company)s" if company else ""}
			group by party""",
			{"company": company},
			as_dict=True,
		)
	}
	report_total = sum(report.values())
	ledger_total = sum(ledger.values())
	rows.append(
		{
			"check": "Outstanding Vendor Bills total",
			"reference": "",
			"detail": f"Report {flt(report_total, 2)}; supplier ledger balance {flt(ledger_total, 2)}",
		}
	)
	for supplier in sorted(set(report) | set(ledger)):
		a, b = report.get(supplier, 0.0), ledger.get(supplier, 0.0)
		if abs(a - b) > MONEY_TOLERANCE:
			rows.append(
				{
					"check": "Outstanding differs from the supplier ledger",
					"reference": supplier,
					"detail": f"Report {flt(a, 2)}, ledger {flt(b, 2)} (journal entries or opening balances "
					"outside bills and payments explain a difference)",
				}
			)
	if frappe.get_meta(PI).has_field("custom_is_msme"):
		for inv in frappe.db.sql(
			"""select pi.name, pi.supplier from `tabPurchase Invoice` pi join `tabSupplier` s on s.name = pi.supplier
			where pi.docstatus = 1 and ifnull(s.custom_is_msme, 0) = 1 and ifnull(pi.custom_is_msme, 0) = 0
				and ifnull(pi.is_return, 0) = 0""",
			as_dict=True,
		):
			rows.append(
				{
					"check": "Bill from an MSME supplier not flagged MSME",
					"reference": inv.name,
					"detail": inv.supplier,
				}
			)
		for inv in frappe.get_all(
			PI,
			filters={"docstatus": 1, "custom_is_msme": 1, "is_return": 0},
			fields=["name", "bill_date", "posting_date", "custom_msme_due_date"],
		):
			expected = add_days(msme_basis_date(inv.name, inv.bill_date, inv.posting_date), msme_days())
			if inv.custom_msme_due_date and getdate(inv.custom_msme_due_date) != getdate(expected):
				rows.append(
					{
						"check": "MSME pay-by date differs from the rule",
						"reference": inv.name,
						"detail": f"Stored {inv.custom_msme_due_date}, rule gives {getdate(expected)}",
					}
				)
	return rows


SHEETS = (
	("1 Purchase Trackers", ("check", "document", "detail")),
	("2 Receipt Log and heat", ("check", "document", "item", "detail")),
	("3 Supplier approval", ("check", "supplier", "detail")),
	("4 Comparison and overrides", ("check", "reference", "detail")),
	("5 Scheduled jobs", ("check", "job", "detail")),
	("6 Valuation by class", ("check", "item", "detail")),
	("7 Vendor bill reports", ("check", "reference", "detail")),
)

# Rows that report a figure rather than a problem; not counted as findings.
INFO_CHECKS = (
	"Usage",
	"Overrides logged",
	"Stock value by class",
	"Outstanding Vendor Bills total",
	"Supplier not approved, a reason logged on every PO",
	"Job Waiting for First Run",
)


def build_health_check(since=DEFAULT_SINCE, company=None):
	"""{sheet title: [row dicts]} for every check. Reads only."""
	since = getdate(since)
	company = company or stock_tree.default_company()
	data = [
		_trackers(since),
		_receipt_log(since),
		_supplier_approval(since),
		_comparison_and_overrides(since),
		_jobs(),
		_valuation(since),
		_reports(company),
	]
	return {title: rows for (title, _cols), rows in zip(SHEETS, data, strict=True)}


def findings(check):
	"""{sheet: number of real findings}, information rows left out."""
	return {sheet: len([r for r in rows if r["check"] not in INFO_CHECKS]) for sheet, rows in check.items()}


@frappe.whitelist()
def run_health_check(since=DEFAULT_SINCE):
	"""For the System Console check: the findings per sheet, and the rows themselves."""
	frappe.only_for("System Manager")
	check = build_health_check(since)
	return {"findings": findings(check), "rows": check}


@frappe.whitelist()
def download_health_check(since=DEFAULT_SINCE):
	"""System Manager only. Streams the health-check workbook; writes nothing."""
	frappe.only_for("System Manager")
	frappe.response["filename"] = f"PEPL Cycle 2 health check {today()}.xlsx"
	frappe.response["filecontent"] = audit.to_xlsx(build_health_check(since), SHEETS, INFO_CHECKS)
	frappe.response["type"] = "binary"
	return None
