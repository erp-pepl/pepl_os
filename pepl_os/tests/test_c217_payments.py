"""C2-17 - Vendor Payment Priority, Payment Entries from Tally payments, MSME 45-day, Payment Run."""

import frappe
from frappe.utils import add_days, getdate, today

from pepl_os.pepl_purchase import payments as pay
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, set_param

SERVICE = "PEPL-T-PAY-SERVICE"
MSME_SUP = "PEPL T PAY MSME"
CRIT_SUP = "PEPL T PAY CRITICAL"
ROUTINE_SUP = "PEPL T PAY ROUTINE"


def _supplier(name, msme=False, criticality="Routine"):
	if not frappe.db.exists("Supplier", name):
		fields = {"custom_vendor_criticality": criticality}
		if msme:
			fields.update({"custom_is_msme": 1, "custom_udyam_number": "UDYAM-MH-00-0000001"})
		make_supplier(name, **fields).insert(ignore_permissions=True)
	return name


def _account(account_type=None, root_type=None, exclude_type=None):
	filters = {"company": TEST_COMPANY, "is_group": 0}
	if account_type:
		filters["account_type"] = account_type
	if root_type:
		filters["root_type"] = root_type
	for name, kind in frappe.get_all(
		"Account", filters=filters, fields=["name", "account_type"], as_list=True
	):
		if exclude_type and kind in exclude_type:
			continue
		return name


def _invoice(supplier, amount, posting=None, bill_date=None, due=None, submit=True):
	posting = posting or today()
	pi = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"company": TEST_COMPANY,
			"supplier": supplier,
			"set_posting_time": 1,
			"posting_date": posting,
			"bill_no": f"T-{frappe.generate_hash(length=6)}",
			"bill_date": bill_date or posting,
			"due_date": due or posting,
			"items": [{"item_code": SERVICE, "qty": 1, "rate": amount}],
		}
	).insert(ignore_permissions=True)
	if submit:
		pi.submit()
	return pi


