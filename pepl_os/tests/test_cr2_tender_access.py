"""CR2 - Tender data (PEPL Tender, PEPL CST Cost Sheet) open only to the users listed in site_config.json."""

from unittest.mock import patch

import frappe

from pepl_os.pepl_governance import audit_trail
from pepl_os.pepl_governance import tender_access as ta
from pepl_os.pepl_production import costing
from pepl_os.setup import permissions, roles
from pepl_os.tests.utils import PEPLTestCase, make_user

ONE = "cr2.tender.one@example.com"  # listed
OTHER = "cr2.system.manager@example.com"  # a System Manager who also holds the tender role, NOT listed
PLAIN = "cr2.sales.user@example.com"  # an ordinary sales login, not listed
TENDER_ROLES = ["PEPL Tender Manager", "Sales User"]


class TenderAccessCase(PEPLTestCase):
	listed = (ONE,)

	def setUp(self):
		self._had_conf = ta.CONF_KEY in frappe.local.conf
		self._conf = frappe.local.conf.get(ta.CONF_KEY)
		frappe.local.conf[ta.CONF_KEY] = list(self.listed)
		make_user(ONE, roles=TENDER_ROLES)
		make_user(OTHER, roles=["System Manager", "Sales Manager", *TENDER_ROLES])
		make_user(PLAIN, roles=["Sales User"])
		ta.sync_access_role()

	def tearDown(self):
		if self._had_conf:
			frappe.local.conf[ta.CONF_KEY] = self._conf
		else:
			frappe.local.conf.pop(ta.CONF_KEY, None)

	def set_list(self, value):
		frappe.local.conf[ta.CONF_KEY] = value

	@staticmethod
	def tender(name="TND-T-CR2-1"):
		return frappe.get_doc({"doctype": ta.TENDER, "name": name, "status": "Draft"})

	@staticmethod
	def cost_sheet(name="CST-T-CR2-1"):
		return frappe.get_doc({"doctype": ta.COST_SHEET, "name": name, "cst_title": "CR2", "status": "Draft"})


class TestWhoMaySee(TenderAccessCase):
	def test_what_user_sees_runs_on_a_site_with_a_tender(self):
		# 0.79.5 regression: Check 62's helper called frappe.has_permission(..., print_logs=False), which v16 refuses
		# (TypeError) once a tender exists on the site (bench, 24 Nov 2026).
		tender = self.tender("TND-T-CR2-SEES")
		if not frappe.db.exists(ta.TENDER, tender.name):
			tender.db_insert()
		for_plain = ta.what_user_sees(PLAIN)
		self.assertFalse(for_plain["opens_a_tender"])
		self.assertEqual(for_plain["counts"][ta.TENDER], 0)
		self.assertTrue(ta.what_user_sees(ONE)["opens_a_tender"])

	def test_listed_user_and_administrator_may_everyone_else_not(self):
		self.assertTrue(ta.is_active())
		self.assertTrue(ta.can_access(ONE))
		self.assertTrue(ta.can_access("Administrator"))
		self.assertFalse(ta.can_access(OTHER))  # System Manager is not enough
		self.assertFalse(ta.can_access(PLAIN))

	def test_session_user_is_asked_when_no_user_is_given(self):
		frappe.set_user(OTHER)
		self.assertFalse(ta.can_access())
		frappe.set_user(ONE)
		self.assertTrue(ta.can_access())

	def test_no_list_means_no_restriction(self):
		self.set_list([])
		self.assertFalse(ta.is_active())
		self.assertTrue(ta.can_access(PLAIN))
		frappe.local.conf.pop(ta.CONF_KEY, None)
		self.assertTrue(ta.can_access(PLAIN))

	def test_list_may_be_text_with_any_case_and_spaces(self):
		self.set_list(" CR2.Tender.One@Example.com , someone@example.com,, ")
		self.assertEqual(ta.allowed_users(), [ONE, "someone@example.com"])
		self.assertTrue(ta.can_access(ONE))
		self.assertTrue(ta.can_access(ONE.upper()))

	def test_three_pepl_users(self):
		self.set_list(
			["ankit@parasramkagroup.com", "sudam@parasramkagroup.com", "aviral@parasramkagroup.com"]
		)
		self.assertTrue(ta.can_access("Sudam@parasramkagroup.com"))
		self.assertFalse(ta.can_access(ONE))


