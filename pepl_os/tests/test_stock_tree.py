"""C2-04 - Seven-class stock tree, stores and the CSM rule."""

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import PEPLTestCase


def _wh(store):
	return frappe.db.get_value("Warehouse", {"company": TEST_COMPANY, "warehouse_name": store}, "name")


class TestStockTree(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)

	def test_every_class_sits_under_the_root(self):
		root = st.root_item_group()
		for name in st.STOCK_CLASSES:
			self.assertEqual(frappe.db.get_value("Item Group", name, "parent_item_group"), root, name)
			self.assertTrue(frappe.db.get_value("Item Group", name, "is_group"), name)
		for name in st.SCRAP_CHILDREN:
			self.assertEqual(frappe.db.get_value("Item Group", name, "parent_item_group"), st.SCRAP)

	def test_seed_is_repeatable(self):
		st.seed_stock_structure(TEST_COMPANY)
		self.assertEqual(st.seed_item_groups(), {})

	def test_stock_class_set_from_group(self):
		item = make_item("PEPL-T-BRASS-SCRAP", "Brass Scrap")
		self.assertEqual(item.custom_stock_class, st.SCRAP)
		self.assertEqual(st.stock_class_of("Brass Scrap"), st.SCRAP)
		self.assertIsNone(st.stock_class_of("_Test Item Group"))

	def test_rm_group_placed_by_material_base(self):
		group = frappe.get_doc(
			{
				"doctype": "PEPL RM Group",
				"group_name": "PEPL-T-CUTTING-OIL",
				"material_base": "Consumable",
				"default_uom": "Nos",
				"auto_sync_to_item_group": 1,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(
			frappe.db.get_value("Item Group", group.linked_item_group, "parent_item_group"), st.RAW_MATERIAL
		)
		moved = st.seed_item_groups()
		self.assertEqual(moved.get(group.linked_item_group), st.CONSUMABLES)
		self.assertEqual(st.stock_class_of(group.linked_item_group), st.CONSUMABLES)

	def test_item_outside_tree_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_item("PEPL-T-OUTSIDE", "_Test Item Group")

	def test_existing_item_outside_tree_is_only_warned(self):
		frappe.flags.pepl_allow_items_outside_tree = True
		try:
			item = make_item("PEPL-T-LEGACY", "_Test Item Group")
		finally:
			frappe.flags.pepl_allow_items_outside_tree = False
		item.description = "Legacy item, reclassified later from the C2-01 audit"
		item.save(ignore_permissions=True)  # unchanged group: only an orange message

		other = frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": "PEPL-T-OUTSIDE-2",
				"parent_item_group": st.root_item_group(),
			}
		).insert(ignore_permissions=True)
		item.item_group = other.name
		with self.assertRaises(frappe.ValidationError):
			item.save(ignore_permissions=True)

	def test_capital_item_not_stock(self):
		item = make_item("PEPL-T-LATHE", st.CAPITAL, is_stock_item=1)
		self.assertEqual(item.is_stock_item, 0)
		self.assertEqual(item.custom_stock_class, st.CAPITAL)

	def test_csm_item_is_customer_provided(self):
		item = make_item("PEPL-T-CSM-BAR", st.CSM, is_purchase_item=1)
		self.assertEqual((item.is_customer_provided_item, item.is_purchase_item), (1, 0))

	def test_customer_provided_item_outside_csm_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_item("PEPL-T-CP-WRONG", st.RAW_MATERIAL, is_customer_provided_item=1, is_purchase_item=0)

	def test_stores_created(self):
		for store in (*st.LEAF_STORES, *st.CSM_STORES, "WIP Main Workshop"):
			self.assertTrue(_wh(store), store)
		csm_group = _wh(st.CSM_GROUP)
		for store in st.CSM_STORES:
			self.assertEqual(frappe.db.get_value("Warehouse", _wh(store), "parent_warehouse"), csm_group)
			self.assertTrue(st.is_csm_warehouse(_wh(store)))
		self.assertFalse(st.is_csm_warehouse(_wh("RM Stores")))

	def test_every_company_gets_the_stores(self):
		st.seed_stock_structure()
		for company in frappe.get_all("Company", pluck="name"):
			for store in ("RM Stores", "CSM Stores", "WIP Main Workshop"):
				self.assertTrue(
					frappe.db.exists("Warehouse", {"company": company, "warehouse_name": store}),
					f"{company}: {store}",
				)

	def test_new_company_gets_the_stores_at_once(self):
		# Regression: a company made in the setup wizard (after install) had no
		# PEPL stores until the next migrate, so Material Requests fell back to
		# ERPNext's "Stores" warehouse.
		name = "_Test PEPL New Company"
		if not frappe.db.exists("Company", name):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": name,
					"abbr": "_TPNC",
					"default_currency": "INR",
					"country": "India",
				}
			).insert()
		for store in ("RM Stores", "Bought-Out Stores", "CSM Stores", "WIP Main Workshop"):
			self.assertTrue(
				frappe.db.exists("Warehouse", {"company": name, "warehouse_name": store}), store
			)
		bought_out = frappe.get_doc("Item Group", st.BOUGHT_OUT)
		self.assertTrue(any(d.company == name for d in bought_out.item_group_defaults))

	def test_reapply_is_system_manager_only(self):
		from pepl_os.tests.utils import make_user

		self.assertIn(TEST_COMPANY, st.reapply_stock_structure())
		frappe.set_user(make_user("pepl.stores.reapply@example.com"))
		try:
			with self.assertRaises(frappe.PermissionError):
				st.reapply_stock_structure()
		finally:
			frappe.set_user("Administrator")

	def test_item_group_default_store(self):
		def default(group):
			return frappe.db.get_value(
				"Item Default",
				{"parent": group, "parenttype": "Item Group", "company": TEST_COMPANY},
				"default_warehouse",
			)

		self.assertEqual(default(st.RAW_MATERIAL), _wh("RM Stores"))
		self.assertEqual(default("Brass Scrap"), _wh("Scrap Yard"))
		self.assertEqual(default(st.CSM), _wh("CSM Stores"))
		self.assertEqual(default(st.WIP), _wh("WIP Main Workshop"))
		self.assertIsNone(default(st.CAPITAL))

	def _receipt(self, item_code, store, rate):
		return make_stock_entry(
			item_code=item_code,
			qty=5,
			to_warehouse=_wh(store),
			company=TEST_COMPANY,
			rate=rate,
			do_not_save=True,
		)

	def test_csm_item_blocked_from_pepl_warehouse(self):
		make_item("PEPL-T-CSM-1", st.CSM)
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._receipt("PEPL-T-CSM-1", "RM Stores", 0).insert(ignore_permissions=True)
		self.assertIn("customer-supplied", str(ctx.exception))

	def test_pepl_item_blocked_from_csm_warehouse(self):
		make_item("PEPL-T-RM-1", st.RAW_MATERIAL, valuation_rate=10)
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._receipt("PEPL-T-RM-1", "CSM Stores", 10).insert(ignore_permissions=True)
		self.assertIn("PEPL material", str(ctx.exception))

	def test_csm_receipt_zero_valued(self):
		make_item("PEPL-T-CSM-2", st.CSM)
		entry = self._receipt("PEPL-T-CSM-2", "CSM Stores", 100)
		entry.insert(ignore_permissions=True)
		entry.submit()
		sle = frappe.get_all(
			"Stock Ledger Entry",
			filters={"voucher_no": entry.name, "is_cancelled": 0},
			fields=["valuation_rate", "stock_value", "actual_qty"],
		)
		self.assertEqual(len(sle), 1)
		self.assertEqual(sle[0].actual_qty, 5)
		self.assertEqual(sle[0].valuation_rate, 0)
		self.assertEqual(sle[0].stock_value, 0)
