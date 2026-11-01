"""C3a-T1 - Cycle 3a health check: is the Production chain set up and doing its job on live records?"""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_production import health_check as hc
from pepl_os.pepl_production import ld
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	TEST_CUSTOMER,
	make_downtime_category,
	make_item,
	make_operator,
	make_shift,
	make_spr,
	make_workstation,
	test_warehouse,
)
from pepl_os.tests.utils import PEPLTestCase, set_param

DAY = "T-T1 Day"
LONE = "T-T1 LONE-01"  # a machine without a machine group
OP_NO_PIN = "T-T1-OP-NOPIN"
NO_LOAD = "T-T1 No Load"
PART = "T-T1-BO-PART"
SINCE = add_days(today(), -60)


def _checks(check, sheet, record=None):
	return [r["check"] for r in check[sheet] if record is None or r.get("record") == record]


class TestCycle3aHealthCheck(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(LONE)
		make_downtime_category(NO_LOAD, "Planned", 0)
		make_operator("T-T1-OP1", pin="8888")
		make_item(PART, st.BOUGHT_OUT, valuation_rate=50)

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")

	def test_eight_sheets_read_only(self):
		before = frappe.db.count("ToDo")
		check = hc.build_health_check(SINCE)
		self.assertEqual(list(check), [title for title, _cols in hc.SHEETS])
		self.assertEqual(frappe.db.count("ToDo"), before)
		counts = hc.findings(check)
		self.assertEqual(set(counts), set(check))

	def test_masters_findings(self):
		frappe.get_doc(
			{"doctype": "PEPL Operator", "employee_code": OP_NO_PIN, "operator_name": "No PIN"}
		).insert(ignore_permissions=True)
		check = hc.build_health_check(SINCE)
		self.assertIn("Machine without a machine group", _checks(check, "1 Shop-floor masters", LONE))
		found = _checks(check, "1 Shop-floor masters", OP_NO_PIN)
		self.assertIn("Active operator without a PIN", found)
		self.assertIn("Active operator without skills", found)
		self.assertIn("Active operator without a default shift", found)

	def test_a_draft_shift_entry_left_for_days(self):
		doc = make_spr(
			LONE,
			DAY,
			"T-T1-OP1",
			add_days(today(), -5),
			downtime=[{"downtime_category": NO_LOAD, "from_time": "08:00", "to_time": "16:30"}],
		).insert(ignore_permissions=True)
		check = hc.build_health_check(SINCE)
		self.assertIn("Shift entry not submitted after 2 days", _checks(check, "2 Shift entries", doc.name))

	def test_an_ld_sector_order_without_the_clause(self):
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": TEST_CUSTOMER,
				"company": TEST_COMPANY,
				"transaction_date": today(),
				"delivery_date": add_days(today(), 10),
				"custom_sector": "Private",
				"items": [
					{
						"item_code": PART,
						"qty": 1,
						"rate": 100,
						"warehouse": test_warehouse("Bought-Out Stores"),
						"delivery_date": add_days(today(), 10),
					}
				],
			}
		).insert(ignore_permissions=True)
		so.submit()
		set_param(ld.DEFAULT_SECTORS_FIELD, "Private")  # Private orders should have carried LD
		check = hc.build_health_check(SINCE)
		self.assertIn("Order of an LD sector without an LD clause", _checks(check, "6 LD", so.name))

	def test_settings_at_default_are_information_only(self):
		check = hc.build_health_check(SINCE)
		rows = check["8 Settings"]
		self.assertTrue(rows)
		self.assertTrue(all(r["check"] in hc.INFO_CHECKS for r in rows))
		self.assertEqual(hc.findings(check)["8 Settings"], 0)

	def test_download_is_an_excel_file(self):
		hc.download_health_check(SINCE)
		self.assertTrue(frappe.response["filename"].startswith("PEPL Cycle 3a health check"))
		self.assertEqual(frappe.response["filecontent"][:2], b"PK")  # an .xlsx is a zip
		out = hc.run_health_check(SINCE)
		self.assertEqual(set(out["findings"]), set(out["rows"]))
