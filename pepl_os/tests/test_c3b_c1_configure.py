"""C3b-C1 - Quality configuration: the Quality Settings sheet and the sign-off matrix in practice."""

import frappe

from pepl_os.pepl_quality import calibration as cal
from pepl_os.pepl_quality import capa, config, incoming_qc, ncr
from pepl_os.pepl_quality.params import validate_quality_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import SYSTEM_PARAMETERS, PEPLTestCase, make_user, set_param, set_single

ROLE = "PEPL T C1 Approver"
OWNER = "pepl.t.c1.owner@example.com"
SIGNER = "pepl.t.c1.signer@example.com"


def _rows():
	return {r.fieldname or r.setting: r for r in config.settings_rows()}


class TestQualityConfigure(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		if not frappe.db.exists("Role", ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(
				ignore_permissions=True
			)

	def setUp(self):
		for severity, field in ncr.SIGNOFF_FIELDS.items():
			set_param(field, ncr.SIGNOFF_DEFAULTS[severity])
		set_param(capa.TARGET_FIELD, 30)
		set_param(cal.ALERT_FIELD, 15)
		set_param(incoming_qc.CLASSES_FIELD, "")
		set_param(ncr.OWNER_FIELD, make_user(OWNER, ["Quality Manager"]))

	def test_every_quality_setting_with_value_default_and_status(self):
		set_param(capa.TARGET_FIELD, 45)
		rows = _rows()
		for f in config.quality_fields():
			if f["fieldtype"] not in config.NO_VALUE:
				self.assertIn(f["fieldname"], rows)
		target = rows[capa.TARGET_FIELD]
		self.assertEqual(
			(target.value, target.default, target.status, target.colour),
			("45", "30", "Changed from default", "green"),
		)
		alert = rows[cal.ALERT_FIELD]
		self.assertEqual(
			(alert.value, alert.status, alert.colour), ("15", "Default, to confirm with PEPL", "orange")
		)
		self.assertEqual(alert.area, "Instruments and Calibration")
		major = rows[ncr.SIGNOFF_FIELDS[ncr.MAJOR]]
		self.assertEqual(major.value, "Quality Manager, Manufacturing Manager")
		self.assertEqual(major.status, "Default, to confirm with PEPL")
		classes = rows[incoming_qc.CLASSES_FIELD]
		self.assertTrue(classes.status.startswith("Empty: to set with PEPL"))
		self.assertEqual(rows[ncr.RATE_FIELD].setting, "NCR: Rejection Rate Threshold %")
		self.assertTrue(frappe.db.exists("Report", "PEPL Quality Settings"))

	def test_signoff_matrix_in_practice(self):
		set_param(ncr.SIGNOFF_FIELDS[ncr.MAJOR], "Quality Manager")  # only roles this test controls
		set_param(ncr.SIGNOFF_FIELDS[ncr.CRITICAL], f"Quality Manager\n{ROLE}")
		row = _rows()[f"{ROLE} signs Critical NCRs"]
		self.assertEqual(
			(row.value, row.status, row.colour),
			("nobody", "No user holds this role: Critical NCRs can never be closed", "red"),
		)
		self.assertEqual(config.unheld_roles(), {ROLE: [ncr.CRITICAL]})
		qm = _rows()["Quality Manager signs Minor, Major, Critical NCRs"]
		self.assertEqual((qm.status, qm.colour), ("Ready", "green"))
		self.assertIn("user(s): ", qm.value)

		doc = frappe.get_doc(SYSTEM_PARAMETERS)
		frappe.clear_messages()
		validate_quality_params(doc)  # a warning, not a refusal
		self.assertIn(f"no user holds the role {ROLE}", " ".join(str(m) for m in frappe.message_log))

		make_user(SIGNER, [ROLE])
		row = _rows()[f"{ROLE} signs Critical NCRs"]
		self.assertEqual((row.value, row.status), (f"1 user(s): {SIGNER}", "Ready"))
		self.assertEqual(config.unheld_roles(), {})

	def test_owner_and_stock_settings(self):
		self.assertEqual(_rows()[ncr.OWNER_FIELD].status, "Set")
		set_param(ncr.OWNER_FIELD, None)
		set_param("notification_fallback_owner", OWNER)
		owner = _rows()[ncr.OWNER_FIELD]
		self.assertEqual(
			(owner.status, owner.colour),
			(f"Not set: Quality ToDos go to the Notification Fallback Owner ({OWNER})", "orange"),
		)
		incoming_qc.switch_stock_settings_once()
		for field in incoming_qc.STOCK_SETTINGS_ACTIONS:
			set_single("Stock Settings", field, "Warn")
		rows = _rows()
		for field in incoming_qc.STOCK_SETTINGS_ACTIONS:
			self.assertEqual((rows[field].status, rows[field].colour), ("As PEPL OS expects", "green"))
		set_single("Stock Settings", incoming_qc.STOCK_SETTINGS_ACTIONS[0], "Stop")
		row = _rows()[incoming_qc.STOCK_SETTINGS_ACTIONS[0]]
		self.assertEqual(row.colour, "red")
		self.assertTrue(row.status.startswith("Different"))

	def test_master_data_rows(self):
		item = make_item("PEPL-T-C1-BARE", st.BOUGHT_OUT, valuation_rate=10).name
		frappe.db.set_value("Item", item, incoming_qc.FLAG, 1)
		frappe.db.set_value("Item", item, incoming_qc.TEMPLATE, None)
		row = _rows()[incoming_qc.FLAG]
		self.assertEqual(row.colour, "orange")
		self.assertIn("without an inspection plan", row.status)
		code = "PEPL-T-C1-GAUGE"
		if frappe.db.exists(cal.INSTRUMENT, code):
			frappe.delete_doc(cal.INSTRUMENT, code, force=True)
		frappe.get_doc(
			{
				"doctype": cal.INSTRUMENT,
				"instrument_id": code,
				"instrument_name": "Gauge",
				"calibration_frequency_days": 30,
			}
		).insert(ignore_permissions=True)
		row = next(r for r in config.settings_rows() if r.setting == "Instruments (not scrapped)")
		self.assertEqual(row.colour, "orange")
		self.assertIn("overdue or never calibrated", row.status)