class TestRecords(TenderAccessCase):
	def test_tender_opens_only_for_the_listed_user(self):
		for ptype in ("read", "write", "create", "delete"):
			self.assertFalse(frappe.has_permission(ta.TENDER, ptype, doc=self.tender(), user=OTHER), ptype)
		self.assertTrue(frappe.has_permission(ta.TENDER, "read", doc=self.tender(), user=ONE))

	def test_cost_sheet_opens_only_for_the_listed_user(self):
		self.assertFalse(frappe.has_permission(ta.COST_SHEET, "read", doc=self.cost_sheet(), user=OTHER))
		self.assertFalse(frappe.has_permission(ta.COST_SHEET, "read", doc=self.cost_sheet(), user=PLAIN))
		self.assertTrue(frappe.has_permission(ta.COST_SHEET, "read", doc=self.cost_sheet(), user=ONE))

	def test_hook_refuses_and_otherwise_leaves_it_to_the_roles(self):
		self.assertIs(ta.has_permission(self.tender(), "read", OTHER), False)
		self.assertIs(ta.has_permission(self.tender(), "read", ONE), True)  # v16: anything falsy would refuse

	def test_generated_document_only_when_made_for_a_tender(self):
		for_tender = frappe._dict(doctype=ta.GENERATED, tender="TND-1")
		for_order = frappe._dict(doctype=ta.GENERATED, tender=None, sales_order="SO-1")
		self.assertIs(ta.has_permission(for_tender, "read", PLAIN), False)
		self.assertIs(ta.has_permission(for_order, "read", PLAIN), True)
		self.assertIn("tender", ta.generated_document_conditions(PLAIN))
		self.assertEqual(ta.generated_document_conditions(ONE), "")

	def test_lists_reports_and_link_searches_return_nothing_for_others(self):
		for doctype in (*ta.GATED, *ta.CHILD_TABLES):
			self.assertEqual(ta.query_conditions(OTHER), "1=0", doctype)
			self.assertEqual(ta.query_conditions(ONE), "", doctype)
		self.assertEqual(frappe.get_list(ta.TENDER, user=OTHER), [])

	def test_every_list_condition_is_wired_in_hooks(self):
		hooks = frappe.get_hooks("permission_query_conditions")
		for doctype in (*ta.GATED, *ta.CHILD_TABLES, ta.GENERATED, *ta.RELATED):
			self.assertTrue(any(m.startswith(ta.__name__) for m in hooks.get(doctype, [])), doctype)
		perm_hooks = frappe.get_hooks("has_permission")
		for doctype in (*ta.GATED, ta.GENERATED, *ta.RELATED):
			self.assertTrue(any(m.startswith(ta.__name__) for m in perm_hooks.get(doctype, [])), doctype)

	def test_change_history_of_a_tender_hidden_from_others(self):
		for doctype, docname in ((ta.TENDER, "TND-T-CR2-HIST"), ("Item", "T-CR2-ITEM-HIST")):
			frappe.get_doc(
				{"doctype": "Version", "ref_doctype": doctype, "docname": docname, "data": '{"changed": []}'}
			).insert(ignore_permissions=True)
		names = ["TND-T-CR2-HIST", "T-CR2-ITEM-HIST"]
		frappe.set_user(OTHER)
		seen = frappe.get_list("Version", filters={"docname": ["in", names]}, pluck="docname")
		self.assertEqual(seen, ["T-CR2-ITEM-HIST"])
		frappe.set_user("Administrator")
		self.assertEqual(
			sorted(frappe.get_list("Version", filters={"docname": ["in", names]}, pluck="docname")),
			sorted(names),
		)

	def test_related_record_refused_one_by_one(self):
		cases = {
			"File": {"attached_to_doctype": ta.TENDER, "attached_to_name": "TND-1"},
			"Version": {"ref_doctype": ta.COST_SHEET, "docname": "CST-1"},
			"Comment": {"reference_doctype": ta.TENDER, "reference_name": "TND-1"},
			"ToDo": {"reference_type": ta.TENDER, "reference_name": "TND-1"},
			"Deleted Document": {"deleted_doctype": ta.TENDER, "deleted_name": "TND-1"},
			"Access Log": {"export_from": ta.TENDER, "reference_document": "TND-1"},
		}
		for doctype, values in cases.items():
			doc = frappe._dict(doctype=doctype, **values)
			self.assertIs(ta.has_related_permission(doc, "read", OTHER), False, doctype)
			self.assertIs(ta.has_related_permission(doc, "read", ONE), True, doctype)
		harmless = frappe._dict(doctype="File", attached_to_doctype="Sales Order", attached_to_name="SO-1")
		self.assertIs(ta.has_related_permission(harmless, "read", OTHER), True)

	def test_ordinary_files_and_tenders_without_a_list_stay_open(self):
		"""Regression guard: in Frappe v16 a hook answering None refuses, which would lock every File."""
		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "po.pdf",
				"attached_to_doctype": "Sales Order",
				"attached_to_name": "SO-1",
			}
		)
		self.assertIs(ta.has_related_permission(file_doc, "read", PLAIN), True)
		self.set_list([])
		self.assertIs(ta.has_related_permission(file_doc, "read", PLAIN), True)
		self.assertIs(ta.has_permission(self.tender(), "read", PLAIN), True)

	def test_file_of_a_tender_refused_through_frappe(self):
		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "bid.pdf",
				"attached_to_doctype": ta.TENDER,
				"attached_to_name": "TND-1",
			}
		)
		self.assertFalse(frappe.has_permission("File", "read", doc=file_doc, user=OTHER))

	def test_related_list_condition_names_every_tender_doctype(self):
		condition = ta.related_condition("Comment", OTHER)
		for doctype in (*ta.GATED, *ta.CHILD_TABLES, ta.GENERATED):
			self.assertIn(doctype, condition)
		self.assertEqual(ta.related_condition("Comment", ONE), "")


