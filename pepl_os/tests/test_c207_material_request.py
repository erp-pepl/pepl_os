"""C2-07 - Sales Order drafts its Material Request; the MR panel."""

from unittest.mock import patch

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from frappe.utils import add_days, today

from pepl_os.pepl_purchase import material_request as mr
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, set_param

CUSTOMER = "_Test Customer"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _sales_order(lines):
	return frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": CUSTOMER,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"delivery_date": add_days(today(), 10),
			"custom_sector": "Private",
			"items": [
				{
					"item_code": code,
					"qty": qty,
					"rate": 100,
					"warehouse": _wh("FG Stores"),
					"delivery_date": add_days(today(), 10),
				}
				for code, qty in lines
			],
		}
	).insert(ignore_permissions=True)


class TestMaterialRequestFromSalesOrder(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item("PEPL-T-BO-1", st.BOUGHT_OUT)
		make_item("PEPL-T-FG-1", st.FINISHED_GOODS)
		# One raw material per test: stock added in one test stays for the rest of the class.
		make_item("PEPL-T-RM-SHORT", st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10)
		make_item("PEPL-T-RM-COVERED", st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10)

	def test_so_submit_creates_one_draft_mr(self):
		so = _sales_order([("PEPL-T-BO-1", 4), ("PEPL-T-FG-1", 2)])
		name = mr.draft_material_request(so)
		doc = frappe.get_doc("Material Request", name)
		self.assertEqual(doc.docstatus, 0)
		self.assertEqual(doc.material_request_type, "Purchase")
		self.assertEqual(doc.custom_sales_order, so.name)
		self.assertEqual([(r.item_code, r.qty) for r in doc.items], [("PEPL-T-BO-1", 4)])
		self.assertEqual(doc.items[0].warehouse, _wh("Bought-Out Stores"))
		self.assertEqual(doc.items[0].sales_order, so.name)

	def test_second_submit_path_does_not_duplicate(self):
		so = _sales_order([("PEPL-T-BO-1", 1)])
		first = mr.draft_material_request(so)
		self.assertEqual(mr.draft_material_request(so), first)
		self.assertEqual(frappe.db.count("Material Request", {"custom_sales_order": so.name}), 1)

	def test_manufactured_items_not_in_mr(self):
		so = _sales_order([("PEPL-T-FG-1", 3)])
		self.assertIsNone(mr.draft_material_request(so))

	def test_raw_material_only_the_shortfall(self):
		make_stock_entry(
			item_code="PEPL-T-RM-SHORT", qty=3, to_warehouse=_wh("RM Stores"), company=TEST_COMPANY, rate=10
		)
		so = _sales_order([("PEPL-T-RM-SHORT", 5)])
		doc = frappe.get_doc("Material Request", mr.draft_material_request(so))
		self.assertEqual([(r.item_code, r.qty) for r in doc.items], [("PEPL-T-RM-SHORT", 2)])

	def test_raw_material_covered_by_stock_not_requested(self):
		make_stock_entry(
			item_code="PEPL-T-RM-COVERED",
			qty=20,
			to_warehouse=_wh("RM Stores"),
			company=TEST_COMPANY,
			rate=10,
		)
		so = _sales_order([("PEPL-T-RM-COVERED", 5)])
		self.assertIsNone(mr.draft_material_request(so))

	def test_hook_registered(self):
		self.assertIn(
			"pepl_os.pepl_purchase.material_request.on_sales_order_submit",
			frappe.get_hooks("doc_events")["Sales Order"]["on_submit"],
		)

	def test_failure_never_blocks_the_sales_order(self):
		set_param("enable_operational_todos", 1)
		set_param("custom_purchase_notification_owner", "Administrator")
		so = _sales_order([("PEPL-T-BO-1", 1)])
		with patch.object(mr, "draft_material_request", side_effect=RuntimeError("boom")):
			mr.on_sales_order_submit(so)  # no exception
		self.assertTrue(
			frappe.db.exists(
				"ToDo",
				{
					"reference_type": "Sales Order",
					"reference_name": so.name,
					"status": "Open",
					"description": ["like", "%PUR-MR-DRAFT-FAILED%"],
				},
			)
		)

	def test_mr_panel_counts_approved_suppliers(self):
		group = frappe.get_doc(
			{
				"doctype": "PEPL RM Group",
				"group_name": "PEPL-T-FASTENERS",
				"material_base": "Hardware",
				"default_uom": "Nos",
				"auto_sync_to_item_group": 1,
			}
		).insert(ignore_permissions=True)
		st.seed_item_groups()
		make_item("PEPL-T-BOLT", group.linked_item_group)
		so = _sales_order([("PEPL-T-BOLT", 10)])
		name = mr.draft_material_request(so)
		line = mr.get_mr_panel(name)[0]
		self.assertEqual((line["rm_group"], line["approved_suppliers"]), (group.name, 0))

		supplier = make_supplier(
			"PEPL Test Bolt Supplier", custom_rm_groups=[{"rm_group": group.name}]
		).insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", supplier.name, "custom_approval_state", "Approved")
		self.assertEqual(mr.get_mr_panel(name)[0]["approved_suppliers"], 1)
