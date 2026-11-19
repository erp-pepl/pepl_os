"""C3b-T1 - Cycle 3b health check: is the Quality chain set up and doing its job on live records?"""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_quality import calibration as cal
from pepl_os.pepl_quality import capa, ncr
from pepl_os.pepl_quality import health_check as hc
from pepl_os.pepl_quality import incoming_qc as qc
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import PEPLTestCase, set_param

SINCE = add_days(today(), -60)
ROLE = "PEPL T T1 Nobody"


def _checks(check, sheet, record=None):
	return [r["check"] for r in check[sheet] if record is None or r.get("record") == record]


def _ncr(item, severity="Minor", **fields):
	return frappe.get_doc(
		{
			"doctype": ncr.NCR,
			"source": "In-Process",
			"severity": severity,
			"item": item,
			"qty_affected": 1,
			"defect_description": "Burr",
			**fields,
		}
	).insert(ignore_permissions=True)


class TestCycle3bHealthCheck(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		if not frappe.db.exists("Role", ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(
				ignore_permissions=True
			)

	def setUp(self):
		set_param(capa.VERIFY_FIELD, 90)
		set_param(capa.WHYS_FIELD, 1)
		for severity, field in ncr.SIGNOFF_FIELDS.items():
			set_param(field, ncr.SIGNOFF_DEFAULTS[severity])

	def test_eight_sheets_read_only(self):
		before = frappe.db.count("ToDo")
		check = hc.build_health_check(SINCE)
		self.assertEqual(list(check), [title for title, _cols in hc.SHEETS])
		self.assertEqual(frappe.db.count("ToDo"), before)
		self.assertEqual(set(hc.findings(check)), set(check))
		self.assertTrue(all(r["check"] in hc.INFO_CHECKS for r in check["8 Usage"]))

	def test_settings_findings(self):
		set_param(ncr.SIGNOFF_FIELDS[ncr.CRITICAL], f"Quality Manager\n{ROLE}")
		check = hc.build_health_check(SINCE)
		self.assertIn(
			"Will not work as it is", _checks(check, "1 Settings and people", f"{ROLE} signs Critical NCRs")
		)
		self.assertTrue(
			any(
				r["check"] == "Setting at its default, to confirm with PEPL"
				for r in check["1 Settings and people"]
			)
		)

	def test_inspection_instrument_and_ncr_findings(self):
		bare = make_item("PEPL-T-T1Q-BARE", st.BOUGHT_OUT, valuation_rate=10).name
		frappe.db.set_value("Item", bare, {qc.FLAG: 1, qc.TEMPLATE: None})
		code = "PEPL-T-T1Q-GAUGE"
		if frappe.db.exists(cal.INSTRUMENT, code):
			frappe.delete_doc(cal.INSTRUMENT, code, force=True)
		frappe.get_doc(
			{
				"doctype": cal.INSTRUMENT,
				"instrument_id": code,
				"instrument_name": code,
				"calibration_frequency_days": 30,
			}
		).insert(ignore_permissions=True)
		old = _ncr(bare, raised_on=add_days(today(), -45))
		costless = _ncr(bare, disposition="Scrap")
		check = hc.build_health_check(SINCE)
		self.assertIn(
			"Item inspected on receipt without an inspection plan", _checks(check, "2 Inspection", bare)
		)
		self.assertIn("Instrument never calibrated", _checks(check, "3 Instruments", code))
		self.assertIn("NCR open more than 30 days", _checks(check, "4 NCR and CAPA", old.name))
		self.assertIn("NCR without its cost", _checks(check, "4 NCR and CAPA", costless.name))

	def test_capa_findings(self):
		item = make_item("PEPL-T-T1Q-CAPA", st.BOUGHT_OUT, valuation_rate=10).name
		doc = frappe.get_doc(capa.CAPA, frappe.db.get_value(ncr.NCR, _ncr(item, "Critical").name, "capa"))
		frappe.db.set_value(capa.CAPA, doc.name, "target_date", add_days(today(), -3))
		check = hc.build_health_check(SINCE)
		self.assertIn("CAPA past its target", _checks(check, "4 NCR and CAPA", doc.name))
		doc.reload()
		doc.why_1 = "Collet worn"
		doc.root_cause = "No collet change interval"
		doc.append("actions", {"action_type": capa.CORRECTIVE, "description": "PM list", "done_on": today()})
		doc.status = capa.CLOSED
		doc.save()
		frappe.db.set_value(capa.CAPA, doc.name, "verification_due_on", add_days(today(), -1))
		check = hc.build_health_check(SINCE)
		self.assertIn("CAPA effectiveness check overdue", _checks(check, "4 NCR and CAPA", doc.name))

	def test_download_is_an_excel_file(self):
		hc.download_health_check(SINCE)
		self.assertTrue(frappe.response["filename"].startswith("PEPL Cycle 3b health check"))
		self.assertEqual(frappe.response["filecontent"][:2], b"PK")
		out = hc.run_health_check(SINCE)
		self.assertEqual(set(out["findings"]), set(out["rows"]))
