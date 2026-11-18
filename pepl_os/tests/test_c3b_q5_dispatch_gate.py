"""C3b-Q5 - The dispatch gate: final inspection on the Delivery Note, open NCRs, Advisory / Soft Block / Hard Block."""

import frappe

from pepl_os.common.overrides import log_override
from pepl_os.pepl_quality import dispatch as dg
from pepl_os.pepl_quality import incoming_qc as qc
from pepl_os.pepl_quality import ncr
from pepl_os.pepl_quality.params import validate_quality_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_delivery_note,
	make_item,
	make_sales_order,
	test_warehouse,
)
from pepl_os.tests.utils import SYSTEM_PARAMETERS, PEPLTestCase, set_param

SHAFT = "PEPL-T-DG-SHAFT"  # final inspection before delivery, with a plan
BUSH = "PEPL-T-DG-BUSH"  # no final inspection
PARAMETER = "PEPL-T-DG Shaft Diameter"
TEMPLATE = "PEPL-T-DG Shaft Final Plan"


def _receive(item, qty):
	doc = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"purpose": "Material Receipt",
			"company": TEST_COMPANY,
			"items": [
				{"item_code": item, "qty": qty, "t_warehouse": test_warehouse("FG Stores"), "basic_rate": 50}
			],
		}
	).insert(ignore_permissions=True)
	doc.submit()


def _delivery(lines):
	so = make_sales_order(lines, submit=True)
	return make_delivery_note(so.name, dict(lines))


def _inspect(name, reading):
	qi = frappe.get_doc(qc.QI, name)
	qi.readings[0].reading_1 = reading
	qi.save()
	qi.submit()
	return qi


def _ncr(item, **fields):
	doc = frappe.get_doc(
		{
			"doctype": ncr.NCR,
			"source": "In-Process",
			"severity": "Minor",
			"item": item,
			"defect_description": "Scratch on the shoulder",
			**fields,
		}
	)
	doc.flags.ignore_links = True  # a made-up batch name in the batch test
	return doc.insert(ignore_permissions=True)


