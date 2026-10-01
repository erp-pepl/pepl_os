"""C2-15 - Heat numbers at the gate, Receipt Log, Split by heat and the heat trace."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import add_days, today

from pepl_os.pepl_stores import heat
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.pepl_stores.trace import heat_trace
from pepl_os.tests.factories import TEST_COMPANY, make_file, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, set_param

ROD = "PEPL-T-HEAT-ROD"
S1 = "PEPL T HEAT Mill One"
S2 = "PEPL T HEAT Mill Two"


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _supplier(name):
	if not frappe.db.exists("Supplier", name):
		make_supplier(name).insert(ignore_permissions=True)
	frappe.db.set_value("Supplier", name, "custom_approval_state", "Approved")
	return name


def _po(supplier, qty):
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": supplier,
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 5),
			"items": [
				{
					"item_code": ROD,
					"qty": qty,
					"rate": 50,
					"schedule_date": add_days(today(), 5),
					"warehouse": _wh("RM Stores"),
				}
			],
		}
	).insert(ignore_permissions=True)
	po.submit()
	return po


def _receipt(supplier, qty, heat_number=None, mtc=True):
	pr = make_purchase_receipt(_po(supplier, qty).name)
	for row in pr.items:
		row.custom_heat_number = heat_number
		row.custom_test_certificate = make_file(f"mtc-{heat_number}.pdf") if mtc and heat_number else None
	pr.insert(ignore_permissions=True)
	return pr


class TestHeatNumbers(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_item(ROD, st.RAW_MATERIAL, valuation_rate=50)
		_supplier(S1)
		_supplier(S2)

	def setUp(self):
		set_param("custom_po_approval_value_threshold", 0)
		set_param("custom_heat_number_gate_mode", heat.HARD_BLOCK)
		set_param("custom_enforce_override_reason", 1)

	def test_batches_switched_on_by_setup(self):
		# Regression: ERPNext v16 refuses every Batch until this Stock Settings switch is on.
		frappe.db.set_single_value("Stock Settings", heat.BATCH_SWITCH, 0)
		self.assertTrue(heat.enable_batches())
		self.assertTrue(heat.batches_enabled())
		self.assertFalse(heat.enable_batches())  # already on: nothing to do

	def test_new_raw_material_is_heat_batch_item(self):
		item = frappe.get_doc("Item", ROD)
		self.assertEqual((item.custom_heat_tracked, item.has_batch_no, item.create_new_batch), (1, 1, 0))
		other = make_item("PEPL-T-HEAT-BO", st.BOUGHT_OUT)
		self.assertEqual((other.custom_heat_tracked, other.has_batch_no), (0, 0))

	def test_pr_without_heat_refused_in_hard_block(self):
		pr = _receipt(S1, 10, heat_number=None)
		with self.assertRaises(frappe.ValidationError) as ctx:
			pr.submit()
		self.assertIn("heat number", str(ctx.exception))

	def test_pr_without_mtc_refused(self):
		pr = _receipt(S1, 10, heat_number="H-NOMTC-1", mtc=False)
		with self.assertRaises(frappe.ValidationError) as ctx:
			pr.submit()
		self.assertIn("MTC", str(ctx.exception))

	def test_reason_mode_logs_override(self):
		from pepl_os.common.overrides import log_override

		set_param("custom_heat_number_gate_mode", heat.REASON_REQUIRED)
		pr = _receipt(S1, 10, heat_number="H-REASON-1", mtc=False)
		self.assertEqual(heat.heat_gate_check("Purchase Receipt", pr.name)["rule_code"], heat.GATE_RULE)
		with self.assertRaises(frappe.ValidationError):
			pr.submit()
		log_override(
			heat.GATE_RULE, "Purchase Receipt", pr.name, "MTC missing", "MTC follows by courier tomorrow"
		)
		pr.reload()
		pr.submit()
		self.assertEqual(pr.docstatus, 1)

	def test_batch_created_per_supplier_heat(self):
		pr = _receipt(S1, 10, heat_number="H-B-100")
		row = pr.items[0]
		self.assertTrue(row.batch_no)
		batch = frappe.get_doc("Batch", row.batch_no)
		self.assertEqual((batch.item, batch.supplier, batch.custom_heat_number), (ROD, S1, "H-B-100"))
		self.assertTrue(batch.custom_test_certificate)
		again = _receipt(S1, 5, heat_number="H-B-100")  # same supplier, same heat: the same batch
		self.assertEqual(again.items[0].batch_no, row.batch_no)

	def test_same_heat_two_suppliers_two_batches(self):
		one = _receipt(S1, 10, heat_number="H-SAME-7")
		two = _receipt(S2, 10, heat_number="H-SAME-7")
		self.assertNotEqual(one.items[0].batch_no, two.items[0].batch_no)

	def test_split_by_heat_preserves_total_and_rate(self):
		pr = _receipt(S1, 100, heat_number=None)
		row = pr.items[0]
		heat.split_line(
			pr, row.name, [{"heat_number": "H-SPLIT-1", "qty": 60}, {"heat_number": "H-SPLIT-2", "qty": 40}]
		)
		pr.reload()
		self.assertEqual(
			[(r.custom_heat_number, r.qty, r.rate) for r in pr.items],
			[("H-SPLIT-1", 60, 50), ("H-SPLIT-2", 40, 50)],
		)
		self.assertTrue(all(r.purchase_order_item == row.purchase_order_item for r in pr.items))
		self.assertTrue(all(r.batch_no for r in pr.items))
		with self.assertRaises(frappe.ValidationError):  # totals must match
			heat.split_line(
				pr, pr.items[0].name, [{"heat_number": "X1", "qty": 10}, {"heat_number": "X2", "qty": 10}]
			)

	def test_receipt_log_one_row_per_line(self):
		pr = _receipt(S1, 100, heat_number=None)
		heat.split_line(
			pr,
			pr.items[0].name,
			[{"heat_number": "H-LOG-1", "qty": 70}, {"heat_number": "H-LOG-2", "qty": 30}],
		)
		pr.reload()
		for row in pr.items:
			row.custom_test_certificate = make_file(f"mtc-{row.custom_heat_number}.pdf")
		pr.save()
		pr.submit()
		logs = frappe.get_all(
			heat.RECEIPT_LOG,
			filters={"purchase_receipt": pr.name},
			fields=["heat_number", "qty", "status", "batch_no", "stock_class"],
			order_by="heat_number",
		)
		self.assertEqual(
			[(r.heat_number, r.qty, r.status) for r in logs],
			[("H-LOG-1", 70, "Active"), ("H-LOG-2", 30, "Active")],
		)
		self.assertTrue(all(r.batch_no and r.stock_class == st.RAW_MATERIAL for r in logs))

	def test_pr_cancel_marks_log_cancelled(self):
		pr = _receipt(S1, 10, heat_number="H-CANCEL-1")
		pr.submit()
		pr.cancel()
		statuses = frappe.get_all(heat.RECEIPT_LOG, filters={"purchase_receipt": pr.name}, pluck="status")
		self.assertEqual(statuses, ["Cancelled"])  # kept, never deleted

	def test_heat_trace_follows_receipt_to_issue(self):
		pr = _receipt(S1, 50, heat_number="H-TRACE-1")
		pr.submit()
		batch = pr.items[0].batch_no
		issue = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Issue",
				"company": TEST_COMPANY,
				"items": [
					{
						"item_code": ROD,
						"qty": 30,
						"s_warehouse": _wh("RM Stores"),
						"batch_no": batch,
						"use_serial_batch_fields": 1,
					}
				],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(issue.items[0].custom_heat_number, "H-TRACE-1")  # heat copied from the batch
		issue.submit()
		trail = heat_trace("H-TRACE-1")
		self.assertEqual([(r.voucher_type, r.voucher_no) for r in trail][:1], [("Purchase Receipt", pr.name)])
		self.assertIn(("Stock Entry", issue.name), [(r.voucher_type, r.voucher_no) for r in trail])

	def test_heat_field_item_issue_needs_heat(self):
		item = make_item("PEPL-T-HEAT-FIELD", st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10)
		frappe.db.set_value("Item", item.name, "custom_heat_tracked", 1)  # heat field, no batch
		frappe.clear_document_cache("Item", item.name)
		receipt = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": TEST_COMPANY,
				"items": [
					{"item_code": item.name, "qty": 10, "basic_rate": 10, "t_warehouse": _wh("RM Stores")}
				],
			}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			receipt.submit()
		receipt.reload()
		receipt.items[0].custom_heat_number = "H-FIELD-1"
		receipt.save()
		receipt.submit()
		self.assertEqual([r.voucher_no for r in heat_trace("H-FIELD-1")], [receipt.name])
