"""C3a-X9 - Customer-supplied material consumed by the Delivery Note; the Delivery Note material gate."""

from unittest.mock import patch

import frappe

from pepl_os.pepl_production import csm_consumption as cc
from pepl_os.pepl_stores import csm, heat
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_bom,
	make_delivery_note,
	make_item,
	make_sales_order,
	test_warehouse,
)
from pepl_os.tests.utils import PEPLTestCase, set_param

STEEL = "T-X9-CSM-STEEL"  # customer's bar, no heat tracking
FORGING = "T-X9-CSM-FORGING"  # customer's material with heat numbers (Batch = heat)
SHAFT = "T-X9-FG-SHAFT"  # 2 x steel a piece
FLANGE = "T-X9-FG-FLANGE"  # 1.5 x forging a piece
PLAIN = "T-X9-FG-PLAIN"  # PEPL's own material only
OWN_RM = "T-X9-RM-OWN"


def _stock_entry(rows, sales_order=None, entry_type="Material Receipt"):
	purpose = frappe.db.get_value("Stock Entry Type", entry_type, "purpose")
	doc = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": entry_type,
			"purpose": purpose,
			"company": TEST_COMPANY,
			"custom_sales_order": sales_order,
			"items": [
				{
					"item_code": r["item"],
					"qty": r["qty"],
					"s_warehouse": test_warehouse(r["from"]) if r.get("from") else None,
					"t_warehouse": test_warehouse(r["to"]) if r.get("to") else None,
					"basic_rate": r.get("rate", 0),
					heat.HEAT_FIELD: r.get("heat"),
				}
				for r in rows
			],
		}
	).insert(ignore_permissions=True)
	doc.submit()
	return doc


