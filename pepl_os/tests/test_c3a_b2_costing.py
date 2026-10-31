"""C3a-B2 - Estimate vs actual cost: the CST estimate a piece against what a Job Order really cost a piece."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, now, today

from pepl_os.pepl_production import costing
from pepl_os.pepl_production import machine_week as mw
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_bom,
	make_downtime_category,
	make_item,
	make_job_card,
	make_operator,
	make_rm_group,
	make_shift,
	make_spr,
	make_workstation,
	test_warehouse,
)
from pepl_os.tests.utils import PEPLTestCase, set_param, set_single

DAY = "T-B2 Day"  # 08:00-16:30, 30 min break
MILL = "T-B2 MILL-01"
GROUP = "T-B2 MILL"
OP1 = "T-B2-OP1"
NO_LOAD = "T-B2 No Load"
OIL = "T-B2-COOLANT"
RM_GROUP = "T-B2 Brass Rod"
REPORT = "PEPL Estimate vs Actual Cost"


def _receipt(item_code, store, qty, rate):
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"purpose": "Material Receipt",
			"company": TEST_COMPANY,
			"set_posting_time": 1,
			"posting_date": add_days(today(), -5),
			"items": [
				{"item_code": item_code, "qty": qty, "t_warehouse": test_warehouse(store), "basic_rate": rate}
			],
		}
	).insert(ignore_permissions=True)
	entry.submit()
	return entry


def make_cst(
	item_code, status="Approved", costing_date=None, components=None, overhead_percent=10, product=None
):
	"""A PEPL CST Cost Sheet for `item_code` (through a Product Master linked to the item)."""
	make_rm_group(RM_GROUP)
	if not product:
		product = frappe.db.get_value("PEPL Product Master", {"linked_item": item_code}, "name")
	if not product:
		product = (
			frappe.get_doc(
				{
					"doctype": "PEPL Product Master",
					"product_name": "T-B2 Product " + item_code,
					"product_type": "Single Component",
					"status": "Active",
					"linked_item": item_code,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	doc = frappe.get_doc(
		{
			"doctype": costing.CST,
			"cst_title": "T-B2 " + item_code,
			"linked_product": product,
			"linked_item": item_code,
			"status": status,
			"costing_date": costing_date or today(),
			"overhead_percent": overhead_percent,
			"components": components
			or [
				{
					"manufactured_or_bought_out": "Manufactured",
					"rm_group": RM_GROUP,
					"quantity_per_assembly": 1,
					"raw_material_cost": 12,
					"machining_cost": 250,
					"surface_treatment_cost": 20,
					"component_other_charges": 5,
				}
			],
		}
	).insert(ignore_permissions=True)
	return doc


class TestCosting(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(MILL, GROUP)
		make_operator(OP1, pin="2222")
		make_downtime_category(NO_LOAD, "Planned", 0)
		make_item(OIL, st.CONSUMABLES, valuation_rate=10)
		_receipt(OIL, "Consumables Stores", 100, 10)
		# 10 pieces at 6 standard minutes; the BOM's raw material costs 10 a piece
		cls.card = make_job_card(MILL, "T-B2-JC", qty=10, minutes_per_piece=6)
		cls.item = cls.card.production_item
		cls.job_order = cls.card.work_order

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")
		set_param(mw.OVERHEAD_FIELD, 10)
		set_param(costing.WARNING_FIELD, 10)
		set_single("Manufacturing Settings", "overproduction_percentage_for_work_order", 0)
		frappe.db.delete("PEPL Machine Hour Rate", {"parent": mw.SYSTEM_PARAMETERS, "machine_group": GROUP})
		frappe.get_doc(
			{
				"doctype": "PEPL Machine Hour Rate",
				"name": "t-b2-rate-mill",
				"parent": mw.SYSTEM_PARAMETERS,
				"parenttype": mw.SYSTEM_PARAMETERS,
				"parentfield": mw.RATES_FIELD,
				"machine_group": GROUP,
				"rate_per_hour": 600,
			}
		).db_insert()

	def _shift(self):
		"""4 h on the Job Card: 8 good, 2 rejected; 3 litres of coolant (30)."""
		doc = make_spr(
			MILL,
			DAY,
			OP1,
			today(),
			production=[
				{
					"job_card": self.card.name,
					"from_time": "08:00",
					"to_time": "12:00",
					"good_qty": 8,
					"rejected_qty": 2,
					"rejection_reason": "Undersize",
				}
			],
			downtime=[{"downtime_category": NO_LOAD, "from_time": "12:00", "to_time": "16:30"}],
			consumables=[{"item_code": OIL, "qty": 3}],
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def _row(self, **filters):
		found = [r for r in costing.rows({"job_order": self.job_order, **filters})]
		self.assertEqual(len(found), 1)
		return found[0]

	# ---- the estimate ----
	def test_estimate_adds_up_as_the_cst_does(self):
		sheet = {
			"overhead_amount": 30,
			"tender_other_charges": 7,
			"components": [
				{
					"manufactured_or_bought_out": "Manufactured",
					"raw_material_cost": 12,
					"machining_cost": 250,
					"surface_treatment_cost": 20,
					"component_other_charges": 5,
					"bought_out_cost": 99,  # not counted on a manufactured component (the CST ignores it too)
				},
				{
					"manufactured_or_bought_out": "Bought Out",
					"bought_out_cost": 40,
					"surface_treatment_cost": 3,
					"machining_cost": 99,  # not counted on a bought-out component
				},
				{"manufactured_or_bought_out": "", "raw_material_cost": 500},  # no type: nothing in the CST
			],
		}
		est = costing.estimate_from_sheet(sheet)
		self.assertEqual(
			(est["material"], est["machining"], est["other"], est["overhead"], est["total"]),
			(52, 250, 35, 30, 367),
		)

	def test_estimate_matches_the_saved_cst_total(self):
		doc = make_cst(self.item)
		est = costing.estimate_from_sheet(doc)
		self.assertAlmostEqual(
			est["total"],
			doc.total_components_cost + doc.overhead_amount + (doc.tender_other_charges or 0),
			places=2,
		)
		self.assertAlmostEqual(est["total"], 315.7, places=2)  # 287 + 10 % overhead

	def test_latest_approved_cst_is_the_estimate_and_drafts_are_not(self):
		self.assertEqual(costing.choose_sheet(self.item), (None, None))
		make_cst(self.item, status="Draft")
		self.assertEqual(costing.choose_sheet(self.item), (None, None))
		older = make_cst(self.item, status="Approved", costing_date=add_days(today(), -30))
		newer = make_cst(self.item, status="Used in Bid", costing_date=add_days(today(), -2))
		name, basis = costing.choose_sheet(self.item)
		self.assertEqual(name, newer.name)
		self.assertNotEqual(name, older.name)
		self.assertIn("Used in Bid", basis)

	def test_the_cst_of_the_sales_orders_tender_comes_first(self):
		asked = []

		def sheets(filters):
			asked.append(filters)
			return (
				[frappe._dict(name="CST-TENDER", status="Under Review")] if "linked_tender" in filters else []
			)

		with (
			patch.object(costing, "tender_of", return_value="TND-1"),
			patch.object(costing, "_sheets", sheets),
		):
			name, basis = costing.choose_sheet(self.item, "SO-1")
		self.assertEqual(name, "CST-TENDER")
		self.assertIn("TND-1", basis)
		self.assertEqual(asked[0]["linked_tender"], "TND-1")
		self.assertEqual(asked[0]["status"], ["not in", costing.RETIRED_STATUSES])

	# ---- the actual ----
	def test_material_is_the_consumed_value_less_scrap(self):
		rows = [
			{"s_warehouse": "RM", "basic_amount": 60},
			{"s_warehouse": "BO", "basic_amount": 25},
			{"t_warehouse": "FG", "basic_amount": 85, "is_finished_item": 1},
			{"t_warehouse": "Scrap", "basic_amount": 4, "is_scrap_item": 1},
		]
		self.assertEqual(costing.material_value(rows), 81)

	def test_erpnext_operating_cost_rows_are_left_out(self):
		rows = [
			{"description": "Plating at job worker", "base_amount": 40},
			{
				"description": "Operating Cost as per Work Order / BOM",
				"base_amount": 300,
				"has_operating_cost": 1,
			},
			{"description": "Corrective Operation Cost", "base_amount": 50, "has_corrective_cost": 1},
			{"description": "Additional Operating Cost", "base_amount": 20},
			{"description": "Freight", "amount": 6},
		]
		self.assertEqual(costing.extra_cost_value(rows), 46)

	def test_job_order_on_the_shop_floor_only(self):
		make_cst(self.item)
		self._shift()
		row = self._row()
		# material 10 x (8 + 2) = 100; machining 4 h x 600 = 2400 + coolant 30; overhead 10 % of 2530 = 253
		# total 2783 for 8 good pieces = 347.875 a piece; estimate 315.70
		self.assertEqual(row["pieces"], 8)
		self.assertAlmostEqual(row["actual_total"], 2783, places=2)
		self.assertAlmostEqual(row["act_material"], 12.5, places=2)
		self.assertAlmostEqual(row["act_machining"], 303.75, places=2)
		self.assertAlmostEqual(row["act_overhead"], 31.625, places=1)
		self.assertAlmostEqual(row["act_total"], 347.875, places=1)
		self.assertAlmostEqual(row["est_total"], 315.7, places=2)
		self.assertAlmostEqual(row["variance"], 32.18, places=1)
		self.assertEqual(row["variance_percent"], 10.2)
		self.assertEqual(row["colour"], "red")
		self.assertIn("material from the BOM", row["notes"])
		self.assertIn("none booked yet", row["notes"])

	def test_the_variance_warning_is_a_system_parameter(self):
		make_cst(self.item)
		self._shift()
		set_param(costing.WARNING_FIELD, 15)
		self.assertEqual(self._row()["colour"], "green")

	def test_no_cst_and_nothing_made_say_so(self):
		row = self._row()
		self.assertIsNone(row["est_total"])
		self.assertIsNone(row["act_total"])
		self.assertEqual(row["colour"], "gray")
		self.assertIn("Nothing made yet", row["notes"])
		self.assertIn("No CST estimate", row["notes"])

	def test_manufacture_entry_gives_material_and_extra_costs(self):
		fg = make_item("T-B2-MF-FG", st.FINISHED_GOODS).name
		rm = make_item("T-B2-MF-RM", st.RAW_MATERIAL, heat_tracked=False, valuation_rate=12).name
		make_bom(fg, rm)
		_receipt(rm, "RM Stores", 20, 12)
		wo = frappe.get_doc(
			{
				"doctype": "Work Order",
				"production_item": fg,
				"bom_no": frappe.db.get_value("BOM", {"item": fg, "is_default": 1, "docstatus": 1}),
				"qty": 5,
				"stock_uom": "Nos",
				"company": TEST_COMPANY,
				"skip_transfer": 1,
				"source_warehouse": test_warehouse("RM Stores"),
				"fg_warehouse": test_warehouse("FG Stores"),
				"planned_start_date": now(),
			}
		)
		wo.get_items_and_operations_from_bom()
		wo.insert(ignore_permissions=True)
		wo.submit()
		from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

		entry = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", 5))
		account = frappe.get_cached_value(
			"Company", TEST_COMPANY, "stock_adjustment_account"
		) or frappe.db.get_value("Account", {"company": TEST_COMPANY, "root_type": "Expense", "is_group": 0})
		entry.append(
			"additional_costs",
			{"expense_account": account, "description": "Plating at job worker", "amount": 40},
		)
		entry.insert(ignore_permissions=True)
		entry.submit()
		act = costing.actual_for(wo.name)
		# material 5 x 12 = 60; job work 40; no shop floor; overhead 10 % of 100 = 10
		self.assertEqual(act.pieces, 5)
		self.assertAlmostEqual(act.material, 60, places=2)
		self.assertAlmostEqual(act.other, 40, places=2)
		self.assertAlmostEqual(act.machining, 0, places=2)
		self.assertAlmostEqual(act.total, 110, places=2)
		self.assertNotIn("material from the BOM", "; ".join(act.notes))

	# ---- by item ----
	def test_by_item_adds_job_orders_together(self):
		est = {"material": 10, "machining": 20, "other": 0, "overhead": 3, "total": 33}

		def job(pieces, total):
			act = {"material": total / 2, "machining": total / 2, "other": 0, "overhead": 0, "total": total}
			return costing._row(
				{"job_order": "JO", "item_code": "X", "item_name": "X", "cst": "CST-1", "notes": ""},
				est,
				act,
				pieces,
				10,
			)

		rows = costing.by_item([job(10, 300), job(30, 1020), job(0, 50)], 10)
		self.assertEqual(len(rows), 1)
		row = rows[0]
		self.assertEqual((row["job_orders"], row["pieces"]), (3, 40))
		self.assertAlmostEqual(row["actual_total"], 1370, places=2)
		self.assertAlmostEqual(
			row["act_total"], 34.25, places=2
		)  # 1370 / 40 (a job not yet made still costs)
		self.assertAlmostEqual(row["est_total"], 33, places=2)
		self.assertEqual(row["variance_percent"], 3.8)
		self.assertEqual(row["colour"], "green")

	# ---- report and settings ----
	def test_report_columns_and_message(self):
		from pepl_os.pepl_production.report.pepl_estimate_vs_actual_cost import (
			pepl_estimate_vs_actual_cost as report,
		)

		make_cst(self.item)
		self._shift()
		columns, data, message = report.execute({"job_order": self.job_order})
		names = [c["fieldname"] for c in columns]
		self.assertEqual(names[:2], ["job_order", "item_code"])
		self.assertIn("variance_percent", names)
		self.assertEqual(len(data), 1)
		self.assertIn("1 of 1 row(s) over", message)
		columns, data, message = report.execute({"job_order": self.job_order, "group_by": "Item"})
		self.assertNotIn("job_order", [c["fieldname"] for c in columns])
		self.assertEqual((len(data), data[0]["item_code"]), (1, self.item))
		self.assertTrue(frappe.db.exists("Report", REPORT))

	def test_variance_warning_must_be_a_sensible_percent(self):
		doc = frappe.get_doc(mw.SYSTEM_PARAMETERS)
		for bad in (0, 150):
			doc.set(costing.WARNING_FIELD, bad)
			with self.assertRaisesRegex(frappe.ValidationError, "Costing: Variance Warning"):
				validate_production_params(doc)
		doc.set(costing.WARNING_FIELD, 10)
		validate_production_params(doc)

	def test_the_setting_has_its_default(self):
		field = frappe.get_meta(mw.SYSTEM_PARAMETERS).get_field(costing.WARNING_FIELD)
		self.assertEqual((field.fieldtype, str(field.default)), ("Percent", "10"))
