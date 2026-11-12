"""CR1 - Older Sales Orders and Sales Invoices booked with their real dates; negative stock; Tally GST ledgers."""

import frappe
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
from frappe.utils import add_days, add_years, getdate, today

from pepl_os.pepl_accounts import historic, tally_gst
from pepl_os.pepl_production import job_orders as jo
from pepl_os.pepl_production import ld
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, TEST_CUSTOMER, make_bom, make_item, test_warehouse
from pepl_os.tests.utils import PEPLTestCase, set_param, set_single

FG = "T-CR1-FG-SHAFT"  # manufactured, default BOM: a new order drafts a Job Order
BOUGHT = "T-CR1-BO-BEARING"  # bought-out, valued at 50: a new order drafts a Material Request
UNVALUED = "T-CR1-BO-NORATE"  # bought-out, no stock, no rate of any kind
RM = "T-CR1-RM-ROD"


def _order(lines, days_ago=30, sector="Railways", submit=True, **fields):
	store = test_warehouse("Bought-Out Stores")
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": TEST_CUSTOMER,
			"company": TEST_COMPANY,
			"transaction_date": add_days(today(), -days_ago),
			"delivery_date": add_days(today(), -days_ago + 10),
			"custom_sector": sector,
			"items": [
				{
					"item_code": code,
					"qty": qty,
					"rate": 100,
					"warehouse": test_warehouse("FG Stores") if code == FG else store,
					"delivery_date": add_days(today(), -days_ago + 10),
				}
				for code, qty in lines
			],
			**fields,
		}
	).insert(ignore_permissions=True)
	if submit:
		so.submit()
	return so


def _invoice(so, days_ago=20, tally_no=None, update_stock=1):
	si = make_sales_invoice(so.name)
	si.set_posting_time = 1
	si.posting_date = add_days(today(), -days_ago)
	si.due_date = si.posting_date
	si.payment_schedule = []
	si.update_stock = update_stock
	si.custom_tally_invoice_no = tally_no
	return si.insert(ignore_permissions=True)


def _stock(item, store="Bought-Out Stores"):
	return (
		frappe.db.get_value("Bin", {"item_code": item, "warehouse": test_warehouse(store)}, "actual_qty") or 0
	)


def _requested(so_name):
	return frappe.get_all("Material Request Item", filters={"sales_order": so_name, "docstatus": ["<", 2]})


def _job_orders(so_name):
	return frappe.get_all("Work Order", filters={"sales_order": so_name, "docstatus": ["<", 2]})