class TestCSMConsumedByDelivery(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		csm.ensure_return_type()
		# customer material is weighed: stock unit Kg (fractions allowed)
		make_item(STEEL, st.CSM, heat_tracked=False, stock_uom="Kg")
		make_item(FORGING, st.CSM, stock_uom="Kg")
		own = make_item(OWN_RM, st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10).name
		for fg in (SHAFT, FLANGE, PLAIN):
			make_item(fg, st.FINISHED_GOODS)
		make_bom(SHAFT, STEEL, rm_qty=2)
		make_bom(FLANGE, FORGING, rm_qty=1.5)
		make_bom(PLAIN, own)
		_stock_entry(
			[{"item": fg, "qty": 100, "to": "FG Stores", "rate": 100} for fg in (SHAFT, FLANGE, PLAIN)]
		)

	def setUp(self):
		set_param(cc.GATE_FIELD, cc.WARN)
		set_param(cc.TOLERANCE_FIELD, 0.5)
		set_param("custom_heat_number_gate_mode", heat.HARD_BLOCK)
		set_param("enable_operational_todos", 1)
		set_param(cc.OWNER_FIELD, "Administrator")

	def _order(self, lines, steel=0, forging_heat=None, forging=0):
		so = make_sales_order(lines, submit=True)
		rows = []
		if steel:
			rows.append({"item": STEEL, "qty": steel, "to": "CSM Stores"})
		if forging:
			rows.append({"item": FORGING, "qty": forging, "to": "CSM Stores", "heat": forging_heat})
		if rows:
			_stock_entry(rows, so.name)
		return so

	def _balance(self, so, item):
		rows = [r for r in csm.csm_balance({"sales_order": so.name}) if r.item_code == item]
		return rows[0] if rows else None

	def _issues(self, dn):
		return frappe.get_all("Stock Entry", filters={cc.DN_FIELD: dn.name, "docstatus": 1}, pluck="name")

	# ---- consumption ----
	def test_delivery_consumes_the_customer_material_it_used(self):
		so = self._order([(SHAFT, 10)], steel=25)
		dn = make_delivery_note(so.name, {SHAFT: 5}, submit=True)
		issues = self._issues(dn)
		self.assertEqual(len(issues), 1)
		entry = frappe.get_doc("Stock Entry", issues[0])
		self.assertEqual((entry.purpose, entry.custom_sales_order), ("Material Issue", so.name))
		self.assertEqual(
			[(r.item_code, r.qty, r.s_warehouse) for r in entry.items],
			[(STEEL, 10, test_warehouse("CSM Stores"))],
		)
		balance = self._balance(so, STEEL)
		self.assertEqual((balance.issued, balance.balance), (10, 15))

	def test_second_delivery_consumes_only_its_own_share(self):
		so = self._order([(SHAFT, 10)], steel=25)
		make_delivery_note(so.name, {SHAFT: 5}, submit=True)
		dn = make_delivery_note(so.name, {SHAFT: 3}, submit=True)
		entry = frappe.get_doc("Stock Entry", self._issues(dn)[0])
		self.assertEqual(entry.items[0].qty, 6)
		self.assertEqual(self._balance(so, STEEL).issued, 16)

	def test_material_already_issued_to_production_counts(self):
		so = self._order([(SHAFT, 10)], steel=25)
		_stock_entry([{"item": STEEL, "qty": 8, "from": "CSM Stores"}], so.name, "Material Issue")
		dn = make_delivery_note(so.name, {SHAFT: 5}, submit=True)
		self.assertEqual(frappe.get_doc("Stock Entry", self._issues(dn)[0]).items[0].qty, 2)

	def test_heat_lot_follows_the_material(self):
		so = self._order([(FLANGE, 10)], forging=20, forging_heat="X9-H1")
		dn = make_delivery_note(so.name, {FLANGE: 4}, submit=True)
		row = frappe.get_doc("Stock Entry", self._issues(dn)[0]).items[0]
		self.assertEqual((row.item_code, row.qty), (FORGING, 6))
		self.assertEqual(frappe.db.get_value("Batch", row.batch_no, heat.HEAT_FIELD), "X9-H1")
		self.assertEqual(row.get(heat.HEAT_FIELD), "X9-H1")

	def test_parts_from_pepl_material_consume_nothing(self):
		so = self._order([(PLAIN, 10)])
		dn = make_delivery_note(so.name, {PLAIN: 5}, submit=True)
		self.assertEqual(self._issues(dn), [])
		self.assertFalse(dn.get(cc.SUMMARY_FIELD))

	def test_cancelling_the_delivery_cancels_the_issue(self):
		so = self._order([(SHAFT, 10)], steel=25)
		dn = make_delivery_note(so.name, {SHAFT: 5}, submit=True)
		issue = self._issues(dn)[0]
		dn.reload()
		dn.cancel()
		self.assertEqual(frappe.db.get_value("Stock Entry", issue, "docstatus"), 2)
		self.assertEqual(self._balance(so, STEEL).balance, 25)

	def test_summary_on_the_delivery_note(self):
		so = self._order([(SHAFT, 10)], steel=25)
		dn = make_delivery_note(so.name, {SHAFT: 5})
		self.assertIn(STEEL, dn.get(cc.SUMMARY_FIELD))
		preview = cc.consumption_preview(dn.name)
		self.assertEqual(preview["orders"][so.name][0].to_consume, 10)

	# ---- the gate ----
	def test_warn_mode_saves_but_will_not_submit_when_material_is_short(self):
		so = self._order([(SHAFT, 10)], steel=8)
		dn = make_delivery_note(so.name, {SHAFT: 5})  # needs 10, the order holds 8
		self.assertTrue(dn.name)
		with self.assertRaisesRegex(frappe.ValidationError, "does not cover"):
			dn.submit()

	def test_hard_block_will_not_even_save(self):
		set_param(cc.GATE_FIELD, cc.HARD)
		so = self._order([(SHAFT, 10)], steel=8)
		with self.assertRaisesRegex(frappe.ValidationError, "Hard Block"):
			make_delivery_note(so.name, {SHAFT: 5})

	def test_gate_off_delivers_and_consumes_what_there_is(self):
		set_param(cc.GATE_FIELD, cc.OFF)
		so = self._order([(SHAFT, 10)], steel=8)
		dn = make_delivery_note(so.name, {SHAFT: 5}, submit=True)
		self.assertEqual(frappe.get_doc("Stock Entry", self._issues(dn)[0]).items[0].qty, 8)

	def test_difference_within_tolerance_is_ignored(self):
		so = self._order([(SHAFT, 10)], steel=9.7)  # needs 10: short 0.3, tolerance 0.5
		dn = make_delivery_note(so.name, {SHAFT: 5}, submit=True)
		self.assertEqual(dn.docstatus, 1)
		self.assertAlmostEqual(frappe.get_doc("Stock Entry", self._issues(dn)[0]).items[0].qty, 9.7, places=3)

	def test_a_failure_never_stops_the_delivery(self):
		so = self._order([(SHAFT, 10)], steel=25)
		with patch.object(cc, "consume", side_effect=RuntimeError("boom")):
			dn = make_delivery_note(so.name, {SHAFT: 5}, submit=True)
		self.assertEqual(dn.docstatus, 1)
		todos = frappe.get_all(
			"ToDo",
			filters={"reference_type": "Delivery Note", "reference_name": dn.name, "status": "Open"},
			pluck="description",
		)
		self.assertEqual(len(todos), 1)

	def test_hooks_registered(self):
		events = frappe.get_hooks("doc_events")["Delivery Note"]
		for event, method in (
			("validate", "validate_delivery_note"),
			("before_submit", "before_submit_delivery_note"),
			("on_submit", "on_submit_delivery_note"),
			("on_cancel", "on_cancel_delivery_note"),
		):
			self.assertIn(f"pepl_os.pepl_production.csm_consumption.{method}", events[event])
		self.assertIn("pepl_os.pepl_stores.stock_tree.validate_csm_segregation", events["validate"])