class TestDispatchGate(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(SHAFT, st.FINISHED_GOODS, valuation_rate=50)
		make_item(BUSH, st.FINISHED_GOODS, valuation_rate=50)
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
						{"specification": PARAMETER, "numeric": 1, "min_value": 19.9, "max_value": 20.1}
					],
				}
			).insert(ignore_permissions=True)
		frappe.db.set_value("Item", SHAFT, {dg.FLAG: 1, qc.TEMPLATE: TEMPLATE})
		qc.switch_stock_settings_once()

	def setUp(self):
		set_param(dg.MODE_FIELD, dg.HARD_BLOCK)
		set_param("custom_enforce_override_reason", 1)
		set_param("enable_operational_todos", 1)
		set_param("dn_material_gate_mode", "Off")
		_receive(SHAFT, 20)
		_receive(BUSH, 20)

	# ---- the final inspection ----
	def test_saving_the_delivery_makes_the_final_inspection(self):
		dn = _delivery([(SHAFT, 5), (BUSH, 3)])
		rows = {r.item_code: r for r in dn.items}
		self.assertFalse(rows[BUSH].quality_inspection)
		qi = frappe.get_doc(qc.QI, rows[SHAFT].quality_inspection)
		self.assertEqual(
			(
				qi.inspection_type,
				qi.reference_type,
				qi.reference_name,
				qi.sample_size,
				qi.custom_auto_created,
			),
			("Outgoing", "Delivery Note", dn.name, 5, 1),
		)
		self.assertEqual([r.specification for r in qi.readings], [PARAMETER])
		self.assertEqual(str(dn.modified), str(frappe.db.get_value(dg.DN, dn.name, "modified")))
		dn.save()  # nothing new
		self.assertEqual(frappe.db.count(qc.QI, {"reference_name": dn.name}), 1)
		frappe.delete_doc(dg.DN, dn.name)
		self.assertFalse(frappe.db.exists(qc.QI, qi.name))

	def test_hard_block_until_accepted(self):
		dn = _delivery([(SHAFT, 5)])
		self.assertIsNone(dg.dispatch_gate_check(dn.name))  # Hard Block never offers a reason
		with self.assertRaisesRegex(
			frappe.ValidationError, "Row 1 PEPL-T-DG-SHAFT \\(5\\): final inspection .* not finished"
		):
			dn.reload().submit()
		_inspect(dn.items[0].quality_inspection, "20.0")
		dn.reload().submit()
		self.assertEqual(dn.docstatus, 1)

	def test_rejected_final_inspection_blocks_and_raises_ncr(self):
		dn = _delivery([(SHAFT, 5)])
		qi = _inspect(dn.items[0].quality_inspection, "20.5")
		self.assertEqual(qi.status, "Rejected")
		raised = frappe.get_all(ncr.NCR, filters={"quality_inspection": qi.name}, fields=["source", "status"])
		self.assertEqual([(r.source, r.status) for r in raised], [("Dispatch", "Open")])
		gaps = [what for _row, what in dg.delivery_gaps(dn.reload())]
		self.assertTrue(any("is Rejected" in g for g in gaps))
		self.assertTrue(any(g.startswith("open NCR ") for g in gaps))

	def test_open_ncr_blocks_until_closed(self):
		open_one = _ncr(BUSH)
		dn = _delivery([(BUSH, 3)])
		with self.assertRaisesRegex(frappe.ValidationError, f"open NCR {open_one.name} \\(Minor\\)"):
			dn.reload().submit()
		frappe.db.set_value(ncr.NCR, open_one.name, "status", ncr.CLOSED)
		dn.reload().submit()
		self.assertEqual(dn.docstatus, 1)

	def test_ncr_on_another_batch_does_not_block(self):
		_ncr(BUSH, batch_no="PEPL-T-DG-HEAT-A")
		self.assertEqual(len(dg.open_ncrs(BUSH, "PEPL-T-DG-HEAT-A")), 1)
		self.assertEqual(dg.open_ncrs(BUSH, "PEPL-T-DG-HEAT-B"), [])
		self.assertEqual(len(dg.open_ncrs(BUSH, None)), 1)  # the line names no batch: it may be that batch

	def test_soft_block_needs_reason(self):
		set_param(dg.MODE_FIELD, dg.SOFT_BLOCK)
		dn = _delivery([(SHAFT, 5)])
		check = dg.dispatch_gate_check(dn.name)
		self.assertEqual(check["rule_code"], dg.GATE_RULE)
		with self.assertRaisesRegex(frappe.ValidationError, dg.GATE_RULE):
			dn.reload().submit()
		log_override(dg.GATE_RULE, dg.DN, dn.name, check["message"], "Customer collecting today, QC at gate")
		dn.reload().submit()
		self.assertEqual(dn.docstatus, 1)

	def test_advisory_only_warns_and_plain_delivery_untouched(self):
		set_param(dg.MODE_FIELD, dg.ADVISORY)
		dn = _delivery([(SHAFT, 5)])
		dn.reload().submit()
		self.assertEqual(dn.docstatus, 1)
		set_param(dg.MODE_FIELD, dg.HARD_BLOCK)
		plain = _delivery([(BUSH, 2)])
		self.assertIsNone(dg.get_dispatch_panel(plain.name))
		plain.reload().submit()
		self.assertEqual(plain.docstatus, 1)

	def test_returns_are_not_gated(self):
		row = frappe._dict(item_code=SHAFT, qty=-2, idx=1, quality_inspection=None, batch_no=None)
		self.assertEqual(dg.delivery_gaps(frappe._dict(is_return=1, items=[row])), [])

	def test_panel_rows(self):
		_ncr(SHAFT)
		dn = _delivery([(SHAFT, 5)])
		texts = [r["text"] for r in dg.get_dispatch_panel(dn.name)]
		self.assertTrue(
			texts[0].startswith("Line 1 PEPL-T-DG-SHAFT: ") and texts[0].endswith("to be inspected")
		)
		self.assertIn("open Minor NCR", texts[1])
		self.assertEqual(texts[-1], "Dispatch gate: Hard Block")

	def test_settings_and_hooks(self):
		doc = frappe.get_doc(SYSTEM_PARAMETERS)
		doc.set(dg.MODE_FIELD, "Maybe")
		with self.assertRaisesRegex(frappe.ValidationError, "Dispatch Gate"):
			validate_quality_params(doc)
		field = frappe.get_meta(SYSTEM_PARAMETERS).get_field(dg.MODE_FIELD)
		self.assertEqual(str(field.default), dg.SOFT_BLOCK)
		events = frappe.get_hooks("doc_events")["Delivery Note"]
		self.assertIn("pepl_os.pepl_quality.dispatch.before_submit_delivery", events["before_submit"])
		self.assertIn(
			"pepl_os.pepl_production.csm_consumption.before_submit_delivery_note", events["before_submit"]
		)
