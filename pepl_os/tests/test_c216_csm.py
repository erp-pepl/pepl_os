"""C2-16 - Customer-supplied material against its Sales Order; scrap option; CSM Balance by Order."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_stores import csm, heat
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import PEPLTestCase, set_param

CUSTOMER = "_Test Customer"
STEEL = "PEPL-T-CSM-STEEL"
HEAT_STEEL = "PEPL-T-CSM-HEAT"
FG = "PEPL-T-CSM-FG"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _sales_order():
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
	return so


def _entry(rows, sales_order=None, stock_entry_type="Material Receipt"):
	purpose = frappe.db.get_value("Stock Entry Type", stock_entry_type, "purpose")
	return frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": stock_entry_type,
			"purpose": purpose,
			"company": TEST_COMPANY,
			"custom_sales_order": sales_order,
			"items": [
				{
					"item_code": row.get("item", STEEL),
					"qty": row["qty"],
					"s_warehouse": _wh(row["from"]) if row.get("from") else None,
					"t_warehouse": _wh(row["to"]) if row.get("to") else None,
					"custom_heat_number": row.get("heat"),
					"batch_no": row.get("batch"),
					"use_serial_batch_fields": 1 if row.get("batch") else 0,
				}
				for row in rows
			],
		}
	)


def _stock_value():
	return frappe.db.sql(
		"select ifnull(sum(stock_value_difference), 0) from `tabStock Ledger Entry` where company = %s and is_cancelled = 0",
		TEST_COMPANY,
	)[0][0]


class TestCustomerSuppliedMaterial(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		csm.ensure_return_type()
		make_item(STEEL, st.CSM, heat_tracked=False)
		make_item(HEAT_STEEL, st.CSM)
		make_item(FG, st.FINISHED_GOODS)

	def setUp(self):
		set_param("custom_heat_number_gate_mode", heat.HARD_BLOCK)

	def test_csm_stock_entry_requires_sales_order(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			_entry([{"qty": 10, "to": "CSM Stores"}]).insert(ignore_permissions=True)
		self.assertIn("Sales Order", str(ctx.exception))
		draft = _sales_order()
		draft.cancel()
		with self.assertRaises(frappe.ValidationError):
			_entry([{"qty": 10, "to": "CSM Stores"}], draft.name).insert(ignore_permissions=True)
		so = _sales_order()
		entry = _entry([{"qty": 10, "to": "CSM Stores"}], so.name).insert(ignore_permissions=True)
		entry.submit()
		self.assertEqual(entry.docstatus, 1)

	def test_csm_receipt_value_zero(self):
		so = _sales_order()
		before = _stock_value()
		entry = _entry([{"qty": 500, "to": "CSM Stores"}], so.name).insert(ignore_permissions=True)
		entry.submit()
		sle = frappe.get_all(
			"Stock Ledger Entry",
			filters={"voucher_no": entry.name, "is_cancelled": 0},
			fields=["actual_qty", "valuation_rate", "stock_value_difference"],
		)
		self.assertEqual(
			[(r.actual_qty, r.valuation_rate, r.stock_value_difference) for r in sle], [(500, 0, 0)]
		)
		self.assertEqual(_stock_value(), before)
		values = frappe.db.get_value(
			"Sales Order", so.name, [csm.HAS_CSM_FIELD, csm.DISPOSITION_FIELD], as_dict=True
		)
		self.assertEqual((values.custom_has_csm, values.custom_csm_scrap_disposition), (1, csm.HOLD))
		entry.cancel()
		self.assertEqual(frappe.db.get_value("Sales Order", so.name, csm.HAS_CSM_FIELD), 0)

	def test_csm_heat_number_applies(self):
		so = _sales_order()
		entry = _entry([{"item": HEAT_STEEL, "qty": 20, "to": "CSM Stores"}], so.name).insert(
			ignore_permissions=True
		)
		with self.assertRaises(frappe.ValidationError):
			entry.submit()  # Hard Block: no heat number
		entry = _entry([{"item": HEAT_STEEL, "qty": 20, "to": "CSM Stores", "heat": "CSM-H-1"}], so.name)
		entry.insert(ignore_permissions=True)
		entry.submit()
		batch = entry.items[0].batch_no
		self.assertEqual(frappe.db.get_value("Batch", batch, heat.HEAT_FIELD), "CSM-H-1")

	def test_csm_balance_by_order(self):
		so = _sales_order()
		other = _sales_order()
		_entry([{"qty": 500, "to": "CSM Stores"}], so.name).insert(ignore_permissions=True).submit()
		_entry([{"qty": 70, "to": "CSM Stores"}], other.name).insert(ignore_permissions=True).submit()
		_entry([{"qty": 300, "from": "CSM Stores"}], so.name, "Material Issue").insert(
			ignore_permissions=True
		).submit()
		_entry([{"qty": 40, "from": "CSM Stores", "to": "CSM Scrap"}], so.name, "Material Transfer").insert(
			ignore_permissions=True
		).submit()
		_entry([{"qty": 60, "from": "CSM Stores"}], so.name, csm.RETURN_TYPE).insert(
			ignore_permissions=True
		).submit()
		_entry([{"qty": 15, "from": "CSM Scrap"}], so.name, csm.RETURN_TYPE).insert(
			ignore_permissions=True
		).submit()
		rows = {r.sales_order: r for r in csm.csm_balance({"company": TEST_COMPANY, "item_code": STEEL})}
		mine = rows[so.name]
		self.assertEqual(
			(mine.received, mine.issued, mine.scrapped, mine.returned, mine.balance, mine.scrap_on_hand),
			(500, 300, 40, 75, 100, 25),
		)
		self.assertEqual(mine.balance_value, 0)
		self.assertEqual(mine.scrap_disposition, csm.HOLD)
		self.assertEqual((rows[other.name].received, rows[other.name].balance), (70, 70))

	def test_return_type_is_for_csm_only(self):
		make_item("PEPL-T-CSM-BO", st.BOUGHT_OUT)
		with self.assertRaises(frappe.ValidationError) as ctx:
			_entry(
				[{"item": "PEPL-T-CSM-BO", "qty": 1, "from": "Bought-Out Stores"}], None, csm.RETURN_TYPE
			).insert(ignore_permissions=True)
		self.assertIn("only for customer-supplied", str(ctx.exception))

	def test_from_customer_provided_request_the_order_comes_along(self):
		so = _sales_order()
		request = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Customer Provided",
				"customer": CUSTOMER,
				"custom_sales_order": so.name,
				"company": TEST_COMPANY,
				"transaction_date": today(),
				"schedule_date": add_days(today(), 3),
				"items": [
					{
						"item_code": STEEL,
						"qty": 25,
						"uom": "Nos",
						"conversion_factor": 1,
						"schedule_date": add_days(today(), 3),
						"warehouse": _wh("CSM Stores"),
					}
				],
			}
		).insert(ignore_permissions=True)
		request.submit()
		from erpnext.stock.doctype.material_request.material_request import make_stock_entry

		entry = make_stock_entry(request.name)
		entry.insert(ignore_permissions=True)
		self.assertEqual((entry.purpose, entry.custom_sales_order), ("Material Receipt", so.name))