class TestNotPassedOn(TenderAccessCase):
	def _todo(self, allocated_to, reference_type=ta.TENDER):
		return frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": allocated_to,
				"reference_type": reference_type,
				"reference_name": "TND-1",
				"description": "x",
			}
		)

	def test_a_person_cannot_assign_a_tender_to_an_outsider(self):
		frappe.set_user(ONE)
		with self.assertRaises(frappe.PermissionError):
			ta.validate_todo(self._todo(OTHER))
		ta.validate_todo(self._todo(ONE))  # to a listed user: fine

	def test_system_alert_for_an_outsider_goes_to_the_first_listed_user(self):
		todo = self._todo(PLAIN)
		ta.validate_todo(todo)  # session user Administrator = scheduler
		self.assertEqual(todo.allocated_to.lower(), ONE)

	def test_other_assignments_untouched(self):
		frappe.set_user(ONE)
		todo = self._todo(PLAIN, reference_type="Sales Order")
		ta.validate_todo(todo)
		self.assertEqual(todo.allocated_to, PLAIN)

	def test_a_tender_cannot_be_shared_outside_the_list(self):
		share = frappe._dict(share_doctype=ta.TENDER, share_name="TND-1", user=OTHER, everyone=0)
		with self.assertRaises(frappe.PermissionError):
			ta.validate_docshare(share)
		with self.assertRaises(frappe.PermissionError):
			ta.validate_docshare(
				frappe._dict(share_doctype=ta.COST_SHEET, share_name="C", user=None, everyone=1)
			)
		ta.validate_docshare(frappe._dict(share_doctype=ta.TENDER, share_name="TND-1", user=ONE, everyone=0))

	def test_unguarded_pepl_sales_methods_now_ask_first(self):
		overrides = frappe.get_hooks("override_whitelisted_methods")
		for key, original in ta.GUARDED_METHODS.items():
			self.assertIn(f"{ta.__name__}.{key}", overrides.get(original, []), original)
			self.assertTrue(callable(getattr(ta, key)))
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			ta.get_tender_summary()
		frappe.set_user(ONE)
		with patch.object(frappe, "call", return_value=["ok"]) as called:
			self.assertEqual(ta.get_tender_summary(cmd="x"), ["ok"])
		called.assert_called_once_with(ta.GUARDED_METHODS["get_tender_summary"])


