"""C2-09 - RFQ filled in by RM group from a submitted Material Request."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_purchase import rfq
from pepl_os.pepl_purchase import supplier_approval as sa
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, set_param


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


def _rm_group(name, base):
	if frappe.db.exists("PEPL RM Group", name):
		return frappe.get_doc("PEPL RM Group", name)
	return frappe.get_doc(
		{
			"doctype": "PEPL RM Group",
			"group_name": name,
			"material_base": base,
			"default_uom": "Kg",
			"auto_sync_to_item_group": 1,
		}
	).insert(ignore_permissions=True)


def _supplier(name, state, groups):
	if frappe.db.exists("Supplier", name):
		return name
	supplier = make_supplier(name, custom_rm_groups=[{"rm_group": g} for g in groups]).insert(
		ignore_permissions=True
	)
	frappe.db.set_value("Supplier", supplier.name, "custom_approval_state", state)
	return supplier.name


def _material_request(lines):
	doc = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": TEST_COMPANY,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 7),
			"items": [
				{
					"item_code": code,
					"qty": qty,
					"uom": "Nos",
					"conversion_factor": 1,
					"schedule_date": add_days(today(), 7),
					"warehouse": _wh("RM Stores"),
				}
				for code, qty in lines
			],
		}
	).insert(ignore_permissions=True)
	doc.submit()
	return doc


def _all_ticked(plan):
	return [
		{
			"rm_group": g["rm_group"],
			"lines": [l["name"] for l in g["lines"]],
			"suppliers": [s["supplier"] for s in g["suppliers"]],
		}
		for g in plan["groups"]
	]


class TestRFQByRMGroup(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		cls.brass = _rm_group("PEPL-T-RFQ-BRASS", "Brass")
		cls.steel = _rm_group("PEPL-T-RFQ-STEEL", "Steel")
		st.seed_item_groups()
		cls.brass.reload()
		cls.steel.reload()
		make_item("PEPL-T-RFQ-BRASS-ROD", cls.brass.linked_item_group)
		make_item("PEPL-T-RFQ-STEEL-BAR", cls.steel.linked_item_group)
		make_item("PEPL-T-RFQ-BO", st.BOUGHT_OUT)
		cls.brass_ok = _supplier("PEPL T RFQ Brass Approved", "Approved", [cls.brass.name])
		cls.brass_cond = _supplier("PEPL T RFQ Brass Conditional", "Conditionally Approved", [cls.brass.name])
		cls.brass_expired = _supplier("PEPL T RFQ Brass Expired", "Expired", [cls.brass.name])
		cls.steel_ok = _supplier("PEPL T RFQ Steel Approved", "Approved", [cls.steel.name])
		cls.brass_draft = _supplier("PEPL T RFQ Brass Draft", "Draft", [cls.brass.name])

	def _groups(self, plan):
		return {g["rm_group"]: g for g in plan["groups"]}

	def test_rfq_prefills_only_approved_suppliers_of_group(self):
		mr = _material_request([("PEPL-T-RFQ-BRASS-ROD", 5), ("PEPL-T-RFQ-STEEL-BAR", 3)])
		groups = self._groups(rfq.plan(mr.name))
		brass = [s["supplier"] for s in groups[self.brass.name]["suppliers"]]
		steel = [s["supplier"] for s in groups[self.steel.name]["suppliers"]]
		self.assertEqual(sorted(brass), sorted([self.brass_ok, self.brass_cond]))
		self.assertEqual(steel, [self.steel_ok])
		self.assertNotIn(self.brass_draft, brass)

	def test_expired_supplier_not_prefilled(self):
		mr = _material_request([("PEPL-T-RFQ-BRASS-ROD", 2)])
		brass = [s["supplier"] for s in self._groups(rfq.plan(mr.name))[self.brass.name]["suppliers"]]
		self.assertNotIn(self.brass_expired, brass)
		frappe.db.set_value("Supplier", self.brass_ok, "disabled", 1)
		try:
			brass = [s["supplier"] for s in self._groups(rfq.plan(mr.name))[self.brass.name]["suppliers"]]
			self.assertNotIn(self.brass_ok, brass)
		finally:
			frappe.db.set_value("Supplier", self.brass_ok, "disabled", 0)

	def test_one_rfq_per_rm_group(self):
		mr = _material_request(
			[("PEPL-T-RFQ-BRASS-ROD", 5), ("PEPL-T-RFQ-STEEL-BAR", 3), ("PEPL-T-RFQ-BRASS-ROD", 1)]
		)
		made = rfq.create(mr.name, _all_ticked(rfq.plan(mr.name)))
		self.assertEqual(len(made), 2)
		by_group = {frappe.db.get_value("Request for Quotation", n, "custom_rm_group"): n for n in made}
		brass = frappe.get_doc("Request for Quotation", by_group[self.brass.name])
		steel = frappe.get_doc("Request for Quotation", by_group[self.steel.name])
		self.assertEqual(brass.docstatus, 0)
		self.assertEqual(brass.custom_material_request, mr.name)
		self.assertEqual(
			sorted(r.supplier for r in brass.suppliers), sorted([self.brass_ok, self.brass_cond])
		)
		self.assertEqual([r.supplier for r in steel.suppliers], [self.steel_ok])
		self.assertEqual(
			[(r.item_code, r.qty) for r in brass.items],
			[("PEPL-T-RFQ-BRASS-ROD", 5), ("PEPL-T-RFQ-BRASS-ROD", 1)],
		)
		self.assertTrue(all(r.material_request == mr.name and r.material_request_item for r in brass.items))
		self.assertEqual([r.item_code for r in steel.items], ["PEPL-T-RFQ-STEEL-BAR"])

	def test_lines_already_on_an_rfq_are_not_sent_twice(self):
		mr = _material_request([("PEPL-T-RFQ-STEEL-BAR", 4)])
		rfq.create(mr.name, _all_ticked(rfq.plan(mr.name)))
		plan = rfq.plan(mr.name)
		self.assertEqual(plan["groups"], [])
		self.assertEqual(len(plan["skipped"]), 1)
		with self.assertRaises(frappe.ValidationError):
			rfq.create(
				mr.name,
				[{"rm_group": self.steel.name, "lines": [mr.items[0].name], "suppliers": [self.steel_ok]}],
			)

	def test_line_sent_under_the_wrong_group_refused(self):
		mr = _material_request([("PEPL-T-RFQ-STEEL-BAR", 2)])
		with self.assertRaises(frappe.ValidationError):
			rfq.create(
				mr.name,
				[{"rm_group": self.brass.name, "lines": [mr.items[0].name], "suppliers": [self.brass_ok]}],
			)

	def test_items_without_rm_group_get_no_suggestion(self):
		mr = _material_request([("PEPL-T-RFQ-BO", 2)])
		groups = self._groups(rfq.plan(mr.name))
		self.assertEqual(groups[rfq.NO_GROUP]["suppliers"], [])
		with self.assertRaises(frappe.ValidationError):  # a group with no supplier chosen
			rfq.create(mr.name, [{"rm_group": "", "lines": [mr.items[0].name], "suppliers": []}])

	def test_draft_request_refused(self):
		doc = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": TEST_COMPANY,
				"schedule_date": add_days(today(), 7),
				"items": [
					{
						"item_code": "PEPL-T-RFQ-STEEL-BAR",
						"qty": 1,
						"uom": "Nos",
						"schedule_date": add_days(today(), 7),
						"warehouse": _wh("RM Stores"),
					}
				],
			}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			rfq.plan(doc.name)

	def test_supplier_approved_for_another_group_needs_reason(self):
		set_param("custom_enforce_override_reason", 1)
		mr = _material_request([("PEPL-T-RFQ-STEEL-BAR", 2)])
		made = rfq.create(
			mr.name,
			[{"rm_group": self.steel.name, "lines": [mr.items[0].name], "suppliers": [self.brass_ok]}],
		)
		doc = frappe.get_doc("Request for Quotation", made[0])
		pairs = sa.unapproved_suppliers(doc)
		self.assertEqual([p[0] for p in pairs], [self.brass_ok])
		self.assertIn(self.steel.name, pairs[0][1])
		doc.suppliers[0].supplier = self.steel_ok
		self.assertEqual(sa.unapproved_suppliers(doc), [])
