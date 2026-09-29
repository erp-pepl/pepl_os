"""C2-05 - Capital Equipment Register."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_stores import capital_equipment as cap
from pepl_os.tests.factories import make_file
from pepl_os.tests.utils import PEPLTestCase, set_param

JOB = "pepl_os.pepl_stores.capital_equipment.daily_equipment_alerts"


def _equipment(name, documents=(), **fields):
	doc = frappe.get_doc(
		{"doctype": cap.DOCTYPE, "equipment_name": name, "equipment_type": "Machine", **fields}
	)
	for document_type in documents:
		doc.append(
			"documents", {"document_type": document_type, "file": make_file(f"{name}-{document_type}.pdf")}
		)
	return doc.insert(ignore_permissions=True)


def _open_todos(name):
	return frappe.get_all(
		"ToDo",
		filters={
			"status": "Open",
			"reference_type": cap.DOCTYPE,
			"reference_name": name,
			"description": ["like", f"%{cap.RULE_CODE}%"],
		},
		pluck="name",
	)


class TestCapitalEquipment(PEPLTestCase):
	def setUp(self):
		set_param("enable_operational_todos", 1)
		set_param("custom_stores_notification_owner", "Administrator")
		set_param("custom_supplier_doc_expiry_alert_days", 30)

	def test_missing_core_documents_flagged(self):
		doc = _equipment("PEPL-T-VMC", documents=["Manual"])
		self.assertEqual(doc.document_status, "Missing")
		self.assertIn("Purchase Invoice PDF", doc.missing_documents)
		self.assertIn("Warranty / Guarantee Certificate", doc.missing_documents)
		self.assertNotIn("Manual", doc.missing_documents)

	def test_guarantee_counts_as_warranty(self):
		doc = _equipment(
			"PEPL-T-PRESS", documents=["Purchase Invoice PDF", "Manual", "Guarantee Certificate"]
		)
		self.assertEqual(doc.document_status, "Complete")
		self.assertFalse(doc.missing_documents)

	def test_removing_a_document_turns_it_red(self):
		doc = _equipment("PEPL-T-CMM", documents=["Purchase Invoice PDF", "Manual", "Warranty Certificate"])
		doc.documents = [d for d in doc.documents if d.document_type != "Manual"]
		doc.save(ignore_permissions=True)
		self.assertEqual((doc.document_status, doc.missing_documents), ("Missing", "Manual"))

	def test_days_left_computed(self):
		doc = _equipment("PEPL-T-DAYS", warranty_until=add_days(today(), 10), amc_until=add_days(today(), -2))
		self.assertEqual((doc.warranty_days_left, doc.amc_days_left), (10, -2))

	def test_workstation_only_for_machines(self):
		doc = _equipment("PEPL-T-VAN", equipment_type="Vehicle")
		self.assertFalse(doc.workstation)

	def test_warranty_alert_raised_and_closed(self):
		doc = _equipment("PEPL-T-ALERT", warranty_until=add_days(today(), 10))
		cap.refresh_equipment_alerts()
		self.assertEqual(len(_open_todos(doc.name)), 1)
		cap.refresh_equipment_alerts()
		self.assertEqual(len(_open_todos(doc.name)), 1)  # one ToDo, not one per run

		doc.warranty_until = add_days(today(), 400)
		doc.save(ignore_permissions=True)
		cap.refresh_equipment_alerts()
		self.assertEqual(_open_todos(doc.name), [])

	def test_expired_amc_alerted_disposed_not(self):
		live = _equipment("PEPL-T-AMC", amc_until=add_days(today(), -5))
		gone = _equipment("PEPL-T-SOLD", amc_until=add_days(today(), -5), status="Disposed")
		cap.refresh_equipment_alerts()
		self.assertEqual(len(_open_todos(live.name)), 1)
		self.assertEqual(_open_todos(gone.name), [])

	def test_daily_job_is_registered_and_tracked(self):
		self.assertIn(JOB, frappe.get_hooks("scheduler_events")["daily"])
		self.assertTrue(frappe.db.exists("Scheduled Job Type", {"method": JOB}))
		cap.daily_equipment_alerts()
		self.assertTrue(frappe.db.exists("PEPL Job Run", {"method": JOB, "status": "Success"}))

	def test_daily_job_with_equipment_missing_dates(self):
		# Regression: the job failed on the test site with "Column 'amc_days_left' cannot be null"
		# for a machine with a warranty but no AMC. Frappe v16 Int columns are NOT NULL.
		no_amc = _equipment("PEPL-T-NO-AMC", warranty_until=add_days(today(), 10))
		no_dates = _equipment("PEPL-T-NO-DATES")
		cap.daily_equipment_alerts()
		run = frappe.get_all(
			"PEPL Job Run",
			filters={"method": JOB},
			fields=["status", "error"],
			order_by="creation desc",
			limit=1,
		)[0]
		self.assertEqual(run.status, "Success", run.error)
		self.assertEqual(frappe.db.get_value(cap.DOCTYPE, no_amc.name, "warranty_days_left"), 10)
		self.assertEqual(frappe.db.get_value(cap.DOCTYPE, no_amc.name, "amc_days_left"), 0)
		self.assertEqual(frappe.db.get_value(cap.DOCTYPE, no_dates.name, "warranty_days_left"), 0)
		self.assertEqual(len(_open_todos(no_amc.name)), 1)
		self.assertEqual(_open_todos(no_dates.name), [])

	def test_equipment_is_not_stock(self):
		self.assertFalse(frappe.get_meta(cap.DOCTYPE).is_submittable)
		self.assertFalse(frappe.db.exists("DocField", {"parent": cap.DOCTYPE, "options": "Warehouse"}))
