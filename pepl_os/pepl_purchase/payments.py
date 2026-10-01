"""C2-17 - Vendor Payment Priority, Payment Entries mirroring Tally, MSME 45-day, Payment Run.

Prioritisation lives in ERPNext; the money moves in Tally. Every Tally payment is
recorded here as a standard Payment Entry against the Purchase Invoice
(record_vendor_payment), so ERPNext's outstanding amounts, ageing and Accounts
Payable stay true and Work Package R can match entries to Tally vouchers one to
one (one submitted entry per Tally voucher number and company). Nothing is
written into Tally.

Ranking (payment_priority), over submitted invoices with an outstanding amount:
  1. MSME invoices, earliest MSME pay-by date first (past it: Breach).
  2. Critical-vendor invoices past their due date, most overdue first.
  3. Everything else, oldest due date first.

MSME pay-by date = basis + MSME Payment Days. Basis = the bill date (else the
posting date), or - when "MSME Clock Starts From" is Receipt Date - the latest
linked Purchase Receipt date. Days left are recomputed every morning; Accounts
gets a ToDo (rule PUR-MSME-DUE) once 7 days or fewer are left, closed when paid.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, fmt_money, getdate, today

from pepl_os.common import params
from pepl_os.common.alerts import close_resolved, raise_todo
from pepl_os.common.jobs import tracked_job
from pepl_os.common.overrides import log_override

PI = "Purchase Invoice"
PE = "Payment Entry"
RUN = "PEPL Payment Run"
RUN_ITEM = "PEPL Payment Run Item"
MSME, CRITICAL, AGEING = "MSME", "Critical Overdue", "Ageing"
MANUAL, MIRROR = "Manual Tick", "Tally Mirror"
PENDING, PAID, PART_PAID, SKIPPED = "Pending", "Paid", "Part Paid", "Skipped"
DUE_RULE = "PUR-MSME-DUE"
SKIP_RULE = "PUR-MSME-SKIP"
RUN_RULE = "PUR-PAY-RUN"
ALERT_DAYS = 7
RECEIPT_DATE = "Receipt Date"
PAY_ROLES = ("Accounts User", "Accounts Manager", "System Manager")
ACCOUNTS_OWNER = "accounts_notification_owner"
MIN_REASON = 10


def msme_days():
	return params.get_int("custom_msme_payment_days", 45) or 45


# MSME pay-by date ---------------------------------------------------------------------


def latest_receipt_date(invoice_name):
	row = frappe.db.sql(
		"""select max(pr.posting_date) from `tabPurchase Invoice Item` pii
		join `tabPurchase Receipt` pr on pr.name = pii.purchase_receipt and pr.docstatus = 1
		where pii.parent = %s""",
		invoice_name,
	)
	return row[0][0] if row and row[0][0] else None


def msme_basis_date(invoice_name, bill_date, posting_date, receipts=None):
	"""receipts: the linked Purchase Receipt names (for an invoice not yet saved)."""
	if params.get("custom_msme_clock_basis") == RECEIPT_DATE:
		if receipts is not None:
			dates = [frappe.db.get_value("Purchase Receipt", r, "posting_date") for r in receipts]
			dates = [getdate(d) for d in dates if d]
			received = max(dates) if dates else None
		else:
			received = latest_receipt_date(invoice_name)
		if received:
			return getdate(received)
	return getdate(bill_date or posting_date)


def msme_due_date(invoice_name, bill_date, posting_date, receipts=None):
	return getdate(add_days(msme_basis_date(invoice_name, bill_date, posting_date, receipts), msme_days()))


def validate_invoice(doc, method=None):
	"""doc_events: Purchase Invoice validate. MSME flag from the supplier, pay-by date, days left."""
	doc.custom_is_msme = cint(frappe.db.get_value("Supplier", doc.supplier, "custom_is_msme"))
	if not doc.custom_is_msme or doc.get("is_return"):
		doc.custom_msme_due_date = None
		doc.custom_msme_days_left = 0
		return
	receipts = {row.purchase_receipt for row in doc.get("items") or [] if row.get("purchase_receipt")}
	due = msme_due_date(doc.name, doc.bill_date, doc.posting_date, receipts)
	doc.custom_msme_due_date = due
	doc.custom_msme_days_left = date_diff(due, today())


def open_msme_invoices(company=None):
	filters = {"docstatus": 1, "custom_is_msme": 1, "is_return": 0, "outstanding_amount": [">", 0]}
	if company:
		filters["company"] = company
	return frappe.get_all(
		PI,
		filters=filters,
		fields=[
			"name",
			"supplier_name",
			"bill_date",
			"posting_date",
			"custom_msme_due_date",
			"outstanding_amount",
		],
	)


def refresh_msme_days(as_of=None):
	"""Pay-by date and days left for every open MSME invoice."""
	as_of = getdate(as_of or today())
	count = 0
	for inv in open_msme_invoices():
		due = msme_due_date(inv.name, inv.bill_date, inv.posting_date)
		frappe.db.set_value(
			PI,
			inv.name,
			{"custom_msme_due_date": due, "custom_msme_days_left": date_diff(due, as_of)},
			update_modified=False,
		)
		count += 1
	return count


def sync_msme_todos(as_of=None):
	"""PUR-MSME-DUE: a ToDo to Accounts for each MSME invoice with 7 days or fewer left."""
	as_of = getdate(as_of or today())
	active = []
	for inv in open_msme_invoices():
		due = getdate(inv.custom_msme_due_date or msme_due_date(inv.name, inv.bill_date, inv.posting_date))
		left = date_diff(due, as_of)
		if left > ALERT_DAYS:
			continue
		active.append(inv.name)
		when = (
			_("{0} day(s) past the MSME deadline").format(-left)
			if left < 0
			else _("MSME payment due in {0} day(s)").format(left)
		)
		raise_todo(
			DUE_RULE,
			PI,
			inv.name,
			_("Pay {0} ({1}): {2} outstanding. {3} (pay by {4}).").format(
				inv.name,
				inv.supplier_name,
				fmt_money(inv.outstanding_amount),
				when,
				frappe.format(due, {"fieldtype": "Date"}),
			),
			owner_field=ACCOUNTS_OWNER,
			priority="High",
			due_date=due,
		)
	close_resolved(DUE_RULE, PI, active)
	return active


@tracked_job("MSME payment days and alerts")
def daily_msme_payments():
	refreshed = refresh_msme_days()
	alerts = sync_msme_todos()
	return {
		"records_touched": refreshed,
		"message": f"{refreshed} open MSME bills, {len(alerts)} with 7 days or fewer",
	}


@frappe.whitelist()
def refresh_msme_now():
	"""Do the morning MSME refresh now (Accounts / System Manager). Not the tracked job: that commits."""
	frappe.only_for(PAY_ROLES)
	refreshed = refresh_msme_days()
	return {"refreshed": refreshed, "alerts": sync_msme_todos()}


# Payment priority ---------------------------------------------------------------------


def payment_priority(as_of=None, company=None, supplier=None):
	"""Open invoices in payment order, with their rule, days left (negative = overdue) and a running total."""
	as_of = getdate(as_of or today())
	filters = {"docstatus": 1, "outstanding_amount": [">", 0]}
	if company:
		filters["company"] = company
	if supplier:
		filters["supplier"] = supplier
	invoices = frappe.get_all(
		PI,
		filters=filters,
		fields=[
			"name",
			"company",
			"supplier",
			"supplier_name",
			"bill_no",
			"bill_date",
			"posting_date",
			"due_date",
			"grand_total",
			"outstanding_amount",
			"custom_is_msme",
			"custom_msme_due_date",
		],
	)
	critical = set(
		frappe.get_all("Supplier", filters={"custom_vendor_criticality": "Critical"}, pluck="name")
	)
	rows = []
	for inv in invoices:
		due = getdate(inv.due_date or inv.posting_date)
		if cint(inv.custom_is_msme):
			rule = MSME
			pay_by = getdate(
				inv.custom_msme_due_date or msme_due_date(inv.name, inv.bill_date, inv.posting_date)
			)
			order = 0
		elif inv.supplier in critical and due < as_of:
			rule, pay_by, order = CRITICAL, due, 1
		else:
			rule, pay_by, order = AGEING, due, 2
		days_left = date_diff(pay_by, as_of)
		if rule == MSME:
			flag = "Breach" if days_left < 0 else ("Due Soon" if days_left <= ALERT_DAYS else "On Track")
		else:
			flag = "Overdue" if days_left < 0 else ("Due Today" if days_left == 0 else "Not Due")
		rows.append(
			frappe._dict(
				purchase_invoice=inv.name,
				company=inv.company,
				supplier=inv.supplier,
				supplier_name=inv.supplier_name,
				bill_no=inv.bill_no,
				bill_date=inv.bill_date,
				posting_date=inv.posting_date,
				grand_total=flt(inv.grand_total),
				outstanding_amount=flt(inv.outstanding_amount),
				rule=rule,
				pay_by=pay_by,
				days_left=days_left,
				flag=flag,
				_order=(order, pay_by, getdate(inv.posting_date), inv.name),
			)
		)
	rows.sort(key=lambda r: r._order)
	running = 0.0
	for rank, row in enumerate(rows, 1):
		running += row.outstanding_amount
		row.rank = rank
		row.running_total = running
		del row["_order"]
	return rows


def describe(row):
	"""'Rank #4 this week · MSME due in 6 days'."""
	left = row.days_left
	if row.rule == MSME:
		when = (
			_("MSME deadline passed {0} day(s) ago - Breach").format(-left)
			if left < 0
			else _("MSME due in {0} day(s)").format(left)
		)
	elif row.rule == CRITICAL:
		when = _("critical vendor, {0} day(s) overdue").format(-left)
	else:
		when = _("{0} day(s) overdue").format(-left) if left < 0 else _("due in {0} day(s)").format(left)
	return _("Rank #{0} this week · {1}").format(row.rank, when)


def _colour(row):
	if row.flag in ("Breach", "Overdue"):
		return "red"
	if row.flag in ("Due Soon", "Due Today"):
		return "orange"
	return "gray"


@frappe.whitelist()
def get_invoice_panel(purchase_invoice):
	"""Payment-priority panel on the Purchase Invoice."""
	frappe.has_permission(PI, doc=purchase_invoice, throw=True)
	company = frappe.db.get_value(PI, purchase_invoice, "company")
	for row in payment_priority(company=company):
		if row.purchase_invoice == purchase_invoice:
			return [{"text": describe(row), "colour": _colour(row)}]
	return []


@frappe.whitelist()
def get_supplier_panel(supplier):
	"""Payment-priority panel on the Supplier: its open bills, highest priority first."""
	frappe.has_permission("Supplier", doc=supplier, throw=True)
	if not frappe.has_permission(PI, "read"):
		return []
	mine = [row for row in payment_priority() if row.supplier == supplier]
	return [
		{
			"text": f"{row.purchase_invoice}: {fmt_money(row.outstanding_amount)} · {describe(row)}",
			"colour": _colour(row),
		}
		for row in mine[:5]
	]


# Recording a Tally payment -----------------------------------------------------------------


def duplicate_voucher(company, voucher, exclude=None):
	filters = {"company": company, "custom_tally_voucher_no": voucher, "docstatus": 1}
	if exclude:
		filters["name"] = ["!=", exclude]
	return frappe.db.get_value(PE, filters, "name")


def validate_payment_entry(doc, method=None):
	"""doc_events: Payment Entry validate. One submitted entry per Tally voucher number and company."""
	voucher = (doc.get("custom_tally_voucher_no") or "").strip()
	doc.custom_tally_voucher_no = voucher or None
	if not voucher:
		return
	other = duplicate_voucher(doc.company, voucher, exclude=doc.name)
	if other:
		frappe.throw(
			_("Tally voucher {0} is already recorded as Payment Entry {1}.").format(
				frappe.bold(voucher), frappe.bold(other)
			),
			title=_("Duplicate Tally voucher"),
		)


def open_run_for(invoice):
	"""The latest submitted Payment Run that approved this invoice and is not yet paid."""
	row = frappe.db.sql(
		"""select r.name from `tabPEPL Payment Run Item` i join `tabPEPL Payment Run` r on r.name = i.parent
		where i.purchase_invoice = %s and r.docstatus = 1 and i.approve = 1 and i.status != %s
		order by r.week_starting desc, r.creation desc limit 1""",
		(invoice, PAID),
	)
	return row[0][0] if row else None


def record_vendor_payment(
	invoice, paid_on, amount, tally_voucher_no, utr=None, tds_amount=0, source=MANUAL, payment_run=None
):
	"""Record a payment made in Tally as a submitted Payment Entry against the invoice.

	amount     - what is settled against the bill (the TDS deducted is part of it)
	tds_amount - TDS deducted at payment: the bank pays amount - TDS, a deduction row credits TDS
	Returns the Payment Entry name.
	"""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	amount, tds = flt(amount), flt(tds_amount)
	voucher = (tally_voucher_no or "").strip()
	inv = frappe.get_doc(PI, invoice)
	if inv.docstatus != 1:
		frappe.throw(_("Purchase Invoice {0} is not submitted.").format(invoice))
	if amount <= 0:
		frappe.throw(_("Enter the amount paid."))
	if amount > flt(inv.outstanding_amount) + 0.005:
		frappe.throw(
			_("{0} is more than the outstanding {1} on {2}.").format(
				fmt_money(amount), fmt_money(inv.outstanding_amount), invoice
			)
		)
	if tds < 0 or tds >= amount:
		frappe.throw(_("TDS deducted must be zero or less than the amount."))
	if not voucher:
		frappe.throw(_("Enter the Tally voucher number."))
	if not paid_on:
		frappe.throw(_("Enter the date paid."))
	other = duplicate_voucher(inv.company, voucher)
	if other:
		frappe.throw(
			_("Tally voucher {0} is already recorded as Payment Entry {1}.").format(
				frappe.bold(voucher), frappe.bold(other)
			),
			title=_("Duplicate Tally voucher"),
		)
	paid_on = getdate(paid_on)
	bank = params.get("custom_vendor_payment_bank_account") or None
	pe = get_payment_entry(PI, invoice, party_amount=amount, bank_account=bank, reference_date=paid_on)
	pe.posting_date = paid_on
	pe.reference_date = paid_on
	pe.reference_no = (utr or "").strip() or voucher
	mode = params.get("custom_vendor_payment_mode_of_payment")
	if mode:
		pe.mode_of_payment = mode
	pe.custom_tally_voucher_no = voucher
	pe.custom_payment_source = source if source in (MANUAL, MIRROR) else MANUAL
	pe.custom_payment_run = payment_run or open_run_for(invoice)
	if tds:
		account = params.get("custom_vendor_tds_account")
		if not account:
			frappe.throw(_("Set Vendor Payment: TDS Payable Account in PEPL System Parameters."))
		pe.paid_amount = amount - tds
		pe.append(
			"deductions",
			{
				"account": account,
				"cost_center": inv.get("cost_center")
				or frappe.get_cached_value("Company", inv.company, "cost_center"),
				"amount": -tds,
				"description": _("TDS deducted at payment"),
			},
		)
	pe.set_amounts()
	pe.insert()
	pe.submit()
	return pe.name


@frappe.whitelist()
def mark_paid(purchase_invoice, paid_on, amount, tally_voucher_no, utr=None, tds_amount=0):
	"""The "Mark paid" row action of the Vendor Payment Priority report (Accounts)."""
	frappe.only_for(PAY_ROLES)
	return record_vendor_payment(purchase_invoice, paid_on, amount, tally_voucher_no, utr, tds_amount, MANUAL)


def on_payment_entry_change(doc, method=None):
	"""doc_events: Payment Entry on_submit / on_cancel. Payment Run rows and MSME ToDos follow."""
	invoices = {r.reference_name for r in doc.get("references") or [] if r.reference_doctype == PI}
	if not invoices:
		return
	for invoice in invoices:
		sync_run_rows(invoice)
	_alerts_never_block(sync_msme_todos)
	_alerts_never_block(sync_run_todos)


def _alerts_never_block(fn):
	"""A missing notification owner must not stop a payment being recorded; the daily job retries."""
	try:
		fn()
	except frappe.ValidationError:
		frappe.clear_last_message()
		frappe.log_error(title=f"PEPL payments: {fn.__name__}")


def latest_payment(invoice):
	row = frappe.db.sql(
		"""select pe.name from `tabPayment Entry Reference` ref join `tabPayment Entry` pe on pe.name = ref.parent
		where ref.reference_doctype = %s and ref.reference_name = %s and pe.docstatus = 1
		order by pe.posting_date desc, pe.creation desc limit 1""",
		(PI, invoice),
	)
	return row[0][0] if row else None


def sync_run_rows(invoice):
	"""Each submitted run row of this invoice: Paid / Part Paid / Pending from the invoice outstanding."""
	outstanding = flt(frappe.db.get_value(PI, invoice, "outstanding_amount"))
	payment = latest_payment(invoice)
	rows = frappe.get_all(
		RUN_ITEM,
		filters={"purchase_invoice": invoice, "docstatus": 1, "approve": 1},
		fields=["name", "outstanding"],
	)
	for row in rows:
		paid = max(0.0, flt(row.outstanding) - outstanding)
		status = PAID if outstanding <= 0.005 else (PART_PAID if paid > 0.005 else PENDING)
		frappe.db.set_value(
			RUN_ITEM,
			row.name,
			{"status": status, "paid_amount": paid, "payment_entry": payment if paid > 0.005 else None},
			update_modified=False,
		)
	return len(rows)


# Payment Run ---------------------------------------------------------------------------


def validate_run(doc):
	if not doc.prepared_by:
		doc.prepared_by = frappe.session.user
	if doc.docstatus == 0:
		for row in doc.items:
			row.status = PENDING if cint(row.approve) else SKIPPED
	doc.total_outstanding = sum(flt(r.outstanding) for r in doc.items)
	doc.total_approved = sum(flt(r.outstanding) for r in doc.items if cint(r.approve))


def skipped_msme_without_reason(doc):
	return [
		row
		for row in doc.items
		if row.rule == MSME and not cint(row.approve) and len((row.skip_reason or "").strip()) < MIN_REASON
	]


def before_submit_run(doc):
	if not doc.items:
		frappe.throw(_("Build the run from the worklist first."))
	missing = skipped_msme_without_reason(doc)
	if missing:
		frappe.throw(
			_("Skipping an MSME bill needs a reason of at least {0} characters: {1}").format(
				MIN_REASON, ", ".join(f"row {r.idx} {r.purchase_invoice}" for r in missing)
			),
			title=_("Reason required"),
		)


def on_submit_run(doc):
	for row in doc.items:
		if row.rule == MSME and not cint(row.approve):
			log_override(
				SKIP_RULE,
				RUN,
				doc.name,
				_("MSME bill {0} ({1}) skipped in Payment Run {2}").format(
					row.purchase_invoice, row.supplier_name, doc.name
				),
				row.skip_reason,
				module="PEPL Purchase",
			)
	for row in doc.items:
		if cint(row.approve):
			sync_run_rows(row.purchase_invoice)
	_alerts_never_block(sync_run_todos)


def on_cancel_run(doc):
	_alerts_never_block(sync_run_todos)


def sync_run_todos():
	"""PUR-PAY-RUN: Accounts has a ToDo for each submitted run with approved bills still unpaid."""
	active = []
	runs = frappe.get_all(RUN, filters={"docstatus": 1}, fields=["name", "week_starting"])
	for run in runs:
		open_rows = frappe.get_all(
			RUN_ITEM,
			filters={"parent": run.name, "approve": 1, "status": ["!=", PAID]},
			fields=["outstanding", "paid_amount"],
		)
		if not open_rows:
			continue
		active.append(run.name)
		due = sum(flt(r.outstanding) - flt(r.paid_amount) for r in open_rows)
		raise_todo(
			RUN_RULE,
			RUN,
			run.name,
			_(
				"Payment Run {0} (week of {1}): {2} approved bill(s), {3} still to pay. Record each Tally payment with Mark paid."
			).format(
				run.name,
				frappe.format(run.week_starting, {"fieldtype": "Date"}),
				len(open_rows),
				fmt_money(due),
			),
			owner_field=ACCOUNTS_OWNER,
		)
	close_resolved(RUN_RULE, RUN, active)
	return active


@frappe.whitelist()
def build_from_worklist(name):
	"""Fill a draft Payment Run with this week's worklist, in rank order."""
	doc = frappe.get_doc(RUN, name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft Payment Run can be rebuilt."))
	doc.set("items", [])
	for row in payment_priority(as_of=doc.week_starting or today(), company=doc.company):
		doc.append(
			"items",
			{
				"rank": row.rank,
				"purchase_invoice": row.purchase_invoice,
				"supplier": row.supplier,
				"supplier_name": row.supplier_name,
				"rule": row.rule,
				"pay_by": row.pay_by,
				"days_left": row.days_left,
				"outstanding": row.outstanding_amount,
				"approve": 1,
			},
		)
	doc.save()
	return len(doc.items)


# Reports -------------------------------------------------------------------------------


def msme_compliance(filters=None):
	"""Every MSME invoice: basis, pay-by, the Payment Entry date that cleared it, days taken, status."""
	filters = frappe._dict(filters or {})
	as_of = getdate(filters.get("as_of") or today())
	conditions = {"docstatus": 1, "custom_is_msme": 1, "is_return": 0}
	for key in ("company", "supplier"):
		if filters.get(key):
			conditions[key] = filters[key]
	if filters.get("from_date"):
		conditions["posting_date"] = [">=", filters.from_date]
	invoices = frappe.get_all(
		PI,
		filters=conditions,
		fields=[
			"name",
			"supplier",
			"supplier_name",
			"bill_no",
			"bill_date",
			"posting_date",
			"grand_total",
			"outstanding_amount",
			"custom_msme_due_date",
		],
		order_by="posting_date",
	)
	rows = []
	for inv in invoices:
		basis = msme_basis_date(inv.name, inv.bill_date, inv.posting_date)
		due = getdate(inv.custom_msme_due_date or add_days(basis, msme_days()))
		cleared_on, payment = None, None
		if flt(inv.outstanding_amount) <= 0.005:
			last = frappe.db.sql(
				"""select pe.name, pe.posting_date from `tabPayment Entry Reference` ref
				join `tabPayment Entry` pe on pe.name = ref.parent
				where ref.reference_doctype = %s and ref.reference_name = %s and pe.docstatus = 1
				order by pe.posting_date desc limit 1""",
				(PI, inv.name),
			)
			if last:
				payment, cleared_on = last[0][0], getdate(last[0][1])
				status = "Paid on time" if cleared_on <= due else "Paid late"
				days_taken = date_diff(cleared_on, basis)
			else:
				status, days_taken = "Settled without payment", None  # e.g. a debit note cleared it
		else:
			status = "Open" if as_of <= due else "Breach"
			days_taken = date_diff(as_of, basis)
		rows.append(
			frappe._dict(
				purchase_invoice=inv.name,
				supplier=inv.supplier,
				supplier_name=inv.supplier_name,
				bill_no=inv.bill_no,
				basis_date=basis,
				due_date=due,
				payment_entry=payment,
				cleared_on=cleared_on,
				days_taken=days_taken,
				grand_total=flt(inv.grand_total),
				outstanding_amount=flt(inv.outstanding_amount),
				status=status,
			)
		)
	if filters.get("status"):
		rows = [r for r in rows if r.status == filters.status]
	return rows


BUCKETS = (("not_due", None), ("age_1_30", 30), ("age_31_60", 60), ("age_61_90", 90), ("age_91_plus", None))


def outstanding_vendor_bills(filters=None):
	"""Outstanding per supplier by days overdue (from the due date), from outstanding_amount.

	Debit notes count negative and unallocated advance payments are taken off, as in
	ERPNext's Accounts Payable report, so the totals match it.
	"""
	filters = frappe._dict(filters or {})
	as_of = getdate(filters.get("as_of") or today())
	conditions = {"docstatus": 1, "outstanding_amount": ["!=", 0], "posting_date": ["<=", as_of]}
	for key in ("company", "supplier"):
		if filters.get(key):
			conditions[key] = filters[key]
	invoices = frappe.get_all(
		PI,
		filters=conditions,
		fields=["supplier", "supplier_name", "due_date", "posting_date", "outstanding_amount"],
	)
	by_supplier = {}

	def row_for(supplier, supplier_name):
		return by_supplier.setdefault(
			supplier,
			frappe._dict(
				supplier=supplier,
				supplier_name=supplier_name,
				bills=0,
				advances=0.0,
				total=0.0,
				**{key: 0.0 for key, _limit in BUCKETS},
			),
		)

	for inv in invoices:
		row = row_for(inv.supplier, inv.supplier_name)
		amount = flt(inv.outstanding_amount)
		overdue = date_diff(as_of, getdate(inv.due_date or inv.posting_date))
		if overdue <= 0:
			key = "not_due"
		elif overdue <= 30:
			key = "age_1_30"
		elif overdue <= 60:
			key = "age_31_60"
		elif overdue <= 90:
			key = "age_61_90"
		else:
			key = "age_91_plus"
		row[key] += amount
		row.total += amount
		row.bills += 1
	pe_filters = {
		"docstatus": 1,
		"party_type": "Supplier",
		"payment_type": "Pay",
		"unallocated_amount": [">", 0],
	}
	pe_filters["posting_date"] = ["<=", as_of]
	for key, field in (("company", "company"), ("supplier", "party")):
		if filters.get(key):
			pe_filters[field] = filters[key]
	for adv in frappe.get_all(PE, filters=pe_filters, fields=["party", "party_name", "unallocated_amount"]):
		row = row_for(adv.party, adv.party_name)
		row.advances -= flt(adv.unallocated_amount)
		row.total -= flt(adv.unallocated_amount)
	return sorted(by_supplier.values(), key=lambda r: -r.total)
