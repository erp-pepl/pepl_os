"""C3b-Q1 - Incoming QC Inspection created with the Purchase Receipt, and the incoming QC gate."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import add_days, today

from pepl_os.common.overrides import log_override
from pepl_os.pepl_quality import incoming_qc as qc
from pepl_os.pepl_quality.params import validate_quality_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import SYSTEM_PARAMETERS, PEPLTestCase, make_user, set_param, set_single

BOLT = "PEPL-T-QC-BOLT"  # bought-out, inspected (class listed)
WASHER = "PEPL-T-QC-WASHER"  # bought-out, inspected, with an inspection plan
OIL = "PEPL-T-QC-OIL"  # consumable, not inspected
SUPPLIER = "PEPL T QC Fasteners"
PARAMETER = "PEPL-T-QC Thread Pitch"
TEMPLATE = "PEPL-T-QC Washer Plan"
OWNER = "pepl.t.qc.owner@example.com"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _plan():
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
					{"specification": PARAMETER, "numeric": 1, "min_value": 1.4, "max_value": 1.6}
				],
			}
		).insert(ignore_permissions=True)
	return TEMPLATE


def _receipt(lines):
	"""A draft receipt from a submitted PO; lines = [(item, qty)]."""
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": SUPPLIER,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 5),
			"items": [
				{
					"item_code": item,
					"qty": qty,
					"rate": 10,
					"schedule_date": add_days(today(), 5),
					"warehouse": _wh(
						st.CLASS_DEFAULT_STORE[frappe.db.get_value("Item", item, "custom_stock_class")]
					),
				}
				for item, qty in lines
			],
		}
	).insert(ignore_permissions=True)
	po.submit()
	pr = make_purchase_receipt(po.name)
	pr.insert(ignore_permissions=True)
	return pr


def _inspect(name, status="Accepted"):
	qi = frappe.get_doc(qc.QI, name)
	if qi.readings:  # a measured value: 1.5 is inside the plan's 1.4 - 1.6, 1.9 is not
		qi.readings[0].reading_1 = "1.5" if status == "Accepted" else "1.9"
	else:
		qi.status = status
	qi.save()
	qi.submit()
	assert qi.status == status, qi.status
	return qi


class TestIncomingQC(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		set_param(qc.CLASSES_FIELD, st.BOUGHT_OUT)
		make_item(BOLT, st.BOUGHT_OUT, valuation_rate=10)
		make_item(WASHER, st.BOUGHT_OUT, valuation_rate=10)
		frappe.db.set_value("Item", WASHER, qc.TEMPLATE, _plan())
		make_item(OIL, st.CONSUMABLES, valuation_rate=10)
		if not frappe.db.exists("Supplier", SUPPLIER):
			make_supplier(SUPPLIER).insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")
		qc.switch_stock_settings_once()

	def setUp(self):
		set_param("custom_po_approval_value_threshold", 0)
		set_param(qc.CLASSES_FIELD, st.BOUGHT_OUT)
		set_param(qc.MODE_FIELD, qc.SOFT_BLOCK)
		set_param("custom_enforce_override_reason", 1)
		set_param("enable_operational_todos", 1)
		set_param(qc.OWNER_FIELD, make_user(OWNER, ["Quality Manager"]))
		frappe.db.set_value("Item", WASHER, qc.TEMPLATE, TEMPLATE)
		frappe.clear_document_cache("Item", WASHER)

	# ---- which items are inspected ----
	def test_new_item_of_listed_class_is_inspected(self):
		self.assertEqual(frappe.db.get_value("Item", BOLT, qc.FLAG), 1)
		self.assertEqual(frappe.db.get_value("Item", OIL, qc.FLAG), 0)

	def test_adding_and_removing_a_class_ticks_and_unticks(self):
		set_param(qc.CLASSES_FIELD, "")
		doc = frappe.get_doc(SYSTEM_PARAMETERS)
		doc._doc_before_save = frappe.get_doc(SYSTEM_PARAMETERS)
		doc.set(qc.CLASSES_FIELD, f"{st.BOUGHT_OUT}\n{st.CONSUMABLES}")
		doc._doc_before_save.set(qc.CLASSES_FIELD, st.BOUGHT_OUT)
		ticked, unticked = qc.on_parameters_update(doc)
		self.assertGreaterEqual(ticked, 1)
		self.assertEqual(unticked, 0)
		self.assertEqual(frappe.db.get_value("Item", OIL, qc.FLAG), 1)
		doc._doc_before_save.set(qc.CLASSES_FIELD, f"{st.BOUGHT_OUT}\n{st.CONSUMABLES}")
		doc.set(qc.CLASSES_FIELD, st.BOUGHT_OUT)
		ticked, _unticked = qc.on_parameters_update(doc)
		self.assertEqual(ticked, 0)
		self.assertEqual(frappe.db.get_value("Item", OIL, qc.FLAG), 0)
		self.assertEqual(frappe.db.get_value("Item", BOLT, qc.FLAG), 1)

	def test_unknown_class_and_mode_refused(self):
		doc = frappe.get_doc(SYSTEM_PARAMETERS)
		doc.set(qc.CLASSES_FIELD, "Raw Material\nGold Bars")
		with self.assertRaisesRegex(frappe.ValidationError, "Gold Bars"):
			validate_quality_params(doc)
		doc.set(qc.CLASSES_FIELD, st.CAPITAL)
		with self.assertRaisesRegex(frappe.ValidationError, "unknown class"):
			validate_quality_params(doc)
		doc.set(qc.CLASSES_FIELD, "Raw Material, Bought-Out Components")
		doc.set(qc.MODE_FIELD, "Maybe")
		with self.assertRaisesRegex(frappe.ValidationError, "Incoming QC Gate"):
			validate_quality_params(doc)
		self.assertEqual(
			qc.parse_classes("Raw Material, Bought-Out Components\nRaw Material"),
			[st.RAW_MATERIAL, st.BOUGHT_OUT],
		)

	def test_stock_settings_switched_to_warn_once(self):
		frappe.db.set_default(qc.STOCK_SETTINGS_FLAG, 0)
		set_single("Stock Settings", qc.STOCK_SETTINGS_ACTIONS[0], "Stop")
		self.assertTrue(qc.switch_stock_settings_once())
		self.assertEqual(frappe.db.get_single_value("Stock Settings", qc.STOCK_SETTINGS_ACTIONS[0]), "Warn")
		set_single("Stock Settings", qc.STOCK_SETTINGS_ACTIONS[0], "Stop")
		self.assertFalse(qc.switch_stock_settings_once())  # PEPL chose Stop again: it stays
		self.assertEqual(frappe.db.get_single_value("Stock Settings", qc.STOCK_SETTINGS_ACTIONS[0]), "Stop")
		set_single("Stock Settings", qc.STOCK_SETTINGS_ACTIONS[0], "Warn")

	# ---- the QC Inspection of each line ----
	def test_receipt_save_creates_one_inspection_per_inspected_line(self):
		pr = _receipt([(BOLT, 20), (OIL, 5), (WASHER, 100)])
		rows = {r.item_code: r for r in pr.items}
		self.assertFalse(rows[OIL].quality_inspection)
		bolt_qi = frappe.get_doc(qc.QI, rows[BOLT].quality_inspection)
		self.assertEqual(
			(
				bolt_qi.inspection_type,
				bolt_qi.reference_name,
				bolt_qi.item_code,
				bolt_qi.sample_size,
				bolt_qi.docstatus,
			),
			("Incoming", pr.name, BOLT, 20, 0),
		)
		self.assertEqual(
			(bolt_qi.custom_auto_created, bolt_qi.custom_supplier, bolt_qi.child_row_reference),
			(1, SUPPLIER, rows[BOLT].name),
		)
		washer_qi = frappe.get_doc(qc.QI, rows[WASHER].quality_inspection)
		self.assertEqual(washer_qi.quality_inspection_template, TEMPLATE)
		self.assertEqual([r.specification for r in washer_qi.readings], [PARAMETER])
		# the link is stored on the line, and the form's copy is not "modified by someone else"
		self.assertEqual(frappe.db.get_value(qc.PR_ITEM, rows[BOLT].name, "quality_inspection"), bolt_qi.name)
		self.assertEqual(str(pr.modified), str(frappe.db.get_value(qc.PR, pr.name, "modified")))
		pr.save()  # saving again makes nothing new
		self.assertEqual(frappe.db.count(qc.QI, {"reference_name": pr.name}), 2)

	def test_item_without_plan_gives_quality_a_todo_closed_when_plan_set(self):
		_receipt([(BOLT, 5)])
		todo = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "Item",
				"reference_name": BOLT,
				"status": "Open",
				"description": ["like", f"%{qc.NO_PLAN_RULE}%"],
			},
			fields=["allocated_to", "description"],
		)
		self.assertEqual(len(todo), 1)
		self.assertEqual(todo[0].allocated_to, OWNER)
		self.assertIn("no inspection plan", todo[0].description)
		item = frappe.get_doc("Item", BOLT)
		item.quality_inspection_template = TEMPLATE
		item.save()
		self.assertFalse(
			frappe.get_all(
				"ToDo",
				filters={
					"reference_name": BOLT,
					"status": "Open",
					"description": ["like", f"%{qc.NO_PLAN_RULE}%"],
				},
			)
		)

	def test_removed_line_loses_its_unused_draft(self):
		pr = _receipt([(BOLT, 20), (WASHER, 10)])
		washer_row = next(r for r in pr.items if r.item_code == WASHER)
		washer_qi = washer_row.quality_inspection
		pr.remove(washer_row)
		pr.save()
		self.assertFalse(frappe.db.exists(qc.QI, washer_qi))
		self.assertEqual(frappe.db.count(qc.QI, {"reference_name": pr.name}), 1)

	def test_deleting_draft_receipt_deletes_its_drafts(self):
		pr = _receipt([(BOLT, 20)])
		name = pr.items[0].quality_inspection
		frappe.delete_doc(qc.PR, pr.name)
		self.assertFalse(frappe.db.exists(qc.QI, name))

	# ---- the gate ----
	def test_soft_block_needs_reason_until_inspected(self):
		pr = _receipt([(BOLT, 20)])
		check = qc.qc_gate_check(pr.name)
		self.assertEqual(check["rule_code"], qc.GATE_RULE)
		self.assertIn("not finished", check["message"])
		with self.assertRaisesRegex(frappe.ValidationError, qc.GATE_RULE):
			pr.reload().submit()
		log_override(qc.GATE_RULE, qc.PR, pr.name, check["message"], "Urgent line stoppage, QC tomorrow")
		pr.reload().submit()
		self.assertEqual(pr.docstatus, 1)

	def test_accepted_inspection_clears_the_gate(self):
		set_param(qc.MODE_FIELD, qc.HARD_BLOCK)
		pr = _receipt([(WASHER, 50)])
		self.assertIsNone(qc.qc_gate_check(pr.name))  # Hard Block never asks for a reason
		with self.assertRaisesRegex(frappe.ValidationError, "not finished"):
			pr.reload().submit()
		_inspect(pr.items[0].quality_inspection, "Accepted")
		pr.reload().submit()
		self.assertEqual(pr.docstatus, 1)

	def test_rejected_inspection_blocks_while_accepted_qty(self):
		set_param(qc.MODE_FIELD, qc.HARD_BLOCK)
		pr = _receipt([(BOLT, 10)])
		_inspect(pr.items[0].quality_inspection, "Rejected")
		# regression 0.60.1: quantities without ".0" (Check 60 showed "Rejected but 20.0")
		with self.assertRaisesRegex(frappe.ValidationError, "Rejected but 10 is accepted"):
			pr.reload().submit()
		# the whole lot booked as rejected (nothing accepted into stores): the gate has nothing to stop
		pr.reload()
		pr.items[0].qty = 0
		pr.items[0].rejected_qty = 10
		self.assertFalse(qc.receipt_gaps(pr))

	def test_advisory_only_warns(self):
		set_param(qc.MODE_FIELD, qc.ADVISORY)
		pr = _receipt([(BOLT, 10)])
		pr.reload().submit()
		self.assertEqual(pr.docstatus, 1)

	def test_receipt_without_inspected_items_untouched(self):
		set_param(qc.MODE_FIELD, qc.HARD_BLOCK)
		pr = _receipt([(OIL, 5)])
		self.assertIsNone(qc.get_receipt_qc_panel(pr.name))
		pr.reload().submit()
		self.assertEqual(pr.docstatus, 1)

	def test_panel_rows(self):
		pr = _receipt([(BOLT, 10), (WASHER, 10)])
		rows = qc.get_receipt_qc_panel(pr.name)
		texts = [r["text"] for r in rows]
		self.assertTrue(
			texts[0].startswith(f"Line 1 {BOLT}: ") and "to be inspected (no inspection plan)" in texts[0]
		)
		self.assertEqual(rows[0]["colour"], "orange")
		self.assertNotIn("no inspection plan", texts[1])
		self.assertEqual(texts[-1], "Incoming QC gate: Soft Block")
		_inspect(pr.items[1].quality_inspection, "Accepted")
		rows = qc.get_receipt_qc_panel(pr.name)
		self.assertEqual((rows[1]["text"].endswith("Accepted"), rows[1]["colour"]), (True, "green"))
