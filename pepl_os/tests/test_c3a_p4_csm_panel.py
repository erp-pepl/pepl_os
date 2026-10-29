"""C3a-P4 - Customer-supplied material panel on the Job Order."""

import frappe
from frappe.utils import now

from pepl_os.pepl_production import csm_consumption as cc
from pepl_os.pepl_production import csm_panel as cp
from pepl_os.pepl_stores import csm
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_bom,
	make_item,
	make_sales_order,
	make_work_order,
	test_warehouse,
)
from pepl_os.tests.utils import PEPLTestCase, set_param

STEEL = "T-P4-CSM-STEEL"  # customer's bar, Kg, no heat tracking
SHAFT = "T-P4-FG-SHAFT"  # 2 Kg of steel a piece
PLAIN = "T-P4-FG-PLAIN"  # PEPL's own material only
OWN_RM = "T-P4-RM-OWN"


def _stock_entry(item, qty, sales_order, entry_type="Material Receipt"):
	purpose = frappe.db.get_value("Stock Entry Type", entry_type, "purpose")
	row = {"item_code": item, "qty": qty, "basic_rate": 0}
	if purpose == "Material Receipt":
		row["t_warehouse"] = test_warehouse("CSM Stores")
	else:
		row["s_warehouse"] = test_warehouse("CSM Stores")
	doc = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": entry_type,
			"purpose": purpose,
			"company": TEST_COMPANY,
			"custom_sales_order": sales_order,
			"items": [row],
		}
	).insert(ignore_permissions=True)
	doc.submit()
	return doc


def _job_orders(so):
	return frappe.get_all(
		"Work Order", filters={"sales_order": so.name, "docstatus": 0}, pluck="name", order_by="creation"
	)


def _texts(rows):
	return " | ".join(r["text"] for r in rows)


class TestJobOrderCSMPanel(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		csm.ensure_return_type()
		make_item(STEEL, st.CSM, heat_tracked=False, stock_uom="Kg")
		own = make_item(OWN_RM, st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10).name
		for fg in (SHAFT, PLAIN):
			make_item(fg, st.FINISHED_GOODS)
		make_bom(SHAFT, STEEL, rm_qty=2)
		make_bom(PLAIN, own)

	def setUp(self):
		set_param(cc.TOLERANCE_FIELD, 0.5)
		set_param("custom_job_order_from_sales_order", 1)

	def _order(self, lines, received=0):
		so = make_sales_order(lines, submit=True)
		if received:
			_stock_entry(STEEL, received, so.name)
		return so

	def test_a_job_order_without_customer_material_has_no_panel(self):
		so = self._order([(PLAIN, 10)])
		self.assertEqual(cp.panel_rows(_job_orders(so)[0]), [])

	def test_enough_for_what_is_still_to_make(self):
		so = self._order([(SHAFT, 10)], received=25)
		rows = cp.panel_rows(_job_orders(so)[0])
		self.assertEqual(rows[0]["colour"], "green")
		self.assertIn(f"Sales Order {so.name} holds enough", rows[0]["text"])
		self.assertIn(
			f"{STEEL}: 2 Kg a piece x 10 still to make = 20 Kg; the order holds 25 Kg (enough for 12 pieces)",
			rows[1]["text"],
		)
		self.assertEqual(rows[1]["colour"], "green")

	def test_short_for_this_job_order(self):
		so = self._order([(SHAFT, 10)], received=15)
		rows = cp.panel_rows(_job_orders(so)[0])
		self.assertEqual(rows[0]["colour"], "red")
		self.assertIn("does not hold enough", rows[0]["text"])
		self.assertIn("short by 5 Kg", rows[1]["text"])
		self.assertIn("(enough for 7 pieces)", rows[1]["text"])

	def test_enough_for_this_job_order_not_for_the_whole_order(self):
		so = self._order([(SHAFT, 10), (SHAFT, 5)], received=25)
		first = _job_orders(so)[0]
		self.assertEqual(frappe.db.get_value("Work Order", first, "qty"), 10)
		rows = cp.panel_rows(first)
		self.assertEqual(rows[0]["colour"], "orange")
		self.assertIn("the whole order still needs 30 Kg", rows[1]["text"])

	def test_material_already_issued_to_production_counts(self):
		so = self._order([(SHAFT, 10)], received=25)
		_stock_entry(STEEL, 18, so.name, "Material Issue")  # 18 Kg already on the shop floor
		line = cp.lines(_job_orders(so)[0])[0]
		self.assertEqual((line.held, line.issued, line.still_needed, line.state), (7, 18, 2, "enough"))
		text = _texts(cp.panel_rows(_job_orders(so)[0]))
		self.assertIn("= 20 Kg (2 Kg after what is already issued)", text)
		self.assertIn("issued or consumed so far 18 Kg", text)

	def test_tolerance(self):
		so = self._order([(SHAFT, 10)], received=19.7)
		self.assertEqual(cp.lines(_job_orders(so)[0])[0].state, "enough")
		set_param(cc.TOLERANCE_FIELD, 0)
		self.assertEqual(cp.lines(_job_orders(so)[0])[0].state, "short")

	def test_pieces_already_made_need_nothing(self):
		so = self._order([(SHAFT, 10)], received=25)
		name = _job_orders(so)[0]
		frappe.db.set_value("Work Order", name, "produced_qty", 4)
		line = cp.lines(name)[0]
		self.assertEqual((line.remaining, line.wo_need), (6, 12))

	def test_customer_material_without_a_sales_order(self):
		wo = make_work_order(SHAFT, 5, now(), submit=False)
		rows = cp.panel_rows(wo.name)
		self.assertEqual((len(rows), rows[0]["colour"]), (1, "red"))
		self.assertIn("has no Sales Order", rows[0]["text"])

	def test_form_api(self):
		so = self._order([(SHAFT, 10)], received=25)
		self.assertTrue(cp.get_job_order_csm_panel(_job_orders(so)[0])["rows"])

	def test_panel_hooked_on_the_form(self):
		self.assertIn("public/js/work_order.js", str(frappe.get_hooks("doctype_js").get("Work Order")))