class TestVendorPayments(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_item(SERVICE, "_Test Item Group", is_stock_item=0)
		_supplier(MSME_SUP, msme=True)
		_supplier(CRIT_SUP, criticality="Critical")
		_supplier(ROUTINE_SUP)

	def setUp(self):
		set_param("custom_msme_payment_days", 45)
		set_param("custom_msme_clock_basis", "Bill Date")
		set_param("custom_vendor_payment_bank_account", _account("Bank"))
		set_param("custom_vendor_tds_account", _account(root_type="Liability", exclude_type=("Payable",)))
		set_param("enable_operational_todos", 1)

	def test_msme_due_date_from_bill_date(self):
		pi = _invoice(MSME_SUP, 1000, posting=today(), bill_date=add_days(today(), -5))
		self.assertEqual(pi.custom_is_msme, 1)
		self.assertEqual(getdate(pi.custom_msme_due_date), getdate(add_days(today(), 40)))
		self.assertEqual(pi.custom_msme_days_left, 40)

	def test_msme_due_date_from_receipt_date_when_switched(self):
		set_param("custom_msme_clock_basis", "Receipt Date")
		receipt_date = getdate(add_days(today(), -2))
		with self.subTest("receipt basis"):
			original = pay.latest_receipt_date
			pay.latest_receipt_date = lambda name: receipt_date
			try:
				due = pay.msme_due_date("X", add_days(today(), -10), today())
			finally:
				pay.latest_receipt_date = original
			self.assertEqual(due, getdate(add_days(receipt_date, 45)))
		# No receipt linked: falls back to the bill date.
		self.assertEqual(
			pay.msme_due_date("X", add_days(today(), -10), today(), receipts=set()),
			getdate(add_days(today(), 35)),
		)

	def test_priority_order_three_rules(self):
		ageing = _invoice(ROUTINE_SUP, 300, posting=add_days(today(), -60), due=add_days(today(), -50))
		critical = _invoice(CRIT_SUP, 200, posting=add_days(today(), -20), due=add_days(today(), -3))
		msme = _invoice(MSME_SUP, 100, posting=today())
		ranked = [r.purchase_invoice for r in pay.payment_priority(company=TEST_COMPANY)]
		mine = [n for n in ranked if n in (ageing.name, critical.name, msme.name)]
		self.assertEqual(mine, [msme.name, critical.name, ageing.name])
		rows = {r.purchase_invoice: r for r in pay.payment_priority(company=TEST_COMPANY)}
		self.assertEqual(
			(rows[msme.name].rule, rows[critical.name].rule, rows[ageing.name].rule),
			(pay.MSME, pay.CRITICAL, pay.AGEING),
		)
		self.assertTrue(pay.describe(rows[msme.name]).startswith("Rank #"))

	def test_record_vendor_payment_creates_submitted_payment_entry(self):
		pi = _invoice(ROUTINE_SUP, 1000)
		name = pay.record_vendor_payment(pi.name, today(), 1000, "TV-1001", utr="UTR123")
		pe = frappe.get_doc("Payment Entry", name)
		self.assertEqual(pe.docstatus, 1)
		self.assertEqual((pe.party_type, pe.party), ("Supplier", ROUTINE_SUP))
		self.assertEqual(
			[(r.reference_doctype, r.reference_name, r.allocated_amount) for r in pe.references],
			[("Purchase Invoice", pi.name, 1000)],
		)
		self.assertEqual((pe.reference_no, str(pe.reference_date)), ("UTR123", today()))
		self.assertEqual((pe.custom_tally_voucher_no, pe.custom_payment_source), ("TV-1001", pay.MANUAL))
		self.assertEqual(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), 0)

	def test_part_payment_reduces_outstanding_then_clears(self):
		pi = _invoice(ROUTINE_SUP, 1000)
		pay.record_vendor_payment(pi.name, today(), 400, "TV-2001")
		self.assertEqual(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), 600)
		pay.record_vendor_payment(pi.name, today(), 600, "TV-2002")
		self.assertEqual(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), 0)
		self.assertNotIn(pi.name, [r.purchase_invoice for r in pay.payment_priority(company=TEST_COMPANY)])

	def test_duplicate_tally_voucher_refused(self):
		one = _invoice(ROUTINE_SUP, 100)
		two = _invoice(ROUTINE_SUP, 100)
		pay.record_vendor_payment(one.name, today(), 100, "TV-3001")
		with self.assertRaises(frappe.ValidationError):
			pay.record_vendor_payment(two.name, today(), 100, "TV-3001")

	def test_tds_deduction_row(self):
		pi = _invoice(ROUTINE_SUP, 1000)
		pe = frappe.get_doc(
			"Payment Entry", pay.record_vendor_payment(pi.name, today(), 1000, "TV-4001", tds_amount=100)
		)
		self.assertEqual(pe.paid_amount, 900)
		self.assertEqual(
			[(d.account, d.amount) for d in pe.deductions],
			[(pay.params.get("custom_vendor_tds_account"), -100)],
		)
		self.assertEqual(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), 0)

	def _run(self):
		run = frappe.get_doc({"doctype": pay.RUN, "company": TEST_COMPANY, "week_starting": today()}).insert(
			ignore_permissions=True
		)
		pay.build_from_worklist(run.name)
		return frappe.get_doc(pay.RUN, run.name)

	def test_payment_entry_updates_payment_run_row(self):
		pi = _invoice(ROUTINE_SUP, 500)
		run = self._run()
		for row in run.items:
			if row.rule == pay.MSME:
				row.approve, row.skip_reason = 0, "Not this week (test reason)"
		run.save()
		run.submit()
		pay.record_vendor_payment(pi.name, today(), 200, "TV-5001")
		row = frappe.db.get_value(
			pay.RUN_ITEM,
			{"parent": run.name, "purchase_invoice": pi.name},
			["status", "paid_amount"],
			as_dict=True,
		)
		self.assertEqual((row.status, row.paid_amount), (pay.PART_PAID, 200))
		name = pay.record_vendor_payment(pi.name, today(), 300, "TV-5002")
		row = frappe.db.get_value(
			pay.RUN_ITEM,
			{"parent": run.name, "purchase_invoice": pi.name},
			["status", "payment_entry"],
			as_dict=True,
		)
		self.assertEqual((row.status, row.payment_entry), (pay.PAID, name))
		# Both payments are linked to the run that approved the bill.
		self.assertEqual(
			frappe.get_all(
				"Payment Entry",
				filters={"custom_tally_voucher_no": ["in", ["TV-5001", "TV-5002"]]},
				pluck="custom_payment_run",
			),
			[run.name, run.name],
		)

	def test_cancel_reverts_run_row(self):
		pi = _invoice(ROUTINE_SUP, 500)
		run = self._run()
		for row in run.items:
			if row.rule == pay.MSME:
				row.approve, row.skip_reason = 0, "Not this week (test reason)"
		run.save()
		run.submit()
		name = pay.record_vendor_payment(pi.name, today(), 500, "TV-6001")
		frappe.get_doc("Payment Entry", name).cancel()
		row = frappe.db.get_value(
			pay.RUN_ITEM,
			{"parent": run.name, "purchase_invoice": pi.name},
			["status", "payment_entry"],
			as_dict=True,
		)
		self.assertEqual((row.status, row.payment_entry), (pay.PENDING, None))
		self.assertIn(pi.name, [r.purchase_invoice for r in pay.payment_priority(company=TEST_COMPANY)])

	def test_skip_msme_in_payment_run_needs_reason(self):
		_invoice(MSME_SUP, 100)
		run = self._run()
		for row in run.items:
			if row.rule == pay.MSME:
				row.approve = 0
		run.save()
		with self.assertRaises(frappe.ValidationError):
			run.submit()
		run.reload()
		for row in run.items:
			if row.rule == pay.MSME:
				row.skip_reason = "Supplier asked to hold (test reason)"
		run.save()
		run.submit()
		self.assertTrue(
			frappe.db.exists("PEPL Override Log", {"rule_code": pay.SKIP_RULE, "reference_name": run.name})
		)

	def test_msme_todo_opens_at_7_days_and_closes_on_paid(self):
		pi = _invoice(MSME_SUP, 100, bill_date=add_days(today(), -40))  # pay by today + 5
		pay.sync_msme_todos()
		todo = {"reference_type": "Purchase Invoice", "reference_name": pi.name, "status": "Open"}
		self.assertTrue(frappe.db.exists("ToDo", todo))
		far = _invoice(MSME_SUP, 100, bill_date=today())  # pay by today + 45
		pay.sync_msme_todos()
		self.assertFalse(frappe.db.exists("ToDo", dict(todo, reference_name=far.name)))
		pay.record_vendor_payment(pi.name, today(), 100, "TV-7001")
		self.assertFalse(frappe.db.exists("ToDo", todo))

	def test_msme_compliance_statuses(self):
		on_time = _invoice(MSME_SUP, 100, bill_date=add_days(today(), -10))
		late = _invoice(MSME_SUP, 100, bill_date=add_days(today(), -60))
		open_ = _invoice(MSME_SUP, 100, bill_date=add_days(today(), -5))
		breach = _invoice(MSME_SUP, 100, bill_date=add_days(today(), -50))
		pay.record_vendor_payment(on_time.name, today(), 100, "TV-8001")
		pay.record_vendor_payment(late.name, today(), 100, "TV-8002")
		status = {r.purchase_invoice: r.status for r in pay.msme_compliance({"company": TEST_COMPANY})}
		self.assertEqual(
			[status[x.name] for x in (on_time, late, open_, breach)],
			["Paid on time", "Paid late", "Open", "Breach"],
		)