class TestHistoricBooking(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		rm = make_item(RM, st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10).name
		make_item(FG, st.FINISHED_GOODS)
		make_bom(FG, rm)
		make_item(BOUGHT, st.BOUGHT_OUT, valuation_rate=50)
		make_item(UNVALUED, st.BOUGHT_OUT)

	def setUp(self):
		set_param(historic.CUTOFF_FIELD, today())
		set_param(jo.ENABLE_FIELD, 1)
		set_param(ld.DEFAULT_SECTORS_FIELD, "Railways\nDefence")
		set_param(ld.DEFAULT_RATE_FIELD, 0.5)
		set_param(ld.DEFAULT_PERIOD_FIELD, ld.WEEK)
		set_param(ld.DEFAULT_CAP_FIELD, 10)

	# ---- the rule ----
	def test_rule_off_when_the_date_is_empty(self):
		set_param(historic.CUTOFF_FIELD, None)
		self.assertIsNone(historic.cutoff())
		self.assertFalse(historic.is_historic(add_years(today(), -4)))
		so = _order([(BOUGHT, 2)], submit=False)
		self.assertEqual(so.get(historic.FLAG), 0)
		self.assertEqual(so.get(ld.APPLICABLE), 1)  # a new Railways order keeps its standard LD clause

	def test_the_day_itself_is_not_historic(self):
		self.assertTrue(historic.is_historic(add_days(today(), -1)))
		self.assertFalse(historic.is_historic(today()))

	# ---- Sales Order ----
	def test_historic_order_drafts_no_material_request_no_job_order_no_ld(self):
		so = _order([(FG, 3), (BOUGHT, 4)])
		self.assertEqual(so.get(historic.FLAG), 1)
		self.assertEqual(so.get(ld.APPLICABLE), 0)
		self.assertEqual(_job_orders(so.name), [])
		self.assertEqual(_requested(so.name), [])

	def test_order_on_or_after_the_date_works_as_before(self):
		set_param(historic.CUTOFF_FIELD, add_days(today(), -31))
		so = _order([(FG, 3), (BOUGHT, 4)])
		self.assertEqual(so.get(historic.FLAG), 0)
		self.assertEqual(so.get(ld.APPLICABLE), 1)
		self.assertEqual(len(_job_orders(so.name)), 1)
		self.assertTrue(_requested(so.name))

	def test_ld_typed_by_hand_on_a_historic_order_stays(self):
		so = _order(
			[(BOUGHT, 2)],
			submit=False,
			custom_ld_applicable=1,
			custom_ld_rate_percent=1,
			custom_ld_period=ld.WEEK,
			custom_ld_max_percent=5,
		)
		self.assertEqual((so.get(ld.APPLICABLE), so.get(ld.RATE), so.get(ld.CAP)), (1, 1, 5))

	# ---- Sales Invoice ----
	def test_historic_invoice_needs_its_tally_number(self):
		so = _order([(BOUGHT, 2)])
		si = _invoice(so, update_stock=0)
		self.assertEqual(si.get(historic.FLAG), 1)
		with self.assertRaisesRegex(frappe.ValidationError, "Tally Invoice No"):
			si.submit()
		si.reload()
		si.custom_tally_invoice_no = " PEPL/23-24/101 "
		si.save(ignore_permissions=True)
		si.submit()
		self.assertEqual(si.custom_tally_invoice_no, "PEPL/23-24/101")
		self.assertEqual(si.docstatus, 1)

	def test_a_tally_number_is_used_once(self):
		_invoice(_order([(BOUGHT, 4)]), update_stock=0, tally_no="PEPL/23-24/102").submit()
		with self.assertRaisesRegex(frappe.ValidationError, "already on Sales Invoice"):
			_invoice(_order([(BOUGHT, 3)]), update_stock=0, tally_no="PEPL/23-24/102")

	def test_new_invoice_is_not_historic_and_needs_no_number(self):
		set_param(historic.CUTOFF_FIELD, add_days(today(), -40))
		so = _order([(BOUGHT, 2)])
		si = _invoice(so, update_stock=0)
		self.assertEqual(si.get(historic.FLAG), 0)
		si.submit()
		self.assertEqual(si.docstatus, 1)

	def test_historic_invoices_make_no_e_invoice_or_e_waybill(self):
		so = _order([(BOUGHT, 2)])
		si = _invoice(so, update_stock=0, tally_no="PEPL/23-24/103")
		si.submit()
		for field in ("einvoice_status", "e_waybill_status"):
			if si.meta.has_field(field):  # India Compliance fields (not on the CI site)
				self.assertEqual(si.get(field), historic.NOT_APPLICABLE)

	# ---- negative stock ----
	def test_an_item_with_no_rate_is_named_before_erpnext_refuses(self):
		set_single("Stock Settings", "allow_negative_stock", 1)
		so = _order([(UNVALUED, 2)])
		si = _invoice(so, tally_no="PEPL/23-24/104")
		with self.assertRaisesRegex(frappe.ValidationError, UNVALUED):
			si.submit()

	def test_invoice_takes_stock_negative_and_the_later_receipt_brings_it_to_zero(self):
		set_single("Stock Settings", "allow_negative_stock", 1)
		before = _stock(BOUGHT)
		so = _order([(BOUGHT, 10)])
		_invoice(so, tally_no="PEPL/23-24/105").submit()
		self.assertEqual(_stock(BOUGHT), before - 10)
		receipt = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"purpose": "Material Receipt",
				"company": TEST_COMPANY,
				"items": [
					{
						"item_code": BOUGHT,
						"qty": 10,
						"t_warehouse": test_warehouse("Bought-Out Stores"),
						"basic_rate": 50,
					}
				],
			}
		).insert(ignore_permissions=True)
		receipt.submit()
		self.assertEqual(_stock(BOUGHT), before)


