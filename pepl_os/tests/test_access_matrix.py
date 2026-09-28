"""A2 - Role Access Matrix and CEO view access."""

import frappe

from pepl_os.common.rights import OWN, YES, combine, summarise
from pepl_os.pepl_governance import access_matrix
from pepl_os.pepl_governance.report.pepl_role_access_matrix import pepl_role_access_matrix
from pepl_os.setup import permissions
from pepl_os.tests.utils import PEPLTestCase


class TestRightsArithmetic(PEPLTestCase):
	def test_union_of_roles(self):
		rows = [
			{"role": "A", "permlevel": 0, "read": 1},
			{"role": "B", "permlevel": 0, "read": 1, "write": 1},
		]
		self.assertEqual(combine(rows, ["A"])["write"], "")
		self.assertEqual(combine(rows, ["A", "B"])["write"], YES)

	def test_if_owner_rule_is_own_only(self):
		rows = [{"role": "A", "permlevel": 0, "if_owner": 1, "read": 1, "write": 1}]
		self.assertEqual(combine(rows, ["A"])["write"], OWN)

	def test_higher_permlevel_ignored(self):
		rows = [{"role": "A", "permlevel": 1, "read": 1, "write": 1}]
		self.assertEqual(combine(rows, ["A"])["read"], "")

	def test_baseline_roles_count(self):
		rows = [{"role": "Desk User", "permlevel": 0, "read": 1}]
		self.assertEqual(combine(rows, [])["read"], YES)

	def test_no_read_means_no_record_rights(self):
		rows = [{"role": "A", "permlevel": 0, "print": 1, "export": 1}]
		result = combine(rows, ["A"])
		self.assertEqual(result["print"], "")
		self.assertEqual(result["export"], YES)

	def test_plain_words(self):
		self.assertEqual(summarise(combine([], [])), "No access")
		rows = [{"role": "A", "permlevel": 0, "read": 1, "create": 1, "write": 1, "submit": 1}]
		self.assertEqual(summarise(combine(rows, ["A"])), "View, create, edit, submit (finalise)")


class TestProfileAccess(PEPLTestCase):
	def assertRight(self, profile, doctype, right, expected):
		if not frappe.db.exists("DocType", doctype):
			return
		self.assertEqual(
			access_matrix.rights_for(profile, doctype)[right], expected, f"{profile} / {doctype} / {right}"
		)

	def test_stores_receives_goods_but_cannot_order(self):
		self.assertRight("PEPL Stores", "Purchase Receipt", "create", YES)
		self.assertRight("PEPL Stores", "Material Request", "create", YES)
		self.assertRight("PEPL Stores", "Purchase Order", "read", YES)
		self.assertRight("PEPL Stores", "Purchase Order", "create", "")

	def test_purchase_manager_creates_suppliers_and_items(self):
		self.assertRight("PEPL Purchase Manager", "Supplier", "create", YES)
		self.assertRight("PEPL Purchase Manager", "Item", "create", YES)
		self.assertRight("PEPL Purchase Manager", "Purchase Order", "submit", YES)

	def test_ceo_views_everything_changes_nothing(self):
		for doctype in ("Purchase Order", "Sales Order", "Stock Entry", "Supplier", "Work Order"):
			self.assertRight("PEPL CEO", doctype, "read", YES)
			self.assertRight("PEPL CEO", doctype, "print", YES)
			self.assertRight("PEPL CEO", doctype, "report", YES)
			for right in ("create", "write", "submit", "cancel", "delete"):
				self.assertRight("PEPL CEO", doctype, right, "")

	def test_accounts_sees_purchase_orders_for_bill_matching(self):
		self.assertRight("PEPL Accounts", "Purchase Order", "read", YES)
		self.assertRight("PEPL Accounts", "Purchase Order", "create", "")
		self.assertRight("PEPL Accounts", "Purchase Invoice", "submit", YES)

	def test_nobody_in_the_matrix_can_delete(self):
		rows = access_matrix.get_rows()
		self.assertTrue(rows)
		self.assertEqual([r for r in rows if r["delete"]], [])


class TestCeoViewGrant(PEPLTestCase):
	def test_grant_is_idempotent(self):
		permissions.grant_ceo_view()
		self.assertEqual(permissions.grant_ceo_view(), [])

	def test_grant_restores_a_removed_view_right(self):
		permissions.grant_ceo_view(["Purchase Order"])
		frappe.db.set_value(
			"Custom DocPerm", {"parent": "Purchase Order", "role": "PEPL CEO", "permlevel": 0}, "print", 0
		)
		frappe.clear_cache(doctype="Purchase Order")
		self.assertEqual(permissions.grant_ceo_view(["Purchase Order"]), ["Purchase Order"])
		self.assertEqual(access_matrix.rights_for("PEPL CEO", "Purchase Order")["print"], YES)

	def test_logs_are_not_in_the_ceo_list(self):
		for doctype in ("Version", "Access Log", "Deleted Document"):
			self.assertNotIn(doctype, permissions.ceo_view_doctypes())


class TestMatrixReport(PEPLTestCase):
	def test_columns_and_filters(self):
		columns, rows, _message = pepl_role_access_matrix.execute(
			{"role_profile": "PEPL Stores", "only_with_access": 1}
		)
		fields = [c["fieldname"] for c in columns]
		self.assertEqual(fields[:4], ["role_profile", "area", "document", "in_plain_words"])
		self.assertIn("delete", fields)
		self.assertTrue(rows)
		self.assertEqual({r["role_profile"] for r in rows}, {"PEPL Stores"})
		self.assertNotIn("No access", {r["in_plain_words"] for r in rows})

	def test_area_filter(self):
		_c, rows, _m = pepl_role_access_matrix.execute({"area": "Purchase"})
		self.assertTrue(rows)
		self.assertEqual({r["area"] for r in rows}, {"Purchase"})