class TestTenderSalesOrder(TenderAccessCase):
	"""PEPL (Aviral ji, 16 Nov 2026): only the three make a Sales Order from a tender."""

	def _order(self, tender="TND-T-CR2-SO", name=None):
		return frappe._dict(doctype="Sales Order", name=name, custom_tender_reference=tender)

	def test_outsider_cannot_make_a_sales_order_from_a_tender(self):
		frappe.set_user(PLAIN)
		with self.assertRaises(frappe.PermissionError):
			ta.guard_sales_order_tender(self._order())
		frappe.set_user(OTHER)  # System Manager: refused too
		with self.assertRaises(frappe.PermissionError):
			ta.guard_sales_order_tender(self._order())

	def test_listed_user_and_administrator_can(self):
		frappe.set_user(ONE)
		ta.guard_sales_order_tender(self._order())
		frappe.set_user("Administrator")
		ta.guard_sales_order_tender(self._order())

	def test_outsider_works_on_an_existing_tender_order(self):
		frappe.set_user(PLAIN)
		ta.guard_sales_order_tender(self._order(tender=None))  # an ordinary order
		with patch.object(frappe.db, "get_value", return_value="TND-T-CR2-SO"):
			ta.guard_sales_order_tender(self._order(name="SO-CR2"))  # saving the order: link unchanged
			with self.assertRaises(frappe.PermissionError):
				ta.guard_sales_order_tender(self._order(tender="TND-OTHER", name="SO-CR2"))  # re-pointing it

	def test_no_list_no_restriction(self):
		self.set_list([])
		frappe.set_user(PLAIN)
		ta.guard_sales_order_tender(self._order())

	def test_guard_runs_before_frappe_blanks_the_field(self):
		events = frappe.get_hooks("doc_events")["Sales Order"]
		for event in ("before_insert", "before_validate"):
			self.assertIn(f"{ta.__name__}.guard_sales_order_tender", events[event])