class TestFiscalYears(PEPLTestCase):
	def test_missing_earlier_years_are_created_once(self):
		first = getdate(
			frappe.get_all(
				"Fiscal Year", fields=["year_start_date"], order_by="year_start_date asc", limit=1
			)[0].year_start_date
		)
		target = add_days(add_years(first, -2), 10)
		result = historic.create_fiscal_years(target)
		self.assertEqual(len(result["created"]), 2)
		covering = frappe.get_all(
			"Fiscal Year",
			filters={"year_start_date": ["<=", target], "year_end_date": [">=", target]},
			pluck="name",
		)
		self.assertEqual(len(covering), 1)
		self.assertEqual(historic.create_fiscal_years(target)["created"], [])

	def test_only_accounts_or_system_managers(self):
		from pepl_os.tests.utils import make_user

		make_user("t-cr1-clerk@example.com", ["Sales User"])
		frappe.set_user("t-cr1-clerk@example.com")
		with self.assertRaises(frappe.PermissionError):
			historic.create_fiscal_years("2001-01-01")


class TestTallyGstLedgers(PEPLTestCase):
	"""India Compliance is not on the CI site: its accounts and a template are made here as it makes them."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.abbr = frappe.get_cached_value("Company", TEST_COMPANY, "abbr")

	def _account(self, name, parent):
		full = f"{name} - {self.abbr}"
		if not frappe.db.exists("Account", full):
			frappe.get_doc(
				{
					"doctype": "Account",
					"company": TEST_COMPANY,
					"account_name": name,
					"parent_account": parent,
					"account_type": "Tax",
				}
			).insert(ignore_permissions=True)
		return full

	def _india_compliance_like(self):
		duties = frappe.db.get_value(
			"Account", {"company": TEST_COMPANY, "account_name": "Duties and Taxes"}, "name"
		)
		assets = frappe.db.get_value(
			"Account", {"company": TEST_COMPANY, "account_name": "Tax Assets", "is_group": 1}, "name"
		) or frappe.db.get_value(
			"Account", {"company": TEST_COMPANY, "account_name": "Current Assets"}, "name"
		)
		for old in tally_gst.RENAMES:
			self._account(old, assets if old.startswith("Input Tax") and not old.endswith("RCM") else duties)
		self._account("Output Tax CGST RCM", duties)  # no Tally ledger: stays as it is
		template = frappe.get_doc(
			{
				"doctype": "Sales Taxes and Charges Template",
				"title": "T-CR1 Output In-state",
				"company": TEST_COMPANY,
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": f"Output Tax CGST - {self.abbr}",
						"description": "Output Tax CGST",
						"rate": 9,
					},
					{
						"charge_type": "On Net Total",
						"account_head": f"Output Tax SGST - {self.abbr}",
						"description": "Output Tax SGST",
						"rate": 9,
					},
				],
			}
		).insert(ignore_permissions=True)
		return duties, template.name

	def test_tally_tree_built_and_india_compliance_accounts_renamed(self):
		duties, template = self._india_compliance_like()
		result = tally_gst.setup_tally_gst_ledgers(TEST_COMPANY)
		a = self.abbr
		self.assertIn(f"Output Tax CGST - {a} → CGST - {a}", result["renamed"])
		for ledger, parent in tally_gst.ledger_parents().items():
			name = f"{ledger} - {a}"
			self.assertTrue(frappe.db.exists("Account", name), name)
			expected = f"{parent} - {a}" if parent else duties
			self.assertEqual(frappe.db.get_value("Account", name, "parent_account"), expected, name)
		self.assertEqual(
			frappe.db.get_value("Account", f"Intermediate ITC - WB CGST - {a}", "root_type"), "Liability"
		)
		self.assertFalse(frappe.db.exists("Account", f"Output Tax CGST - {a}"))
		self.assertTrue(frappe.db.exists("Account", f"Output Tax CGST RCM - {a}"))
		rows = frappe.get_doc("Sales Taxes and Charges Template", template).taxes
		self.assertEqual(
			[(r.account_head, r.description) for r in rows],
			[(f"CGST - {a}", "CGST"), (f"SGST - {a}", "SGST")],
		)
		self.assertEqual(
			len(tally_gst.ledger_parents()), 37
		)  # 10 groups + 27 ledgers, as in PEPL's Tally sheet

	def test_running_again_changes_nothing(self):
		self._india_compliance_like()
		tally_gst.setup_tally_gst_ledgers(TEST_COMPANY)
		again = tally_gst.setup_tally_gst_ledgers(TEST_COMPANY)
		self.assertEqual(
			(again["groups_created"], again["renamed"], again["moved"], again["created"]), ([], [], [], [])
		)
