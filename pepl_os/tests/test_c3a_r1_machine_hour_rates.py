"""C3a-R1 - Machine-Hour Rates are linked to the machine group (Workstation Type)."""

import frappe

from pepl_os.pepl_production import machine_hour_rates as mhr
from pepl_os.pepl_production import machine_week as mw
from pepl_os.tests.factories import make_workstation, make_workstation_type
from pepl_os.tests.utils import PEPLTestCase

VMC = "T-R1 VMC"
VMC_01 = "T-R1 VMC-01"


def _row(group, rate, name):
	frappe.get_doc(
		{
			"doctype": mhr.RATE_DOCTYPE,
			"name": name,
			"parent": mhr.SYSTEM_PARAMETERS,
			"parenttype": mhr.SYSTEM_PARAMETERS,
			"parentfield": mhr.RATES_FIELD,
			"machine_group": group,
			"rate_per_hour": rate,
			"idx": 90,
		}
	).db_insert()
	return name


class TestMachineHourRateLinks(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_workstation_type(VMC)
		make_workstation(VMC_01, VMC)

	def test_the_group_is_a_link_to_the_machine_group(self):
		field = frappe.get_meta(mhr.RATE_DOCTYPE).get_field("machine_group")
		self.assertEqual((field.fieldtype, field.options), ("Link", "Workstation Type"))

	def test_old_rows_are_moved_across(self):
		typed = _row("t-r1 vmc", 650, "t-r1-typed")  # typed in another case
		missing = _row("T-R1 Gear Hobbing", 800, "t-r1-missing")  # no such machine group yet
		result = mhr.link_rate_groups()
		self.assertEqual(frappe.db.get_value(mhr.RATE_DOCTYPE, typed, "machine_group"), VMC)
		self.assertTrue(frappe.db.exists("Workstation Type", "T-R1 Gear Hobbing"))
		self.assertEqual(frappe.db.get_value(mhr.RATE_DOCTYPE, missing, "machine_group"), "T-R1 Gear Hobbing")
		self.assertIn("T-R1 Gear Hobbing", result["created"])
		self.assertIn("t-r1 vmc -> T-R1 VMC", result["renamed"])

	def test_moving_again_changes_nothing(self):
		_row(VMC, 650, "t-r1-linked")
		mhr.link_rate_groups()
		self.assertEqual(mhr.link_rate_groups(), {"renamed": [], "created": []})

	def test_a_machine_takes_its_group_rate(self):
		_row(VMC, 650, "t-r1-rate")
		self.assertEqual(mhr.rate_for_group(VMC), 650)
		rate, source = mw.machine_rate(VMC_01)
		self.assertEqual(rate, 650)
		self.assertIn(VMC, source)

	def test_a_group_without_a_rate_falls_back_to_the_machine(self):
		frappe.db.set_value("Workstation", VMC_01, "hour_rate", 300)
		self.assertIsNone(mhr.rate_for_group(VMC))
		self.assertEqual(mw.machine_rate(VMC_01)[0], 300)

	def test_patch_registered(self):
		with open(frappe.get_app_path("pepl_os", "patches.txt")) as f:
			self.assertIn("pepl_os.patches.v0_34.link_machine_hour_rate_groups", f.read())