class TestRoleRightsAndFields(TenderAccessCase):
	def test_role_follows_the_list(self):
		self.assertIn(ta.ACCESS_ROLE, frappe.get_roles(ONE))
		self.assertNotIn(ta.ACCESS_ROLE, frappe.get_roles(OTHER))
		self.set_list([PLAIN])
		result = ta.sync_access_role()
		self.assertIn(ONE, [u.lower() for u in result["removed"]])
		self.assertIn(PLAIN, [u.lower() for u in result["added"]])
		self.assertNotIn(ta.ACCESS_ROLE, frappe.get_roles(ONE))
		self.assertIn(ta.ACCESS_ROLE, frappe.get_roles(PLAIN))
		self.assertEqual(ta.sync_access_role(), {"added": [], "removed": [], "not_a_user": []})

	def test_role_given_by_hand_is_taken_away_on_save(self):
		user = frappe.get_doc("User", OTHER)
		user.append("roles", {"role": ta.ACCESS_ROLE})
		user.save(ignore_permissions=True)
		self.assertNotIn(ta.ACCESS_ROLE, frappe.get_roles(OTHER))

	def test_listed_email_without_a_login_is_reported(self):
		self.set_list([ONE, "cr2.nobody@example.com"])
		self.assertEqual(ta.sync_access_role()["not_a_user"], ["cr2.nobody@example.com"])

	def test_no_list_takes_the_role_from_everyone(self):
		self.set_list([])
		ta.sync_access_role()
		self.assertEqual(ta.holders(), [])

	def test_sales_order_tender_fields_hidden_while_the_list_is_set(self):
		present = [
			f
			for f in ta.SALES_ORDER_FIELDS
			if frappe.db.exists("Custom Field", {"dt": "Sales Order", "fieldname": f})
		]
		if not present:
			self.skipTest("pepl_sales tender fields not on Sales Order on this site")
		ta.set_sales_order_field_level()
		for f in present:
			self.assertEqual(
				frappe.db.get_value("Custom Field", {"dt": "Sales Order", "fieldname": f}, "permlevel"),
				ta.SALES_ORDER_LEVEL,
			)
		self.assertEqual(
			frappe.db.get_value(
				"Custom Field", {"dt": "Sales Order", "fieldname": "custom_sector"}, "permlevel"
			)
			or 0,
			0,
		)
		self.set_list([])
		ta.set_sales_order_field_level()
		for f in present:
			self.assertEqual(
				frappe.db.get_value("Custom Field", {"dt": "Sales Order", "fieldname": f}, "permlevel"), 0
			)

	def _readers(self, level):
		return sorted(
			frappe.get_all(
				"Custom DocPerm",
				filters={"parent": "Sales Order", "permlevel": level, "read": 1},
				pluck="role",
			)
		)

	def test_tender_fields_level_belongs_to_the_access_role_only(self):
		"""Regression (Check 62 on the bench, 17 Nov 2026): at level 1 ERPNext also lets Sales Manager read."""
		ta.grant_access_rights()
		self.assertNotEqual(ta.SALES_ORDER_LEVEL, 1)
		self.assertEqual(self._readers(ta.SALES_ORDER_LEVEL), [ta.ACCESS_ROLE])
		row = frappe.db.get_value(
			"Custom DocPerm",
			{"parent": "Sales Order", "permlevel": ta.SALES_ORDER_LEVEL, "role": ta.ACCESS_ROLE},
			["read", "write"],
		)
		self.assertEqual(tuple(row), (1, 1))
		self.assertNotIn(ta.ACCESS_ROLE, self._readers(1))  # our old level-1 row is gone ...
		erpnext_level_one = frappe.get_all(
			"DocPerm", filters={"parent": "Sales Order", "permlevel": 1}, pluck="role"
		)
		for role in erpnext_level_one:  # ... ERPNext's own level-1 rows (Ignore Pricing Rule) are kept
			self.assertIn(role, self._readers(1))

	def test_a_role_added_by_hand_to_the_tender_level_is_taken_away(self):
		from frappe.permissions import add_permission, update_permission_property

		ta.grant_access_rights()
		add_permission("Sales Order", "Sales Manager", ta.SALES_ORDER_LEVEL)
		update_permission_property(
			"Sales Order", "Sales Manager", ta.SALES_ORDER_LEVEL, "read", 1, validate=False
		)
		self.assertIn("Sales Manager", self._readers(ta.SALES_ORDER_LEVEL))
		ta.grant_access_rights()
		self.assertEqual(self._readers(ta.SALES_ORDER_LEVEL), [ta.ACCESS_ROLE])

	def test_old_level_one_row_is_removed_on_upgrade(self):
		from frappe.permissions import add_permission, update_permission_property

		add_permission("Sales Order", ta.ACCESS_ROLE, 1)
		update_permission_property("Sales Order", ta.ACCESS_ROLE, 1, "read", 1, validate=False)
		changed = ta.grant_access_rights()
		self.assertIn("Sales Order (level 1 row removed)", changed)
		self.assertNotIn(ta.ACCESS_ROLE, self._readers(1))

	def test_access_role_has_full_rights_and_keeps_delete(self):
		ta.grant_access_rights()
		permissions.restrict_delete([ta.TENDER, ta.COST_SHEET], force=True)
		for doctype, rights in ((ta.TENDER, ta.TENDER_RIGHTS), (ta.COST_SHEET, ta.COST_SHEET_RIGHTS)):
			row = next(
				r for r in permissions.perm_rows(doctype) if r.role == ta.ACCESS_ROLE and not r.permlevel
			)
			for right in rights:
				self.assertTrue(row.get(right), f"{doctype} {right}")
			self.assertNotIn(ta.ACCESS_ROLE, permissions.roles_with_delete(doctype))

	def test_delete_still_restricted_for_every_other_role(self):
		self.assertFalse(permissions.may_delete(ta.TENDER, "PEPL Tender Manager"))
		self.assertFalse(permissions.may_delete("Sales Order", ta.ACCESS_ROLE))
		self.assertTrue(permissions.may_delete(ta.TENDER, ta.ACCESS_ROLE))

	def test_ceo_no_longer_sees_tender_data(self):
		for doctype in ta.GATED:
			self.assertNotIn(doctype, permissions.ceo_view_doctypes())
		ta.grant_access_rights()
		for doctype in ta.GATED:
			self.assertFalse(
				frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": "PEPL CEO"}), doctype
			)
		self.assertNotIn("PEPL Tender Viewer", roles.ROLE_PROFILES["PEPL CEO"])

	def test_setup_is_safe_to_repeat(self):
		ta.apply_access_setup()
		again = ta.apply_access_setup()
		self.assertEqual(again["rights"], [])
		self.assertEqual(again["sales_order_fields"], [])
		self.assertEqual(again["role"], {"added": [], "removed": [], "not_a_user": []})


