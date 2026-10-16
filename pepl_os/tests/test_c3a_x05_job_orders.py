"""C3a-X5 - A submitted Sales Order drafts a Job Order (Work Order) for each manufactured line with a BOM."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, getdate, now, today

from pepl_os.pepl_production import job_orders as jo
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_bom,
	make_item,
	make_sales_order,
	make_workstation,
	test_warehouse,
)
from pepl_os.tests.utils import PEPLTestCase, set_param

FG = "T-JO-FG-SHAFT"  # manufactured, has a default BOM
FG2 = "T-JO-FG-FLANGE"  # manufactured, has a default BOM
ROUTED = "T-JO-FG-ROUTED"  # manufactured, BOM with an operation on a machine
NO_BOM = "T-JO-FG-NOBOM"  # manufactured, no BOM yet
BOUGHT = "T-JO-BO-BEARING"  # bought-out: never a Job Order
RM = "T-JO-RM-ROD"
OWNER = "Administrator"


def _job_orders(so_name, docstatus=0):
	return frappe.get_all(
		"Work Order",
		filters={"sales_order": so_name, "docstatus": docstatus},
		fields=[
			"name",
			"production_item",
			"qty",
			"bom_no",
			"sales_order_item",
			"fg_warehouse",
			"wip_warehouse",
			"expected_delivery_date",
			jo.AUTO_FIELD,
		],
		order_by="production_item",
	)


def _todos(so_name, rule):
	return frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Sales Order",
			"reference_name": so_name,
			"status": "Open",
			"description": ["like", f"%{rule}%"],
		},
		pluck="description",
	)


class TestJobOrdersFromSalesOrder(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		rm = make_item(RM, st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10).name
		for code in (FG, FG2, NO_BOM):
			make_item(code, st.FINISHED_GOODS)
		make_item(BOUGHT, st.BOUGHT_OUT)
		make_bom(FG, rm)
		make_bom(FG2, rm)
		make_item(ROUTED, st.FINISHED_GOODS)
		make_workstation("T-JO VMC-01", "T-JO VMC")
		make_bom(ROUTED, rm, "T-JO VMC-01", "T-JO Milling", 12)

	def setUp(self):
		set_param(jo.ENABLE_FIELD, 1)
		set_param("enable_operational_todos", 1)
		set_param("custom_production_notification_owner", OWNER)

	def test_submit_drafts_one_job_order_per_manufactured_line(self):
		so = make_sales_order([(FG, 5), (FG2, 3), (BOUGHT, 2)], submit=True)
		rows = _job_orders(so.name)
		self.assertEqual([(r.production_item, r.qty) for r in rows], [(FG2, 3), (FG, 5)])
		line = {r.item_code: r for r in so.items}
		shaft = next(r for r in rows if r.production_item == FG)
		self.assertEqual(shaft.sales_order_item, line[FG].name)
		self.assertEqual(
			shaft.bom_no, frappe.db.get_value("BOM", {"item": FG, "is_default": 1, "docstatus": 1})
		)
		self.assertEqual(shaft.fg_warehouse, test_warehouse("FG Stores"))
		self.assertEqual(shaft.wip_warehouse, test_warehouse("WIP Main Workshop"))
		self.assertEqual(getdate(shaft.expected_delivery_date), getdate(add_days(today(), 10)))
		self.assertEqual(shaft.get(jo.AUTO_FIELD), 1)

	def test_job_order_carries_the_bom_operations(self):
		so = make_sales_order([(ROUTED, 5)], submit=True)
		name = _job_orders(so.name)[0].name
		ops = frappe.get_all(
			"Work Order Operation", filters={"parent": name}, fields=["operation", "workstation"]
		)
		self.assertEqual([(o.operation, o.workstation) for o in ops], [("T-JO Milling", "T-JO VMC-01")])

	def test_bought_out_only_order_makes_no_job_order(self):
		so = make_sales_order([(BOUGHT, 4)], submit=True)
		self.assertEqual(_job_orders(so.name), [])

	def test_manufactured_line_without_bom_is_flagged_to_production(self):
		so = make_sales_order([(NO_BOM, 2), (FG, 1)], submit=True)
		self.assertEqual([r.production_item for r in _job_orders(so.name)], [FG])
		todos = _todos(so.name, jo.NO_BOM_RULE)
		self.assertEqual(len(todos), 1)
		self.assertIn(NO_BOM, todos[0])

	def test_running_again_creates_nothing_new(self):
		so = make_sales_order([(FG, 5)], submit=True)
		self.assertEqual(jo.draft_job_orders(so), {"created": [], "no_bom": []})
		self.assertEqual(len(_job_orders(so.name)), 1)

	def test_only_the_quantity_not_yet_on_a_job_order(self):
		set_param(jo.ENABLE_FIELD, 0)
		so = make_sales_order([(FG, 10)], submit=True)
		self.assertEqual(_job_orders(so.name), [])
		manual = frappe.get_doc(
			{
				"doctype": "Work Order",
				"production_item": FG,
				"bom_no": frappe.db.get_value("BOM", {"item": FG, "is_default": 1, "docstatus": 1}),
				"qty": 4,
				"company": TEST_COMPANY,
				"sales_order": so.name,
				"sales_order_item": so.items[0].name,
				"fg_warehouse": test_warehouse("FG Stores"),
				"planned_start_date": now(),
			}
		).insert(ignore_permissions=True)
		set_param(jo.ENABLE_FIELD, 1)
		result = jo.draft_job_orders(so)
		self.assertEqual(len(result["created"]), 1)
		self.assertEqual(frappe.db.get_value("Work Order", result["created"][0], "qty"), 6)
		self.assertEqual(frappe.db.get_value("Work Order", manual.name, jo.AUTO_FIELD), 0)

	def test_switched_off_in_system_parameters(self):
		set_param(jo.ENABLE_FIELD, 0)
		so = make_sales_order([(FG, 5)], submit=True)
		self.assertEqual(_job_orders(so.name), [])

	def test_cancelling_the_order_removes_its_draft_job_orders(self):
		so = make_sales_order([(FG, 5), (FG2, 1)], submit=True)
		names = [r.name for r in _job_orders(so.name)]
		self.assertEqual(len(names), 2)
		so.reload()
		so.cancel()
		for name in names:
			self.assertFalse(frappe.db.exists("Work Order", name))

	def test_failure_never_blocks_the_sales_order(self):
		so = make_sales_order([(FG, 1)])
		with patch.object(jo, "draft_job_orders", side_effect=RuntimeError("boom")):
			so.submit()  # no exception
		self.assertEqual(so.docstatus, 1)
		self.assertEqual(len(_todos(so.name, jo.FAILED_RULE)), 1)

	def test_hooks_registered(self):
		events = frappe.get_hooks("doc_events")["Sales Order"]
		self.assertIn("pepl_os.pepl_production.job_orders.on_sales_order_submit", events["on_submit"])
		self.assertIn("pepl_os.pepl_production.job_orders.on_sales_order_cancel", events["on_cancel"])
		# C2-07 keeps running on submit too
		self.assertIn("pepl_os.pepl_purchase.material_request.on_sales_order_submit", events["on_submit"])

	def test_parameter_seeded_on(self):
		from pepl_os.tests.utils import stored_single

		self.assertIsNotNone(stored_single("PEPL System Parameters", jo.ENABLE_FIELD))
