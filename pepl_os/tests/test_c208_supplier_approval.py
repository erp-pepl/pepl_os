"""C2-08 - Supplier Approval: checklist, approval rules, mirror to Supplier, daily job, purchase gate."""

import frappe
from frappe.utils import add_days, getdate, today

from pepl_os.common.overrides import log_override
from pepl_os.pepl_purchase import supplier_approval as sa
from pepl_os.tests.factories import make_file, make_rm_group, make_supplier
from pepl_os.tests.utils import PEPLTestCase, make_user, reopen, set_param

REQS = (
	# code, name, mandatory, expires, sequence
	("T-GST", "GST Registration Certificate", 1, 0, 10),
	("T-ISO", "ISO 9001 Certificate", 1, 1, 20),
	("T-OPT", "Company Brochure", 0, 0, 30),
)


def _requirement(code, name, mandatory, expires, sequence, active=1):
	if frappe.db.exists(sa.REQUIREMENT, code):
		return frappe.get_doc(sa.REQUIREMENT, code)
	return frappe.get_doc(
		{
			"doctype": sa.REQUIREMENT,
			"code": code,
			"requirement_name": name,
			"mandatory": mandatory,
			"expires": expires,
			"sequence": sequence,
			"active": active,
		}
	).insert(ignore_permissions=True)


def _approval(supplier_name):
	supplier = make_supplier(supplier_name).insert(ignore_permissions=True)
	return frappe.get_doc({"doctype": sa.DOCTYPE, "supplier": supplier.name}).insert(ignore_permissions=True)


def _row(doc, code):
	return next(r for r in doc.documents if r.requirement == code)


def _fill(doc, iso_expiry):
	_row(doc, "T-GST").file = make_file(f"{doc.supplier}-gst.pdf")
	iso = _row(doc, "T-ISO")
	iso.file = make_file(f"{doc.supplier}-iso.pdf")
	iso.expiry_date = iso_expiry


def _approved(supplier_name, iso_expiry=None):
	doc = _approval(supplier_name)
	_fill(doc, iso_expiry or add_days(today(), 200))
	doc.state = "Approved"
	doc.save(ignore_permissions=True)
	return doc


class TestSupplierApproval(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for req in REQS:
			_requirement(*req)

	def setUp(self):
		set_param("custom_supplier_doc_expiry_alert_days", 30)
		set_param("enable_operational_todos", 1)
		set_param("custom_purchase_notification_owner", "Administrator")
		set_param("custom_enforce_override_reason", 1)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_sync_adds_missing_requirements_only(self):
		doc = _approval("PEPL Test Sync Supplier")
		self.assertTrue({"T-GST", "T-ISO", "T-OPT"} <= {r.requirement for r in doc.documents})
		_row(doc, "T-GST").file = make_file("sync-gst.pdf")
		doc.save(ignore_permissions=True)
		_requirement("T-NEW", "Bank Mandate", 0, 0, 40)
		_requirement("T-OFF", "Old Form", 1, 0, 50, active=0)
		self.assertEqual(sa.sync_checklist(doc), 1)
		self.assertEqual(sa.sync_checklist(doc), 0)
		self.assertTrue(_row(doc, "T-GST").file)
		self.assertNotIn("T-OFF", {r.requirement for r in doc.documents})

	def test_cannot_approve_with_missing_mandatory(self):
		doc = _approval("PEPL Test Missing Supplier")
		doc.state = "Approved"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
		doc.reload()
		_fill(doc, add_days(today(), 200))
		doc.state = "Approved"
		doc.save(ignore_permissions=True)
		self.assertEqual((doc.approved_by, getdate(doc.approval_date)), ("Administrator", getdate(today())))

	def test_expiring_document_needs_its_expiry_date(self):
		doc = _approval("PEPL Test No Date Supplier")
		_row(doc, "T-ISO").file = make_file("nodate-iso.pdf")
		doc.save(ignore_permissions=True)
		self.assertEqual(_row(doc, "T-ISO").status, sa.PENDING)
		_row(doc, "T-ISO").expiry_date = add_days(today(), 10)
		doc.save(ignore_permissions=True)
		self.assertEqual(_row(doc, "T-ISO").status, sa.EXPIRING)

	def test_supplier_fields_mirror_approval(self):
		group = make_rm_group("PEPL-T-MIRROR-RM")
		doc = _approval("PEPL Test Mirror Supplier")
		_fill(doc, add_days(today(), 90))
		doc.append("rm_groups", {"rm_group": group.name})
		doc.state = "Approved"
		doc.save(ignore_permissions=True)
		supplier = frappe.get_doc("Supplier", doc.supplier)
		self.assertEqual(supplier.custom_approval_state, "Approved")
		self.assertEqual(getdate(supplier.custom_approval_expiry), getdate(add_days(today(), 90)))
		self.assertEqual([r.rm_group for r in supplier.custom_rm_groups], [group.name])

	def test_non_manager_cannot_approve(self):
		doc = _approval("PEPL Test Clerk Supplier")
		_fill(doc, add_days(today(), 200))
		doc.save(ignore_permissions=True)
		frappe.set_user(make_user("pepl.purchase.clerk@example.com", roles=["Purchase User"]))
		doc = frappe.get_doc(sa.DOCTYPE, doc.name)
		doc.state = "Approved"
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)

	def test_conditional_needs_remarks_and_review_date(self):
		doc = _approval("PEPL Test Conditional Supplier")
		doc.state = "Conditionally Approved"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
		reopen(doc)
		doc.remarks = "ISO audit booked for next month, MD agreed"
		doc.next_review_date = add_days(today(), 30)
		doc.save(ignore_permissions=True)
		self.assertEqual(
			frappe.db.get_value("Supplier", doc.supplier, "custom_approval_state"), "Conditionally Approved"
		)

	def test_job_expires_supplier_and_raises_todo(self):
		doc = _approved("PEPL Test Expiry Supplier", iso_expiry=add_days(today(), 5))
		sa.refresh_supplier_approvals()
		self.assertEqual(frappe.db.get_value(sa.DOCTYPE, doc.name, "state"), "Approved")
		todo = {
			"reference_type": sa.DOCTYPE,
			"reference_name": doc.name,
			"status": "Open",
			"description": ["like", f"%{sa.EXPIRY_RULE}%"],
		}
		self.assertEqual(frappe.db.count("ToDo", todo), 1)

		frappe.db.set_value(
			"PEPL Supplier Approval Document", _row(doc, "T-ISO").name, "expiry_date", add_days(today(), -1)
		)
		sa.refresh_supplier_approvals()
		self.assertEqual(frappe.db.get_value(sa.DOCTYPE, doc.name, "state"), "Expired")
		self.assertEqual(frappe.db.get_value("Supplier", doc.supplier, "custom_approval_state"), "Expired")
		self.assertEqual(frappe.db.count("ToDo", todo), 1)
		self.assertEqual(frappe.db.get_value("ToDo", todo, "priority"), "High")

		renewed = frappe.get_doc(sa.DOCTYPE, doc.name)
		_row(renewed, "T-ISO").expiry_date = add_days(today(), 365)
		renewed.state = "Approved"
		renewed.save(ignore_permissions=True)
		sa.refresh_supplier_approvals()
		self.assertEqual(frappe.db.count("ToDo", todo), 0)

	def test_daily_job_registered(self):
		self.assertIn(
			"pepl_os.pepl_purchase.supplier_approval.daily_supplier_approvals",
			frappe.get_hooks("scheduler_events")["daily"],
		)