class TestProfiles(TenderAccessCase):
	def test_sales_and_tender_are_separate_profiles(self):
		self.assertEqual(roles.ROLE_PROFILES["PEPL Tender Only"], ("PEPL Tender Manager", "Sales User"))
		self.assertNotIn("PEPL Tender Manager", roles.ROLE_PROFILES["PEPL Sales Manager"])
		self.assertNotIn("PEPL Tender Executive", roles.ROLE_PROFILES["PEPL Sales Executive"])
		self.assertNotIn("PEPL Sales & Tender Manager", roles.ROLE_PROFILES)
		for profile, profile_roles in roles.ROLE_PROFILES.items():
			self.assertNotIn(ta.ACCESS_ROLE, profile_roles, profile)  # given only by the list

	def test_upgrade_takes_tender_roles_out_and_renames(self):
		old = "PEPL Sales & Tender Executive"
		if not frappe.db.exists("Role Profile", old):
			frappe.get_doc(
				{
					"doctype": "Role Profile",
					"role_profile": old,
					"roles": [{"role": "Sales User"}, {"role": "PEPL Tender Executive"}],
				}
			).insert(ignore_permissions=True)
		ceo = frappe.get_doc("Role Profile", "PEPL CEO")
		ceo.append("roles", {"role": "PEPL Tender Viewer"})
		ceo.save(ignore_permissions=True)
		from pepl_os.patches.v0_62 import split_tender_profiles

		split_tender_profiles.execute()
		have = set(
			frappe.get_all("Has Role", filters={"parent": old, "parenttype": "Role Profile"}, pluck="role")
		)
		self.assertNotIn(
			"PEPL Tender Executive", have
		)  # kept its old name: the new name is already taken here
		self.assertIn("Sales User", have)
		ceo = set(
			frappe.get_all(
				"Has Role", filters={"parent": "PEPL CEO", "parenttype": "Role Profile"}, pluck="role"
			)
		)
		self.assertNotIn("PEPL Tender Viewer", ceo)

	def test_rename_keeps_the_profile_when_the_new_name_is_free(self):
		old, new = "PEPL CR2 Old Profile", "PEPL CR2 New Profile"
		frappe.get_doc(
			{"doctype": "Role Profile", "role_profile": old, "roles": [{"role": "Sales User"}]}
		).insert(ignore_permissions=True)
		self.assertEqual(roles.rename_profiles({old: new}), {old: new})
		self.assertTrue(frappe.db.exists("Role Profile", new))
		self.assertFalse(frappe.db.exists("Role Profile", old))
		self.assertEqual(roles.rename_profiles({old: new}), {})


