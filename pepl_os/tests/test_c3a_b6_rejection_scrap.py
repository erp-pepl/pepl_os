"""C3a-B6 - Rejected pieces on a submitted shift entry go to the Scrap Register by themselves."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_production import rejection_scrap as rs
from pepl_os.pepl_production import spr
from pepl_os.pepl_stores import scrap
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_downtime_category,
	make_item,
	make_job_card,
	make_operator,
	make_shift,
	make_spr,
	make_workstation,
)
from pepl_os.tests.utils import PEPLTestCase, set_param

DAY = "T-B6 Day"
MILL = "T-B6 MILL-01"
OP = "T-B6-OP1"
NO_LOAD = "T-B6 No Load"
BRASS = "T-B6-SCRAP-BRASS"
STEEL = "T-B6-SCRAP-STEEL"
YESTERDAY = add_days(today(), -1)


class TestRejectionScrap(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		scrap.ensure_scrap_masters()
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(MILL)
		make_operator(OP, pin="6543")
		make_downtime_category(NO_LOAD, "Planned", 0)
		make_item(BRASS, "Brass Scrap", stock_uom="Kg")
		make_item(STEEL, "Steel Scrap", stock_uom="Kg")
		for item in (BRASS, STEEL):
			if not frappe.db.exists(scrap.RATE, {"scrap_item": item}):
				frappe.get_doc(
					{
						"doctype": scrap.RATE,
						"scrap_item": item,
						"rate": 40,
						"effective_from": add_days(today(), -30),
					}
				).insert(ignore_permissions=True)
		cls.card = make_job_card(MILL, "T-B6-JC", qty=40, minutes_per_piece=6)
		cls.item = cls.card.production_item

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")
		set_param("enable_operational_todos", 1)
		set_param(rs.ENABLE_FIELD, 1)
		set_param(rs.FALLBACK_FIELD, "")
		frappe.db.set_value(
			"Item", self.item, {"weight_per_unit": 0.25, "weight_uom": "Kg", rs.ITEM_FIELD: BRASS}
		)
		frappe.clear_document_cache("Item", self.item)

	def _submit(self, rejected=4, good=8, on=YESTERDAY):
		row = {"job_card": self.card.name, "from_time": "08:00", "to_time": "10:00", "good_qty": good}
		if rejected:
			row.update({"rejected_qty": rejected, "rejection_reason": "Undersize"})
		doc = make_spr(
			MILL,
			DAY,
			OP,
			on,
			production=[row],
			downtime=[{"downtime_category": NO_LOAD, "from_time": "10:00", "to_time": "16:30"}],
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def _weighments(self, doc, docstatus=1):
		return frappe.get_all(
			scrap.WEIGHMENT,
			filters={rs.LINK_FIELD: doc.name, "docstatus": docstatus},
			fields=[
				"name",
				"source",
				"scrap_item",
				"net_kg",
				"rate_applied",
				"amount",
				"rejected_pieces",
				"stock_entry",
			],
		)

	def _todos(self, doc, status="Open"):
		return frappe.get_all(
			"ToDo",
			filters={
				"reference_type": rs.SPR,
				"reference_name": doc.name,
				"status": status,
				"description": ["like", f"%{rs.RULE}%"],
			},
			pluck="description",
		)

	def test_rejected_pieces_become_a_scrap_weighment(self):
		doc = self._submit(rejected=4)
		rows = self._weighments(doc)
		self.assertEqual(len(rows), 1)
		w = rows[0]
		self.assertEqual((w.source, w.scrap_item, w.rejected_pieces), (scrap.REJECTION, BRASS, 4))
		self.assertAlmostEqual(w.net_kg, 1.0, places=3)  # 4 x 0.25 kg
		self.assertEqual((w.rate_applied, w.amount), (40, 40))
		self.assertEqual(frappe.db.get_value("Stock Entry", w.stock_entry, "docstatus"), 1)  # into Scrap Yard
		texts = [r["text"] for r in spr.panel_rows(frappe.get_doc(rs.SPR, doc.name))]
		self.assertIn(f"4 rejected piece(s) → Scrap Weighment {w.name}: 1 kg {BRASS}", texts)
		self.assertEqual(self._todos(doc), [])

	def test_weight_in_grams(self):
		frappe.db.set_value("Item", self.item, {"weight_per_unit": 500, "weight_uom": "Gram"})
		self.assertAlmostEqual(rs.kg_per_piece(self.item), 0.5, places=6)
		frappe.db.set_value("Item", self.item, {"weight_per_unit": 2, "weight_uom": "Nos"})
		self.assertIsNone(rs.kg_per_piece(self.item))  # not a weight

	def test_no_weight_per_unit_gives_stores_a_todo(self):
		frappe.db.set_value("Item", self.item, "weight_per_unit", 0)
		doc = self._submit(rejected=3)
		self.assertEqual(self._weighments(doc), [])
		todos = self._todos(doc)
		self.assertEqual(len(todos), 1)
		self.assertIn("3 rejected piece(s)", todos[0])
		self.assertIn("weight per unit of", todos[0])
		texts = [r["text"] for r in spr.panel_rows(frappe.get_doc(rs.SPR, doc.name))]
		self.assertIn("Rejected pieces waiting for Stores to weigh (ToDo)", texts)

	def test_the_system_parameter_scrap_item_is_the_fallback(self):
		frappe.db.set_value("Item", self.item, rs.ITEM_FIELD, None)
		set_param(rs.FALLBACK_FIELD, STEEL)
		doc = self._submit(rejected=2)
		self.assertEqual(self._weighments(doc)[0].scrap_item, STEEL)

	def test_no_scrap_item_at_all_gives_a_todo(self):
		frappe.db.set_value("Item", self.item, rs.ITEM_FIELD, None)
		doc = self._submit(rejected=2)
		self.assertEqual(self._weighments(doc), [])
		self.assertIn("scrap item", self._todos(doc)[0])

	def test_missing_scrap_rate_gives_a_todo(self):
		frappe.db.delete(scrap.RATE, {"scrap_item": BRASS})
		doc = self._submit(rejected=2)
		self.assertEqual(self._weighments(doc), [])
		self.assertIn(f"scrap rate of {BRASS}", self._todos(doc)[0])

	def test_switched_off_or_nothing_rejected_does_nothing(self):
		set_param(rs.ENABLE_FIELD, 0)
		doc = self._submit(rejected=2)
		self.assertEqual((self._weighments(doc), self._todos(doc)), ([], []))
		set_param(rs.ENABLE_FIELD, 1)
		doc = self._submit(rejected=0, good=10, on=add_days(today(), -2))  # another day: no overlap
		self.assertEqual((self._weighments(doc), self._todos(doc)), ([], []))

	def test_cancelling_the_entry_takes_the_scrap_back(self):
		doc = self._submit(rejected=4)
		name = self._weighments(doc)[0].name
		frappe.get_doc(rs.SPR, doc.name).cancel()
		self.assertEqual(frappe.db.get_value(scrap.WEIGHMENT, name, "docstatus"), 2)
		frappe.db.set_value("Item", self.item, "weight_per_unit", 0)
		doc = self._submit(rejected=4)
		self.assertTrue(self._todos(doc))
		frappe.get_doc(rs.SPR, doc.name).cancel()
		self.assertEqual(self._todos(doc), [])
		self.assertTrue(self._todos(doc, "Cancelled"))

	def test_settings_exist_with_defaults(self):
		meta = frappe.get_meta("PEPL System Parameters")
		self.assertEqual(str(meta.get_field(rs.ENABLE_FIELD).default), "1")
		self.assertEqual(meta.get_field(rs.FALLBACK_FIELD).options, "Item")
		self.assertTrue(frappe.get_meta("Item").get_field(rs.ITEM_FIELD))
		self.assertTrue(frappe.get_meta(scrap.WEIGHMENT).get_field(rs.LINK_FIELD))
