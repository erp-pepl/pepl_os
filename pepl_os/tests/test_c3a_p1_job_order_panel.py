"""C3a-P1 - Job Order status panel: quantity against target, routing progress, delivery, LD."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_production import job_order_panel as jop
from pepl_os.pepl_production import ld
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_bom,
	make_downtime_category,
	make_item,
	make_job_card,
	make_operator,
	make_sales_order,
	make_shift,
	make_spr,
	make_workstation,
)
from pepl_os.tests.utils import PEPLTestCase, set_param

DAY = "T-P1 Day"
MILL = "T-P1 MILL-01"
OP = "T-P1-OP1"
NO_LOAD = "T-P1 No Load"
YESTERDAY = add_days(today(), -1)


def _texts(rows):
	return " | ".join(r["text"] for r in rows)


class TestJobOrderPanel(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(MILL, "T-P1 MILL")
		make_operator(OP, pin="1111")
		make_downtime_category(NO_LOAD, "Planned", 0)

	def setUp(self):
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")

	def _report(self, card, good, rejected=0):
		row = {"job_card": card, "from_time": "08:00", "to_time": "12:00", "good_qty": good}
		if rejected:
			row.update({"rejected_qty": rejected, "rejection_reason": "Undersize"})
		doc = make_spr(
			MILL,
			DAY,
			OP,
			YESTERDAY,
			production=[row],
			downtime=[{"downtime_category": NO_LOAD, "from_time": "12:00", "to_time": "16:00"}],
		).insert(ignore_permissions=True)
		doc.submit()

	def test_quantity_and_routing(self):
		card = make_job_card(MILL, "T-P1-JC", qty=10)
		self._report(card.name, 8, 2)
		rows = jop.panel_rows(card.work_order)
		text = _texts(rows)
		self.assertIn("Made 0 of 10 (0%)", text)
		self.assertNotIn(".0 ", text)
		self.assertIn("8 good, 2 rejected", text)
		step = next(r for r in rows if "Step 1" in r["text"])
		self.assertIn("8 of 10", step["text"])
		self.assertTrue(step["text"].startswith("▶"))  # the step being worked on
		self.assertEqual(step["colour"], "blue")

	def test_delivery_days_late_and_left(self):
		card = make_job_card(MILL, "T-P1-JD", qty=10)
		frappe.db.set_value("Work Order", card.work_order, "expected_delivery_date", add_days(today(), -3))
		self.assertIn("3 days late", _texts(jop.panel_rows(card.work_order)))
		frappe.db.set_value("Work Order", card.work_order, "expected_delivery_date", add_days(today(), 5))
		self.assertIn("5 days left", _texts(jop.panel_rows(card.work_order)))

	def test_ld_on_the_sales_order_line(self):
		rm = make_item("T-P1-RM", st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10).name
		make_item("T-P1-FG", st.FINISHED_GOODS)
		make_bom("T-P1-FG", rm, MILL, "T-P1 Milling", 6)
		so = make_sales_order([("T-P1-FG", 10)], submit=True)
		wo_name = frappe.get_all("Work Order", filters={"sales_order": so.name}, pluck="name")[0]
		wo = frappe.get_doc("Work Order", wo_name)
		wo.submit()
		line = so.items[0].name
		frappe.db.set_value("Sales Order Item", line, "delivery_date", add_days(today(), -10))
		frappe.db.set_value(
			"Sales Order", so.name, {ld.APPLICABLE: 1, ld.RATE: 0.5, ld.CAP: 10, ld.PERIOD: ld.WEEK}
		)
		self.assertIn("LD so far", _texts(jop.panel_rows(wo_name)))

	def test_quantities_read_like_people_write_them(self):
		# Regression (Check 35 on the bench): the panel said "Made 0.0 of 10.0" and "8.0 good, 2.0 rejected".
		self.assertEqual(
			[jop.qty_text(v) for v in (0.0, 10.0, 8, 2.5, 0.125, 1234.0, 0.1 + 0.2)],
			["0", "10", "8", "2.5", "0.125", "1234", "0.3"],
		)

	def test_form_api(self):
		card = make_job_card(MILL, "T-P1-JE", qty=10)
		self.assertTrue(jop.get_job_order_panel(card.work_order)["rows"])

	def test_panel_hooked_on_the_form(self):
		self.assertIn("public/js/work_order.js", str(frappe.get_hooks("doctype_js").get("Work Order")))