class TestReports(TenderAccessCase):
	ROWS = (
		{"reference_doctype": ta.TENDER, "reference_name": "TND-1", "time": "2026-11-15 10:00:00"},
		{"reference_doctype": ta.COST_SHEET, "reference_name": "CST-1", "time": "2026-11-15 10:00:00"},
		{"reference_doctype": "Sales Order", "reference_name": "SO-1", "time": "2026-11-15 10:00:00"},
		{"reference_doctype": None, "reference_name": None, "time": "2026-11-15 10:00:00"},
	)

	def test_audit_trail_shows_tender_events_only_to_the_listed_users(self):
		frappe.set_user(OTHER)
		kept = ta.filter_events(list(self.ROWS))
		self.assertEqual([r["reference_doctype"] for r in kept], ["Sales Order", None])
		frappe.set_user(ONE)
		self.assertEqual(len(ta.filter_events(list(self.ROWS))), 4)

	def test_audit_trail_report_uses_the_filter(self):
		with patch.dict(audit_trail.SOURCES, {k: (lambda f: list(self.ROWS)) for k in audit_trail.SOURCES}):
			frappe.set_user(OTHER)
			rows, _truncated = audit_trail.get_events(
				{
					"from_date": "2026-11-15",
					"to_date": "2026-11-15",
					"event_type": audit_trail.EVENT_FIELD_CHANGE,
				}
			)
		self.assertEqual({r["reference_doctype"] for r in rows}, {"Sales Order", None})

	def _rows_as(self, user):
		wo = frappe._dict(
			name="WO-CR2",
			production_item="T-CR2",
			item_name="T-CR2",
			sales_order="SO-CR2",
			status="In Process",
		)
		act = frappe._dict(
			material=10.0,
			machining=5.0,
			other=0.0,
			overhead=1.5,
			total=16.5,
			pieces=1.0,
			made=1.0,
			shop_floor_good=1.0,
			run_minutes=6,
			notes=[],
		)
		frappe.set_user(user)
		with (
			patch.object(costing, "_job_orders", return_value=[wo]),
			patch.object(costing, "actual_for", return_value=act),
			patch.object(costing, "choose_sheet", return_value=(None, None)) as chosen,
		):
			out = costing.rows({})
		return out, chosen

	def test_costing_report_hides_the_cst_estimate_from_others(self):
		out, chosen = self._rows_as(OTHER)
		chosen.assert_not_called()
		self.assertIsNone(out[0]["est_total"])
		self.assertEqual(out[0]["act_total"], 16.5)
		self.assertIn(costing.ESTIMATE_HIDDEN, out[0]["notes"])
		self.assertIn(costing.ESTIMATE_HIDDEN, costing.summary_message(out))

	def test_costing_report_unchanged_for_the_listed_user(self):
		out, chosen = self._rows_as(ONE)
		chosen.assert_called_once()
		self.assertNotIn(costing.ESTIMATE_HIDDEN, out[0]["notes"])
		self.assertIn("No CST estimate", out[0]["notes"])