class TestSupplierGate(PEPLTestCase):
	def setUp(self):
		set_param("custom_enforce_override_reason", 1)

	def _po(self, supplier, name):
		doc = frappe.new_doc("Purchase Order")
		doc.supplier = supplier
		doc.name = name
		return doc

	def test_po_with_unapproved_supplier_needs_reason(self):
		supplier = make_supplier("PEPL Test Gate Supplier").insert(ignore_permissions=True)
		doc = self._po(supplier.name, "PEPL-T-PO-GATE")
		with self.assertRaises(frappe.ValidationError) as ctx:
			sa.before_submit_gate(doc)
		self.assertTrue(str(ctx.exception).startswith(f"[{sa.GATE_RULE}]"))

	def test_reason_written_to_override_log_lets_it_through(self):
		supplier = make_supplier("PEPL Test Gate Reason Supplier").insert(ignore_permissions=True)
		doc = self._po(supplier.name, "PEPL-T-PO-REASON")
		log_override(
			sa.GATE_RULE, "Purchase Order", doc.name, "Not approved", "Breakdown spare, MD approved on phone"
		)
		sa.before_submit_gate(doc)  # no error
		self.assertTrue(
			frappe.db.exists("PEPL Override Log", {"rule_code": sa.GATE_RULE, "reference_name": doc.name})
		)

	def test_rfq_with_unapproved_supplier_needs_reason(self):
		ok = make_supplier("PEPL Test RFQ Approved").insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", ok.name, "custom_approval_state", "Approved")
		bad = make_supplier("PEPL Test RFQ Suspended").insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", bad.name, "custom_approval_state", "Suspended")
		rfq = frappe.new_doc("Request for Quotation")
		rfq.name = "PEPL-T-RFQ-GATE"
		rfq.append("suppliers", {"supplier": ok.name})
		rfq.append("suppliers", {"supplier": bad.name})
		self.assertEqual(sa.unapproved_suppliers(rfq), [(bad.name, "Suspended")])
		with self.assertRaises(frappe.ValidationError):
			sa.before_submit_gate(rfq)

	def test_approved_supplier_passes(self):
		supplier = make_supplier("PEPL Test Gate Approved").insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", supplier.name, "custom_approval_state", "Conditionally Approved")
		sa.before_submit_gate(self._po(supplier.name, "PEPL-T-PO-OK"))

	def test_switch_off_only_warns(self):
		set_param("custom_enforce_override_reason", 0)
		supplier = make_supplier("PEPL Test Gate Off").insert(ignore_permissions=True)
		sa.before_submit_gate(self._po(supplier.name, "PEPL-T-PO-OFF"))

	def test_gate_hooked_on_rfq_and_po(self):
		events = frappe.get_hooks("doc_events")
		for doctype in ("Request for Quotation", "Purchase Order"):
			self.assertIn(
				"pepl_os.pepl_purchase.supplier_approval.before_submit_gate", events[doctype]["before_submit"]
			)
