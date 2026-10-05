"""C2-18 - Scrap Register: rates, weighments, sales, the CSM scrap rule and the recovery report."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_stores import csm, scrap
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import PEPLTestCase

BRASS = "PEPL-T-SCRAP-BRASS-TURN"
CSM_BRASS = "PEPL-T-CSM-SCRAP-BRASS"
FG = "PEPL-T-SCRAP-FG"
CUSTOMER = "_Test Customer"
BUYER = "PEPL T Scrap Buyer"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _rate(item, rate, effective):
	return frappe.get_doc(
		{"doctype": scrap.RATE, "scrap_item": item, "rate": rate, "effective_from": effective}
	).insert(ignore_permissions=True)


def _weigh(item, gross, tare, source=scrap.PROCESS, sales_order=None, submit=True, on=None):
	doc = frappe.get_doc(
		{
			"doctype": scrap.WEIGHMENT,
			"company": TEST_COMPANY,
			"weighment_date": on or today(),
			"source": source,
			"scrap_item": item,
			"gross_kg": gross,
			"tare_kg": tare,
			"sales_order": sales_order,
		}
	).insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def _sale(lines, on=None):
	return frappe.get_doc(
		{
			"doctype": scrap.SALE,
			"company": TEST_COMPANY,
			"sale_date": on or today(),
			"buyer": BUYER,
			"vehicle_number": "MH12AB1234",
			"items": lines,
		}
	)


def _sales_order(option=None):
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": CUSTOMER,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"delivery_date": add_days(today(), 10),
			"custom_sector": "Private",
			"items": [
				{
					"item_code": FG,
					"qty": 1,
					"rate": 100,
					"warehouse": _wh("FG Stores"),
					"delivery_date": add_days(today(), 10),
				}
			],
		}
	).insert(ignore_permissions=True)
	so.submit()
	if option:
		frappe.db.set_value("Sales Order", so.name, csm.DISPOSITION_FIELD, option)
	return so


class TestScrapRegister(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		csm.ensure_return_type()
		scrap.ensure_scrap_masters()
		make_item(BRASS, "Brass Scrap")
		make_item(CSM_BRASS, scrap.CSM_SCRAP_GROUP)
		make_item(FG, st.FINISHED_GOODS)
		if not frappe.db.exists("Customer", BUYER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": BUYER,
					"customer_group": scrap.SCRAP_BUYERS,
					"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
				}
			).insert(ignore_permissions=True)

	def setUp(self):
		if not scrap.rate_on(BRASS, add_days(today(), -40)):
			_rate(BRASS, 400, add_days(today(), -60))

	def test_net_weight_computed_and_positive(self):
		doc = _weigh(BRASS, 150, 30, submit=False)
		self.assertEqual(doc.net_kg, 120)
		with self.assertRaises(frappe.ValidationError):
			_weigh(BRASS, 30, 30, submit=False)

	def test_weighment_posts_receipt_at_current_rate(self):
		_rate(BRASS, 450, today())
		doc = _weigh(BRASS, 150, 30)
		self.assertEqual(doc.rate_applied, 450)
		sle = frappe.get_all(
			"Stock Ledger Entry",
			filters={"voucher_no": doc.stock_entry, "is_cancelled": 0},
			fields=["warehouse", "actual_qty", "incoming_rate"],
		)
		# incoming_rate is this receipt's rate; valuation_rate is the moving average of all the
		# brass scrap already in the yard (other tests receive some at 400), so it is not 450.
		self.assertEqual(
			[(r.warehouse, r.actual_qty, r.incoming_rate) for r in sle], [(_wh("Scrap Yard"), 120, 450)]
		)
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Stock Entry", doc.stock_entry, "docstatus"), 2)

	def test_csm_weighment_zero_value_needs_so(self):
		with self.assertRaises(frappe.ValidationError):
			_weigh(CSM_BRASS, 50, 10, source=scrap.SOURCE_CSM, submit=False)
		so = _sales_order()
		doc = _weigh(CSM_BRASS, 50, 10, source=scrap.SOURCE_CSM, sales_order=so.name)
		sle = frappe.get_all(
			"Stock Ledger Entry",
			filters={"voucher_no": doc.stock_entry, "is_cancelled": 0},
			fields=["warehouse", "actual_qty", "stock_value_difference"],
		)
		self.assertEqual(
			[(r.warehouse, r.actual_qty, r.stock_value_difference) for r in sle], [(_wh("CSM Scrap"), 40, 0)]
		)
		self.assertEqual(frappe.db.get_value("Stock Entry", doc.stock_entry, "custom_sales_order"), so.name)

	def test_scrap_sale_issues_stock(self):
		_weigh(BRASS, 150, 30)
		sale = _sale([{"scrap_item": BRASS, "kg": 100, "rate": 480}]).insert(ignore_permissions=True)
		sale.submit()
		self.assertEqual((sale.total_kg, sale.total_amount), (100, 48000))
		entry = sale.items[0].stock_entry
		self.assertEqual(frappe.db.get_value("Stock Entry", entry, "purpose"), "Material Issue")
		self.assertEqual(sale.items[0].warehouse, _wh("Scrap Yard"))

	def test_csm_scrap_sale_refused_unless_so_allows(self):
		so = _sales_order()
		_weigh(CSM_BRASS, 50, 10, source=scrap.SOURCE_CSM, sales_order=so.name)
		with self.assertRaises(frappe.ValidationError) as ctx:
			_sale([{"scrap_item": CSM_BRASS, "kg": 10, "rate": 300, "sales_order": so.name}]).insert(
				ignore_permissions=True
			)
		self.assertIn("PEPL May Sell", str(ctx.exception))

	def test_csm_scrap_sale_allowed_when_pepl_may_sell(self):
		so = _sales_order(csm.PEPL_MAY_SELL)
		_weigh(CSM_BRASS, 50, 10, source=scrap.SOURCE_CSM, sales_order=so.name)
		sale = _sale([{"scrap_item": CSM_BRASS, "kg": 10, "rate": 300, "sales_order": so.name}]).insert(
			ignore_permissions=True
		)
		sale.submit()
		entry = frappe.get_doc("Stock Entry", sale.items[0].stock_entry)
		self.assertEqual((entry.custom_sales_order, entry.items[0].s_warehouse), (so.name, _wh("CSM Scrap")))

	def test_recovery_report_totals(self):
		before = {r.metal: r for r in scrap.scrap_recovery({"company": TEST_COMPANY})}
		_weigh(BRASS, 150, 30)
		_sale([{"scrap_item": BRASS, "kg": 100, "rate": 480}]).insert(ignore_permissions=True).submit()
		month = today()[:7]
		rows = {(r.month, r.metal): r for r in scrap.scrap_recovery({"company": TEST_COMPANY})}
		row = rows[(month, "Brass Scrap")]
		base = before.get("Brass Scrap")
		generated = row.kg_generated - (base.kg_generated if base and base.month == month else 0)
		sold = row.kg_sold - (base.kg_sold if base and base.month == month else 0)
		self.assertEqual((generated, sold), (120, 100))
		self.assertGreaterEqual(row.closing_kg, 20)
		self.assertEqual(row.avg_master_rate, scrap.rate_on(BRASS, today()))
