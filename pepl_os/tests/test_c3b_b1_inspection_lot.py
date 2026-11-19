"""C3b-B1 - Inspection lots: lot request -> proof -> bulk lot offer -> IC; NCR for a rejection; the IC at dispatch."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_quality import dispatch as dg
from pepl_os.pepl_quality import incoming_qc as qc
from pepl_os.pepl_quality import inspection_lot as il
from pepl_os.pepl_quality import ncr
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_delivery_note,
	make_item,
	make_sales_order,
	test_warehouse,
)
from pepl_os.tests.utils import PEPLTestCase, set_param

BOGIE = "PEPL-T-LOT-PIN"  # no final inspection of PEPL's own
SHAFT = "PEPL-T-LOT-SHAFT"  # inspected before delivery
OTHER = "PEPL-T-LOT-OTHER"


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


def _lot(so, item=BOGIE, qty=60, **fields):
	return frappe.get_doc(
		{
			"doctype": il.LOT,
			"sales_order": so,
			"item": item,
			"lot_qty": qty,
			"inspection_agency": "RITES",
			**fields,
		}
	).insert(ignore_permissions=True)


def _inspected(doc, accepted, rejected, **fields):
	doc.update(
		{
			"requested_on": add_days(today(), -6),
			"offered_on": add_days(today(), -2),
			"offered_qty": accepted + rejected,
			"inspected_on": today(),
			"inspector": "IE Sharma",
			"accepted_qty": accepted,
			"rejected_qty": rejected,
			"ic_number": "RITES/IC/001" if accepted else None,
			"ic_date": today() if accepted else None,
			**fields,
		}
	)
	doc.save()
	return doc


class TestInspectionLot(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		for code in (BOGIE, SHAFT, OTHER):
			make_item(code, st.FINISHED_GOODS, valuation_rate=50)
		frappe.db.set_value("Item", SHAFT, dg.FLAG, 1)
		qc.switch_stock_settings_once()

	def setUp(self):
		set_param(dg.MODE_FIELD, dg.HARD_BLOCK)
		set_param("enable_operational_todos", 1)
		set_param("dn_material_gate_mode", "Off")
		set_param(ncr.AUTO_SEVERITY_FIELD, ncr.MAJOR)
		for severity, field in ncr.SIGNOFF_FIELDS.items():
			set_param(field, ncr.SIGNOFF_DEFAULTS[severity])
		self.so = make_sales_order([(BOGIE, 100), (SHAFT, 10)], submit=True).name

	def test_status_follows_each_step(self):
		doc = _lot(self.so, proof_required=1)
		self.assertEqual((doc.status, doc.so_qty), (il.DRAFT, 100))
		doc.requested_on = add_days(today(), -10)
		doc.lot_no = "LOT/24/017"
		doc.save()
		self.assertEqual(doc.status, il.REQUESTED)
		doc.proof_scheduled_on = add_days(today(), -8)
		doc.save()
		self.assertEqual(doc.status, il.PROOF_SCHEDULED)
		doc.offered_on = today()
		doc.offered_qty = 60
		with self.assertRaisesRegex(frappe.ValidationError, "once the proof inspection has Passed"):
			doc.save()
		doc.reload()
		doc.proof_result = "Passed"
		doc.save()
		self.assertEqual(doc.status, il.PROOF_PASSED)
		doc.offered_on = add_days(today(), -2)
		doc.offered_qty = 60
		doc.save()
		self.assertEqual(doc.status, il.OFFERED)
		_inspected(doc, 55, 5)
		self.assertEqual(doc.status, il.INSPECTED)
		texts = [r["text"] for r in il.get_lot_panel(doc.name)]
		self.assertEqual(
			texts[0], f"Lot LOT/24/017 of {BOGIE}: Inspected · {self.so} (100 Nos ordered) · agency RITES"
		)
		self.assertIn(
			f"✓ Inspected {frappe.utils.formatdate(today())}: accepted 55, rejected 5 · IC RITES/IC/001",
			" | ".join(texts),
		)

	def test_rejected_quantity_raises_one_ncr(self):
		doc = _inspected(_lot(self.so), 55, 5)
		name = frappe.db.get_value(il.LOT, doc.name, "ncr")
		self.assertTrue(name)
		n = frappe.get_doc(ncr.NCR, name)
		self.assertEqual(
			(n.source, n.item, n.qty_affected, n.sales_order, n.inspection_lot, n.raise_rule, n.severity),
			(ncr.DISPATCH, BOGIE, 5, self.so, doc.name, il.RULE, ncr.MAJOR),
		)
		self.assertIn("Rejected by RITES", n.defect_type)
		doc = frappe.get_doc(il.LOT, doc.name)
		doc.remarks = "IC copy filed"
		doc.save()
		self.assertEqual(frappe.db.count(ncr.NCR, {"inspection_lot": doc.name}), 1)
		nothing = _inspected(_lot(self.so, qty=20), 0, 20)
		self.assertEqual(nothing.status, il.REJECTED)
		self.assertTrue(frappe.db.get_value(il.LOT, nothing.name, "ncr"))

	def test_rules(self):
		with self.assertRaisesRegex(frappe.ValidationError, "is not on Sales Order"):
			_lot(self.so, item=OTHER)
		_lot(self.so, qty=60)
		with self.assertRaisesRegex(frappe.ValidationError, "more than the 100 ordered"):
			_lot(self.so, qty=50)
		doc = _lot(self.so, qty=40)
		doc.requested_on = today()
		doc.offered_on = today()
		doc.offered_qty = 45
		with self.assertRaisesRegex(frappe.ValidationError, "at most the lot size"):
			doc.save()
		doc.reload()
		doc.update(
			{
				"offered_on": today(),
				"offered_qty": 40,
				"inspected_on": today(),
				"accepted_qty": 30,
				"rejected_qty": 5,
			}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "must equal the quantity offered"):
			doc.save()
		doc.reload()
		doc.update(
			{
				"offered_on": today(),
				"offered_qty": 40,
				"inspected_on": today(),
				"accepted_qty": 40,
				"rejected_qty": 0,
			}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "IC / Inspection Note number"):
			doc.save()
		doc.reload()
		doc = _inspected(doc, 40, 0)
		doc.accepted_qty = 39
		doc.rejected_qty = 1
		with self.assertRaisesRegex(frappe.ValidationError, "locked"):
			doc.save()
		doc.reload()
		doc.cancelled = 1
		with self.assertRaisesRegex(frappe.ValidationError, "reason"):
			doc.save()
		doc.reload()
		doc.cancelled = 1
		doc.cancel_reason = "IC issued against the wrong order"
		doc.save()
		self.assertEqual(doc.status, il.CANCELLED)
		doc.cancelled = 0
		with self.assertRaisesRegex(frappe.ValidationError, "stays cancelled"):
			doc.save()

	def test_item_inspected_before_delivery_needs_pepl_final_inspection(self):
		doc = _lot(self.so, item=SHAFT, qty=10)
		doc.update({"offered_on": today(), "offered_qty": 10})
		with self.assertRaisesRegex(frappe.ValidationError, "PEPL's own final inspection"):
			doc.save()

	def test_dispatch_ships_only_what_the_ic_accepted(self):
		_receive(BOGIE, 20)
		so = make_sales_order([(BOGIE, 10)], submit=True).name
		dn = make_delivery_note(so, {BOGIE: 10})
		self.assertFalse(il.ic_gaps(dn))  # no lot, no tender: not an agency order
		lot = _lot(so, qty=10)
		gaps = il.ic_gaps(dn)
		self.assertEqual(len(gaps), 1)
		self.assertIn("no IC yet", gaps[0][1])
		_inspected(lot, 6, 0)  # 6 of the 10 offered so far, all accepted (no NCR to hold the dispatch)
		gaps = dg.delivery_gaps(dn)
		self.assertIn(
			f"ICs of {so} accepted 6, 0 already delivered; this delivery would make 10", [g[1] for g in gaps]
		)
		first = make_delivery_note(so, {BOGIE: 6}, submit=True)  # inside the IC: the gate lets it go
		self.assertEqual(first.docstatus, 1)
		second = make_delivery_note(so, {BOGIE: 1})
		self.assertIn(
			f"ICs of {so} accepted 6, 6 already delivered; this delivery would make 7",
			[g[1] for g in dg.delivery_gaps(second)],
		)
		with self.assertRaisesRegex(frappe.ValidationError, "already delivered"):
			second.submit()
		panel = " | ".join(r["text"] for r in dg.get_dispatch_panel(second.name))
		self.assertIn("agency ICs accepted 6, delivered 6, left to ship 0", panel)
