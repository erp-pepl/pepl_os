"""C3b-B2 - Cost of Quality: rejections priced, scrap recovered, NCR rework / other / customer, by month and item."""

import frappe
from frappe.utils import add_days, get_first_day, get_last_day, today

from pepl_os.pepl_production import rejection_scrap as rs
from pepl_os.pepl_quality import coq, ncr
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

DAY = "T-COQ Day"
MILL = "T-COQ MILL-01"
OP = "T-COQ-OP1"
NO_LOAD = "T-COQ No Load"
YESTERDAY = add_days(today(), -1)
WINDOW = {"from_date": add_days(today(), -3), "to_date": today(), "group_by": "Item"}


def _by_item(item):
	return next((r for r in coq.rows(WINDOW) if r.key == item), None)


def _ncr(item, severity="Minor", **fields):
	return frappe.get_doc(
		{
			"doctype": ncr.NCR,
			"source": "In-Process",
			"severity": severity,
			"item": item,
			"qty_affected": 2,
			"raised_on": today(),
			"defect_description": "Burr",
			**fields,
		}
	).insert(ignore_permissions=True)


class TestCostOfQuality(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(MILL)
		make_operator(OP, pin="7654")
		make_downtime_category(NO_LOAD, "Planned", 0)
		cls.card = make_job_card(MILL, "T-COQ-JC", qty=60, minutes_per_piece=6)
		cls.part = cls.card.production_item

	def setUp(self):
		set_param(ncr.RATE_FIELD, 0)  # no rejection-rate NCR from the shift entries here
		set_param(rs.ENABLE_FIELD, 0)
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")
		for severity, field in ncr.SIGNOFF_FIELDS.items():
			set_param(field, ncr.SIGNOFF_DEFAULTS[severity])

	def _entry(self, good, rejected):
		doc = make_spr(
			MILL,
			DAY,
			OP,
			YESTERDAY,
			production=[
				{
					"job_card": self.card.name,
					"from_time": "08:00",
					"to_time": "10:00",
					"good_qty": good,
					"rejected_qty": rejected,
					"rejection_reason": "Undersize",
				}
			],
			downtime=[{"downtime_category": NO_LOAD, "from_time": "10:00", "to_time": "16:30"}],
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_rejections_are_priced_and_scrap_is_taken_off(self):
		frappe.db.set_value("Item", self.part, "valuation_rate", 0)
		frappe.db.delete("Bin", {"item_code": self.part})
		before = _by_item(self.part)
		base_pieces = before.rejected_pieces if before else 0
		entry = self._entry(good=8, rejected=2)
		row = _by_item(self.part)
		self.assertEqual(row.rejected_pieces - base_pieces, 2)
		self.assertIn("rejected piece(s) without a cost a piece", row.notes)
		self.assertIn(self.part, row.notes)

		frappe.db.set_value("Item", self.part, "valuation_rate", 25)
		row = _by_item(self.part)
		self.assertEqual(row.rejection, row.rejected_pieces * 25)
		self.assertNotIn("without a cost a piece", row.notes)

		weighment = frappe.get_doc(
			{
				"doctype": coq.WEIGHMENT,
				"name": f"T-COQ-W-{entry.name}",
				"company": TEST_COMPANY,
				"weighment_date": YESTERDAY,
				"source": "Rejection",
				"shift_production_entry": entry.name,
				"rejected_pieces": 2,
				"amount": 20,
				"docstatus": 1,
			}
		)
		weighment.db_insert()
		row = _by_item(self.part)
		self.assertEqual(row.scrap_recovered, 20)
		self.assertEqual(
			row.total, round(row.rejection - 20 + row.ncr_rework + row.ncr_other + row.customer, 2)
		)

	def test_ncr_costs_by_kind(self):
		item = make_item("PEPL-T-COQ-PIN", st.BOUGHT_OUT, valuation_rate=10).name
		_ncr(item, disposition="Rework", estimated_cost=100)
		_ncr(item, disposition="Scrap")  # no cost entered yet
		_ncr(item, source="Customer", disposition="Return to Supplier", estimated_cost=200)
		_ncr(
			item,
			disposition="Scrap",
			estimated_cost=999,
			status=ncr.CANCELLED,
			cancel_reason="Raised by mistake",
		)
		_ncr(item, disposition="Scrap", estimated_cost=70, raise_rule=ncr.RULE_RATE, raised_by_system=1)
		row = _by_item(item)
		self.assertEqual(
			(row.ncr_rework, row.ncr_other, row.customer, row.ncrs, row.total),
			(100, 0, 200, 3, 300),
		)
		self.assertEqual(row.notes, "1 NCR(s) without a cost")

	def test_by_month_and_this_months_total(self):
		item = make_item("PEPL-T-COQ-MONTH", st.BOUGHT_OUT, valuation_rate=10).name
		month = {"from_date": get_first_day(today()), "to_date": get_last_day(today())}
		before = coq.month_total()
		_ncr(item, disposition="Rework", estimated_cost=45)
		self.assertEqual(round(coq.month_total() - before, 2), 45)
		rows = coq.rows(month)
		self.assertEqual([r.key for r in rows], [today()[:7]])
		self.assertEqual(rows[0].total, coq.month_total())
		from pepl_os.pepl_quality.report.pepl_cost_of_quality import pepl_cost_of_quality as report

		result = report.execute(month)
		self.assertEqual(len(result), 5)
		self.assertEqual(result[4][0]["value"], coq.month_total())
		self.assertTrue(frappe.db.exists("Report", "PEPL Cost of Quality"))
