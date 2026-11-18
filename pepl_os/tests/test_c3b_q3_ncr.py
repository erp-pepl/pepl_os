"""C3b-Q3 - NCR: sign-off by severity, closing rules, and the three auto-raise rules."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import add_days, today

from pepl_os.pepl_production import rejection_scrap as rs
from pepl_os.pepl_quality import incoming_qc as qc
from pepl_os.pepl_quality import ncr
from pepl_os.pepl_quality.params import validate_quality_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_downtime_category,
	make_item,
	make_job_card,
	make_operator,
	make_shift,
	make_spr,
	make_supplier,
	make_workstation,
)
from pepl_os.tests.utils import SYSTEM_PARAMETERS, PEPLTestCase, make_user, set_param

OWNER = "pepl.t.ncr.owner@example.com"
QM = "pepl.t.ncr.qm@example.com"
PM = "pepl.t.ncr.pm@example.com"
STORES = "pepl.t.ncr.stores@example.com"
PIN = "PEPL-T-NCR-PIN"
SUPPLIER = "PEPL T NCR Pins"
PARAMETER = "PEPL-T-NCR Diameter"
TEMPLATE = "PEPL-T-NCR Pin Plan"
DAY = "T-NCR Day"
MILL = "T-NCR MILL-01"
OP = "T-NCR-OP1"
NO_LOAD = "T-NCR No Load"
YESTERDAY = add_days(today(), -1)


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _inspection(reading):
	"""A submitted-ready incoming QC Inspection of 25 pins (plan 9.9 - 10.1) with one reading."""
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": SUPPLIER,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 5),
			"items": [
				{
					"item_code": PIN,
					"qty": 25,
					"rate": 10,
					"schedule_date": add_days(today(), 5),
					"warehouse": _wh("Bought-Out Stores"),
				}
			],
		}
	).insert(ignore_permissions=True)
	po.submit()
	pr = make_purchase_receipt(po.name)
	pr.insert(ignore_permissions=True)
	qi = frappe.get_doc(qc.QI, pr.items[0].quality_inspection)
	qi.readings[0].reading_1 = reading
	qi.save()
	return pr, qi


def _manual(severity=ncr.MINOR, **fields):
	return frappe.get_doc(
		{
			"doctype": ncr.NCR,
			"source": "Other",
			"severity": severity,
			"item": PIN,
			"qty_affected": 5,
			"defect_description": "Burr on the chamfer",
			**fields,
		}
	).insert(ignore_permissions=True)


def _ncrs(**filters):
	return frappe.get_all(ncr.NCR, filters=filters, fields=["*"], order_by="creation")


def _todo(name):
	return frappe.get_all(
		"ToDo",
		filters={"reference_type": ncr.NCR, "reference_name": name, "status": "Open"},
		fields=["allocated_to", "priority", "description"],
	)


class TestNCR(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(PIN, st.BOUGHT_OUT, valuation_rate=10)
		frappe.db.set_value("Item", PIN, qc.FLAG, 1)
		if not frappe.db.exists("Quality Inspection Parameter", PARAMETER):
			frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": PARAMETER}).insert(
				ignore_permissions=True
			)
		if not frappe.db.exists("Quality Inspection Template", TEMPLATE):
			frappe.get_doc(
				{
					"doctype": "Quality Inspection Template",
					"quality_inspection_template_name": TEMPLATE,
					"item_quality_inspection_parameter": [
						{"specification": PARAMETER, "numeric": 1, "min_value": 9.9, "max_value": 10.1}
					],
				}
			).insert(ignore_permissions=True)
		frappe.db.set_value("Item", PIN, qc.TEMPLATE, TEMPLATE)
		if not frappe.db.exists("Supplier", SUPPLIER):
			make_supplier(SUPPLIER).insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")
		qc.switch_stock_settings_once()
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(MILL)
		make_operator(OP, pin="6543")
		make_downtime_category(NO_LOAD, "Planned", 0)
		cls.card = make_job_card(MILL, "T-NCR-JC", qty=60, minutes_per_piece=6)
		cls.part = cls.card.production_item

	def setUp(self):
		set_param("custom_po_approval_value_threshold", 0)
		set_param("enable_operational_todos", 1)
		set_param(qc.MODE_FIELD, qc.ADVISORY)
		set_param(ncr.OWNER_FIELD, make_user(OWNER, ["Quality Manager"]))
		set_param(ncr.AUTO_SEVERITY_FIELD, ncr.MAJOR)
		set_param(ncr.RETURN_FIELD, 1)
		set_param(ncr.RATE_FIELD, 5)
		set_param(ncr.MIN_PIECES_FIELD, 10)
		for severity, field in ncr.SIGNOFF_FIELDS.items():
			set_param(field, ncr.SIGNOFF_DEFAULTS[severity])
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")
		set_param(rs.ENABLE_FIELD, 0)
		make_user(QM, ["Quality Manager"])
		make_user(PM, ["Manufacturing Manager"])
		make_user(STORES, ["Stock User"])

	# ---- QA-NCR-QI ----
	def test_rejected_incoming_inspection_raises_ncr(self):
		pr, qi = _inspection("10.4")
		qi.submit()
		self.assertEqual(qi.status, "Rejected")
		rows = _ncrs(quality_inspection=qi.name)
		self.assertEqual(len(rows), 1)
		row = rows[0]
		self.assertEqual(
			(
				row.source,
				row.severity,
				row.status,
				row.item,
				row.supplier,
				row.purchase_receipt,
				row.qty_affected,
			),
			("Incoming", "Major", "Open", PIN, SUPPLIER, pr.name, 25),
		)
		self.assertEqual((row.raised_by_system, row.raise_rule), (1, ncr.RULE_QI))
		self.assertIn(PARAMETER, row.defect_description)
		todo = _todo(row.name)
		self.assertEqual((len(todo), todo[0].allocated_to), (1, OWNER))
		# cancelling the inspection cancels the unsigned NCR and closes the ToDo
		qi.cancel()
		self.assertEqual(frappe.db.get_value(ncr.NCR, row.name, "status"), ncr.CANCELLED)
		self.assertFalse(_todo(row.name))

	def test_accepted_inspection_raises_nothing(self):
		_pr, qi = _inspection("10.0")
		qi.submit()
		self.assertFalse(_ncrs(quality_inspection=qi.name))

	# ---- QA-NCR-RETURN ----
	def _return(self, name="PEPL-T-RET-0001"):
		row = frappe._dict(item_code=PIN, qty=-4, stock_qty=-4, against_sales_order=None, batch_no=None)
		return frappe._dict(
			name=name,
			is_return=1,
			customer="PEPL T NCR Customer",
			return_against="PEPL-T-DN-0001",
			items=[row, row],
		)

	def test_customer_return_raises_one_ncr_per_item(self):
		dn = self._return()
		ncr.on_delivery_note_submit(dn)
		ncr.on_delivery_note_submit(dn)  # twice: still one
		rows = _ncrs(delivery_note=dn.name)
		self.assertEqual(len(rows), 1)
		self.assertEqual(
			(rows[0].source, rows[0].qty_affected, rows[0].against_delivery_note),
			("Customer", 8, "PEPL-T-DN-0001"),
		)
		self.assertIn("returned 8 ", rows[0].defect_description)
		# regression 0.64.1 (CI #69): the return, delivery and customer named here do not exist on the site; the
		# system still cancels its NCR (the cancel used to be refused on the missing links and stayed Open)
		ncr.on_delivery_note_cancel(dn)
		self.assertEqual(frappe.db.get_value(ncr.NCR, rows[0].name, "status"), ncr.CANCELLED)
		self.assertFalse(_todo(rows[0].name))
		set_param(ncr.RETURN_FIELD, 0)
		ncr.on_delivery_note_submit(self._return("PEPL-T-RET-0002"))
		self.assertFalse(_ncrs(delivery_note="PEPL-T-RET-0002"))

	def test_delivery_return_hooks_registered(self):
		events = frappe.get_hooks("doc_events")["Delivery Note"]
		self.assertIn("pepl_os.pepl_quality.ncr.on_delivery_note_submit", events["on_submit"])
		self.assertIn("pepl_os.pepl_quality.ncr.on_delivery_note_cancel", events["on_cancel"])

	# ---- QA-NCR-RATE ----
	def _entry(self, good, rejected, on=YESTERDAY):
		row = {"job_card": self.card.name, "from_time": "08:00", "to_time": "10:00", "good_qty": good}
		if rejected:
			row.update({"rejected_qty": rejected, "rejection_reason": "Undersize"})
		doc = make_spr(
			MILL,
			DAY,
			OP,
			on,
			production=[row],
			downtime=[{"downtime_category": NO_LOAD, "from_time": "10:00", "to_time": "16:30"}],
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_rejection_rate_above_threshold_raises_ncr_and_cancel_takes_it_back(self):
		entry = self._entry(good=8, rejected=4)  # 12 made, 33 % rejected
		rows = _ncrs(item=self.part, rate_date=YESTERDAY)
		self.assertEqual(len(rows), 1)
		row = rows[0]
		self.assertEqual(
			(row.source, row.raise_rule, row.pieces_made, row.pieces_rejected, row.rejection_rate),
			("In-Process", ncr.RULE_RATE, 12, 4, 33.33),
		)
		self.assertIn("4 pieces", row.defect_description)
		self.assertNotIn(".0 ", row.defect_description)
		entry.cancel()
		self.assertEqual(frappe.db.get_value(ncr.NCR, row.name, "status"), ncr.CANCELLED)

	def test_rejection_rate_rules_minimum_and_threshold(self):
		self._entry(good=6, rejected=3)  # 9 made < minimum 10
		self.assertFalse(_ncrs(item=self.part, rate_date=YESTERDAY))
		set_param(ncr.RATE_FIELD, 0)  # off
		self._entry(good=8, rejected=4, on=add_days(today(), -2))
		self.assertFalse(_ncrs(item=self.part, rate_date=add_days(today(), -2)))
		set_param(ncr.RATE_FIELD, 50)  # 33 % is below 50 %
		self.assertIsNone(ncr.check_rate(self.part, add_days(today(), -2)))

	# ---- sign-off and closing ----
	def test_minor_closed_after_quality_signs(self):
		doc = _manual(ncr.MINOR)
		self.assertEqual(doc.required_sign_offs, "Quality Manager")
		doc.status = ncr.CLOSED
		with self.assertRaisesRegex(frappe.ValidationError, "disposition"):
			doc.save()
		doc.reload()
		doc.disposition = "Rework"
		doc.status = ncr.CLOSED
		with self.assertRaisesRegex(frappe.ValidationError, "still needs the sign-off of: Quality Manager"):
			doc.save()
		frappe.set_user(STORES)
		with self.assertRaisesRegex(frappe.ValidationError, "none of the roles"):
			ncr.sign_off(doc.name)
		frappe.set_user(QM)
		result = ncr.sign_off(doc.name, "Reworked and re-checked")
		self.assertEqual(
			(result["signed"], result["missing"], result["status"]),
			(["Quality Manager"], [], ncr.UNDER_REVIEW),
		)
		doc = frappe.get_doc(ncr.NCR, doc.name)
		doc.disposition = "Rework"
		doc.status = ncr.CLOSED
		doc.save()
		self.assertEqual((doc.closed_by, bool(doc.closed_on)), (QM, True))

	def test_critical_needs_three_roles(self):
		doc = _manual(ncr.CRITICAL)
		frappe.set_user(QM)
		ncr.sign_off(doc.name)
		frappe.set_user(PM)
		state = ncr.sign_off(doc.name)
		self.assertEqual(state["missing"], ["PEPL CEO"])
		frappe.set_user("Administrator")
		doc = frappe.get_doc(ncr.NCR, doc.name)
		doc.disposition = "Scrap"
		doc.status = ncr.CLOSED
		with self.assertRaisesRegex(frappe.ValidationError, "PEPL CEO"):
			doc.save()

	def test_closed_ncr_is_locked_and_reopened_by_quality_only(self):
		doc = _manual(ncr.MINOR)
		frappe.set_user(QM)
		ncr.sign_off(doc.name)
		doc = frappe.get_doc(ncr.NCR, doc.name)
		doc.disposition = "Use As Is"
		doc.status = ncr.CLOSED
		doc.save()
		doc.reload()
		doc.qty_affected = 9
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be changed"):
			doc.save()
		frappe.set_user(STORES)
		doc = frappe.get_doc(ncr.NCR, doc.name)
		doc.status = ncr.UNDER_REVIEW
		with self.assertRaisesRegex(frappe.ValidationError, "Only a Quality Manager"):
			doc.save(ignore_permissions=True)
		frappe.set_user(QM)
		doc = frappe.get_doc(ncr.NCR, doc.name)
		doc.status = ncr.UNDER_REVIEW
		doc.save()
		self.assertIsNone(doc.closed_on)

	def test_signature_cannot_be_removed_or_faked(self):
		doc = _manual(ncr.MINOR)
		frappe.set_user(QM)
		ncr.sign_off(doc.name)
		frappe.set_user("Administrator")
		doc = frappe.get_doc(ncr.NCR, doc.name)
		doc.sign_offs = []
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be removed"):
			doc.save()
		other = _manual(ncr.MAJOR)
		other.append("sign_offs", {"role": "Manufacturing Manager", "user": STORES})
		with self.assertRaisesRegex(frappe.ValidationError, "does not hold the role"):
			other.save()

	def test_cancel_needs_reason_and_stays_cancelled(self):
		doc = _manual()
		doc.status = ncr.CANCELLED
		with self.assertRaisesRegex(frappe.ValidationError, "reason"):
			doc.save()
		doc.reload()
		doc.status = ncr.CANCELLED
		doc.cancel_reason = "Raised twice by mistake"
		doc.save()
		doc.reload()
		doc.status = ncr.OPEN
		with self.assertRaisesRegex(frappe.ValidationError, "stays cancelled"):
			doc.save()

	# ---- settings ----
	def test_settings_validated(self):
		doc = frappe.get_doc(SYSTEM_PARAMETERS)
		doc.set(ncr.SIGNOFF_FIELDS[ncr.MAJOR], "Quality Manager\nChief Wizard")
		with self.assertRaisesRegex(frappe.ValidationError, "Chief Wizard"):
			validate_quality_params(doc)
		doc.set(ncr.SIGNOFF_FIELDS[ncr.MAJOR], ncr.SIGNOFF_DEFAULTS[ncr.MAJOR])
		doc.set(ncr.RATE_FIELD, 150)
		with self.assertRaisesRegex(frappe.ValidationError, "Rejection Rate Threshold"):
			validate_quality_params(doc)
		doc.set(ncr.RATE_FIELD, 5)
		doc.set(ncr.MIN_PIECES_FIELD, 0)
		with self.assertRaisesRegex(frappe.ValidationError, "Minimum Pieces"):
			validate_quality_params(doc)
		self.assertTrue(frappe.get_meta(ncr.NCR).track_changes)
