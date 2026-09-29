"""C2-02 Purchase & Stores rulebook, C2-03 supplier fields."""

import frappe

from pepl_os.common import params
from pepl_os.common.rights import YES, combine
from pepl_os.pepl_purchase.params import validate_purchase_params
from pepl_os.setup.custom_fields import CUSTOM_FIELDS, PURCHASE_STORES_FIELDS, SYSTEM_PARAMETERS
from pepl_os.setup.permissions import perm_rows
from pepl_os.tests.factories import make_rm_group, make_supplier
from pepl_os.tests.utils import PEPLTestCase


def _params(**values):
	doc = frappe.get_doc(SYSTEM_PARAMETERS)
	doc.update(values)
	return doc


class TestPurchaseParams(PEPLTestCase):
	def test_every_field_is_on_the_parameters(self):
		meta = frappe.get_meta(SYSTEM_PARAMETERS)
		for field in PURCHASE_STORES_FIELDS:
			self.assertTrue(meta.has_field(field["fieldname"]), field["fieldname"])

	def test_defaults_are_readable(self):
		self.assertEqual(params.get_int("custom_msme_payment_days"), 45)
		self.assertEqual(params.get("custom_msme_clock_basis"), "Bill Date")
		self.assertEqual(params.get("custom_heat_number_gate_mode"), "Hard Block")
		self.assertEqual(params.get_int("custom_supplier_doc_expiry_alert_days"), 30)
		self.assertEqual(params.get_float("custom_abc_a_value_percent"), 80)
		self.assertEqual(params.get_float("custom_abc_b_value_percent"), 15)
		self.assertTrue(params.is_enabled("custom_enforce_override_reason", 0))

	def test_pepl_owned_values_have_no_default(self):
		for fieldname in (
			"custom_po_approval_value_threshold",
			"custom_delivery_alert_lead_days",
			"custom_receipt_short_tolerance_percent",
			"custom_reorder_safety_days",
			"custom_count_variance_approval_percent",
			"custom_overhead_percent",
		):
			field = next(f for f in PURCHASE_STORES_FIELDS if f["fieldname"] == fieldname)
			self.assertNotIn("default", field, fieldname)

	def test_purchase_params_validation(self):
		validate_purchase_params(_params())  # the seeded defaults are valid
		with self.assertRaises(frappe.ValidationError):
			validate_purchase_params(_params(custom_late_grace_days=-1))
		with self.assertRaises(frappe.ValidationError):
			validate_purchase_params(_params(custom_receipt_short_tolerance_percent=120))
		with self.assertRaises(frappe.ValidationError):
			validate_purchase_params(_params(custom_abc_a_value_percent=85, custom_abc_b_value_percent=15))
		with self.assertRaises(frappe.ValidationError):
			validate_purchase_params(_params(custom_po_approval_value_threshold=-5))

	def test_machine_rates_unique_and_not_negative(self):
		doc = _params()
		doc.set("custom_machine_hour_rates", [])
		doc.append("custom_machine_hour_rates", {"machine_group": "CNC", "rate_per_hour": 450})
		validate_purchase_params(doc)
		doc.append("custom_machine_hour_rates", {"machine_group": "cnc", "rate_per_hour": 500})
		with self.assertRaises(frappe.ValidationError):
			validate_purchase_params(doc)

	def test_validation_is_hooked(self):
		events = frappe.get_hooks("doc_events")[SYSTEM_PARAMETERS]["validate"]
		self.assertIn("pepl_os.pepl_purchase.params.validate_purchase_params", events)

	def test_purchase_manager_reads_ceo_edits(self):
		rows = perm_rows(SYSTEM_PARAMETERS)
		self.assertEqual(combine(rows, ["Purchase Manager"])["read"], YES)
		self.assertEqual(combine(rows, ["Purchase Manager"])["write"], "")
		self.assertEqual(combine(rows, ["PEPL CEO"])["write"], YES)


class TestSupplierFields(PEPLTestCase):
	def test_fields_exist(self):
		meta = frappe.get_meta("Supplier")
		for field in CUSTOM_FIELDS["Supplier"]:
			self.assertTrue(meta.has_field(field["fieldname"]), field["fieldname"])

	def test_criticality_defaults_to_routine(self):
		supplier = make_supplier("PEPL Test Routine Supplier").insert(ignore_permissions=True)
		self.assertEqual(supplier.custom_vendor_criticality, "Routine")

	def test_udyam_required_when_msme(self):
		with self.assertRaises(frappe.ValidationError):
			make_supplier("PEPL Test MSME No Udyam", custom_is_msme=1).insert(ignore_permissions=True)

	def test_udyam_format_checked(self):
		with self.assertRaises(frappe.ValidationError):
			make_supplier("PEPL Test MSME Bad Udyam", custom_is_msme=1, custom_udyam_number="12345").insert(
				ignore_permissions=True
			)

	def test_msme_supplier_with_rm_groups_and_criticality(self):
		group = make_rm_group("PEPL-C2-BRASS")
		supplier = make_supplier(
			"PEPL Test MSME Supplier",
			custom_is_msme=1,
			custom_udyam_number="udyam-wb-10-0012345",
			custom_msme_category="Small",
			custom_vendor_criticality="Critical",
			custom_rm_groups=[{"rm_group": group.name}],
		).insert(ignore_permissions=True)
		self.assertEqual(supplier.custom_udyam_number, "UDYAM-WB-10-0012345")
		self.assertEqual([r.rm_group for r in supplier.custom_rm_groups], [group.name])
		self.assertEqual(supplier.custom_vendor_criticality, "Critical")

	def test_approval_fields_are_read_only(self):
		meta = frappe.get_meta("Supplier")
		for fieldname in (
			"custom_approval_state",
			"custom_approval_expiry",
			"custom_delivery_score",
			"custom_quality_score",
		):
			self.assertTrue(meta.get_field(fieldname).read_only, fieldname)

	def test_list_indicator_registered(self):
		self.assertIn("public/js/supplier_list.js", frappe.get_hooks("doctype_list_js")["Supplier"])
