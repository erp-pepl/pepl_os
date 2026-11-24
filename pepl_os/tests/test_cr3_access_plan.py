"""CR3 - PEPL's access plan (Access Planning Pack, answers of 24 Nov 2026).

Profiles (Decisions 1, 2, 3, 8, 11, Quality Executive, view only), cancel by the HOD (Decision 4), BOMs by the
Production Manager (Decision 7), export by the CEO (Decision 9), the cancellation summary, and CR2's tender rule
left exactly as it was.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property
from frappe.utils import add_days, getdate, today

from pepl_os.common.rights import YES
from pepl_os.pepl_governance import access_matrix
from pepl_os.pepl_governance import access_plan as ap
from pepl_os.pepl_governance import tender_access as ta
from pepl_os.setup import roles
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param


def right(profile, doctype, ptype):
	if not frappe.db.exists("DocType", doctype):
		return None
	return access_matrix.rights_for(profile, doctype)[ptype]


def row_of(doctype, role):
	return next(
		(r for r in ap.perm_rows(doctype) if r.role == role and not r.permlevel and not r.if_owner),
		None,
	)


class TestProfiles(PEPLTestCase):
	def test_new_profiles_exist_with_their_roles(self):
		for profile in (
			"PEPL Stores Manager",
			"PEPL Accountant",
			"PEPL Quality Executive",
			"PEPL Production & Quality Viewer",
			"PEPL Item Master",
			"PEPL Supplier Master",
			"PEPL Sales Invoicing",
		):
			self.assertIn(profile, roles.ROLE_PROFILES)
			self.assertTrue(frappe.db.exists("Role Profile", profile), profile)
			have = set(frappe.get_all("Has Role", filters={"parent": profile}, pluck="role"))
			for role in roles.ROLE_PROFILES[profile]:
				if frappe.db.exists("Role", role):
					self.assertIn(role, have, f"{profile} is missing {role}")

	def test_new_roles_exist(self):
		for role in (ap.STOCK_VIEWER, ap.QUALITY_EXECUTIVE, ap.OPS_VIEWER, ap.SALES_INVOICING):
			self.assertTrue(frappe.db.exists("Role", role), role)
			self.assertEqual(frappe.db.get_value("Role", role, "desk_access"), 1)

	def test_decision_1_items_only_through_item_master(self):
		self.assertNotIn("Item Manager", roles.ROLE_PROFILES["PEPL Purchase Manager"])
		self.assertEqual(right("PEPL Purchase Manager", "Item", "create"), "")
		self.assertEqual(right("PEPL Purchase Manager", "Item", "read"), YES)
		self.assertEqual(right("PEPL Item Master", "Item", "create"), YES)

	def test_decision_2_suppliers_by_supplier_master_and_purchase_manager(self):
		self.assertEqual(right("PEPL Supplier Master", "Supplier", "create"), YES)
		self.assertEqual(right("PEPL Purchase Manager", "Supplier", "create"), YES)
		self.assertEqual(right("PEPL Stores", "Supplier", "create"), "")

	def test_decision_3_stores_manager_corrects_stock_stores_does_not(self):
		self.assertEqual(right("PEPL Stores Manager", "Stock Reconciliation", "submit"), YES)
		self.assertEqual(right("PEPL Stores", "Stock Reconciliation", "create"), "")
		self.assertEqual(right("PEPL Stores", "Purchase Receipt", "submit"), YES)

	def test_decision_8_quality_views_stock_but_does_not_post_it(self):
		self.assertNotIn("Stock User", roles.ROLE_PROFILES["PEPL Quality Manager"])
		for profile in ("PEPL Quality Manager", "PEPL Quality Executive"):
			for doctype in (
				"Purchase Receipt",
				"Stock Entry",
				"Delivery Note",
				"Item",
				"Batch",
				"Stock Ledger Entry",
			):
				self.assertEqual(right(profile, doctype, "read"), YES, f"{profile} / {doctype}")
				self.assertEqual(right(profile, doctype, "create"), "", f"{profile} / {doctype}")
				self.assertEqual(right(profile, doctype, "write"), "", f"{profile} / {doctype}")
		self.assertEqual(right("PEPL Quality Manager", "Quality Inspection", "submit"), YES)

	def test_quality_executive_inspects_but_never_cancels(self):
		profile = "PEPL Quality Executive"
		for ptype in ("read", "create", "write", "submit"):
			self.assertEqual(right(profile, "Quality Inspection", ptype), YES, ptype)
		self.assertEqual(right(profile, "Quality Inspection", "cancel"), "")
		self.assertEqual(right(profile, "PEPL NCR", "create"), YES)
		self.assertEqual(right(profile, "PEPL CAPA", "read"), YES)
		self.assertEqual(right(profile, "PEPL CAPA", "write"), "")

	def test_viewer_sees_production_and_quality_and_changes_nothing(self):
		profile = "PEPL Production & Quality Viewer"
		for doctype in ("Work Order", "Job Card", "BOM", "Quality Inspection", "PEPL NCR", "Stock Entry"):
			self.assertEqual(right(profile, doctype, "read"), YES, doctype)
			for ptype in ("create", "write", "submit", "cancel", "delete", "export"):
				self.assertEqual(right(profile, doctype, ptype), "", f"{doctype} {ptype}")

	def test_accountant_books_but_does_not_cancel(self):
		for doctype in ("Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry"):
			self.assertEqual(right("PEPL Accountant", doctype, "submit"), YES, doctype)
			self.assertEqual(right("PEPL Accountant", doctype, "cancel"), "", doctype)
		self.assertEqual(
			right("PEPL Accountant", "Purchase Order", "read"), YES
		)  # bill matching (Work Package A)

	def test_decision_11_sales_invoicing_raises_but_does_not_cancel(self):
		profile = "PEPL Sales Invoicing"
		for ptype in ("read", "create", "submit"):
			self.assertEqual(right(profile, "Sales Invoice", ptype), YES, ptype)
		self.assertEqual(right(profile, "Sales Invoice", "cancel"), "")
		self.assertEqual(right(profile, "Payment Entry", "read"), "")
		self.assertEqual(right(profile, "Journal Entry", "read"), "")

	def test_select_only_grant_does_not_open_the_record(self):
		row = row_of("Account", ap.SALES_INVOICING)
		self.assertTrue(row and row.select)
		self.assertFalse(row.read)

	def test_tender_roles_only_in_tender_only_and_access_role_in_none(self):
		tender_roles = {"PEPL Tender Manager", "PEPL Tender Executive", "PEPL Tender Viewer"}
		for profile, profile_roles in roles.ROLE_PROFILES.items():
			self.assertNotIn(ta.ACCESS_ROLE, profile_roles, profile)
			if profile != "PEPL Tender Only":
				self.assertFalse(tender_roles & set(profile_roles), profile)

	def test_add_ons_are_listed(self):
		for profile in roles.ADD_ON_PROFILES:
			self.assertIn(profile, roles.ROLE_PROFILES)


class TestProfileCorrection(PEPLTestCase):
	def test_correction_removes_item_manager_and_stock_user_only(self):
		for profile, role in (
			("PEPL Purchase Manager", "Item Manager"),
			("PEPL Quality Manager", "Stock User"),
		):
			doc = frappe.get_doc("Role Profile", profile)
			doc.append("roles", {"role": role})
			doc.save(ignore_permissions=True)
		changed = roles.remove_roles_from_profiles(roles.PROFILE_CORRECTIONS_V0_79)
		self.assertEqual(
			changed, {"PEPL Purchase Manager": ["Item Manager"], "PEPL Quality Manager": ["Stock User"]}
		)
		have = set(frappe.get_all("Has Role", filters={"parent": "PEPL Purchase Manager"}, pluck="role"))
		self.assertIn("Purchase Master Manager", have)
		self.assertEqual(roles.remove_roles_from_profiles(roles.PROFILE_CORRECTIONS_V0_79), {})


class TestProfileLock(PEPLTestCase):
	"""0.79.1 regression: a Role Profile saved twice in one migrate (patch, then ensure_role_profiles) was refused with
	DocumentLockedError, because Frappe locks a saved profile until a worker has updated its users (bench, 24 Nov)."""

	PROFILE = "PEPL Quality Manager"

	def tearDown(self):
		frappe.get_doc("Role Profile", self.PROFILE).unlock()

	def _have(self):
		return set(frappe.get_all("Has Role", filters={"parent": self.PROFILE}, pluck="role"))

	def test_locked_profile_is_still_corrected_and_completed(self):
		frappe.get_doc("Role Profile", self.PROFILE).lock()  # as left by the queued update of a first save
		changed = roles.remove_roles_from_profiles({self.PROFILE: (ap.STOCK_VIEWER,)})
		self.assertEqual(changed, {self.PROFILE: [ap.STOCK_VIEWER]})
		frappe.get_doc("Role Profile", self.PROFILE).lock()
		roles.ensure_role_profiles()
		self.assertIn(ap.STOCK_VIEWER, self._have())
		self.assertFalse(frappe.get_doc("Role Profile", self.PROFILE).is_locked)

	def test_users_of_the_profile_follow_at_once(self):
		field = (
			frappe.get_all(
				"DocField", filters={"parent": "User", "options": "User Role Profile"}, pluck="fieldname"
			)
			or [None]
		)[0]
		if not field:
			return
		email = "pepl.test.cr3.qm.profile@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "QM",
					"send_welcome_email": 0,
					field: [{"role_profile": self.PROFILE}],
				}
			).insert(ignore_permissions=True)
		user_roles = lambda: set(frappe.get_all("Has Role", filters={"parent": email}, pluck="role"))  # noqa: E731
		self.assertIn(ap.STOCK_VIEWER, user_roles())
		roles.remove_roles_from_profiles({self.PROFILE: (ap.STOCK_VIEWER,)})
		self.assertNotIn(ap.STOCK_VIEWER, user_roles())
		roles.ensure_role_profiles()
		self.assertIn(ap.STOCK_VIEWER, user_roles())


class TestCancelByHod(PEPLTestCase):
	def test_nobody_but_the_hod_cancels(self):
		found = {d: ap.cancel_offenders(d) for d in ap.CANCEL_RULES if frappe.db.exists("DocType", d)}
		self.assertEqual({d: r for d, r in found.items() if r}, {})

	def test_examples_from_the_pack(self):
		cases = (
			("PEPL Stores", "Purchase Receipt", ""),
			("PEPL Stores Manager", "Purchase Receipt", YES),
			("PEPL Purchase Manager", "Purchase Order", YES),
			("PEPL Foreman", "Work Order", ""),
			("PEPL Production Manager", "Work Order", YES),
			("PEPL Production Manager", "Production Plan", YES),
			("PEPL Sales Executive", "Sales Order", ""),
			("PEPL Sales Manager", "Sales Order", YES),
			("PEPL Sales Manager", "Delivery Note", YES),
			("PEPL Accounts", "Sales Invoice", YES),
			("PEPL Accountant", "Sales Invoice", ""),
			("PEPL Accountant", "Purchase Invoice", ""),
			("PEPL Accountant", "Payment Entry", ""),
			("PEPL Quality Executive", "Quality Inspection", ""),
			("PEPL Quality Manager", "Quality Inspection", YES),
		)
		for profile, doctype, expected in cases:
			self.assertEqual(right(profile, doctype, "cancel"), expected, f"{profile} / {doctype}")

	def test_a_hod_row_added_by_us_has_write_and_submit(self):
		# Frappe expects Cancel together with Write and Submit on a rule.
		for doctype, role in (("Work Order", "Manufacturing Manager"), ("Delivery Note", "Sales Manager")):
			row = row_of(doctype, role)
			self.assertTrue(row, f"{doctype} / {role}")
			for ptype in ("read", "write", "submit", "cancel"):
				self.assertTrue(row.get(ptype), f"{doctype} / {role} / {ptype}")
			self.assertFalse(row.delete)

	def test_cancel_given_by_hand_is_taken_away_again(self):
		set_param("custom_cancel_only_by_hod", 1)
		update_permission_property("Purchase Order", "Purchase User", 0, "cancel", 1, validate=False)
		frappe.clear_cache(doctype="Purchase Order")
		self.assertIn("Purchase User", ap.cancel_offenders("Purchase Order"))
		self.assertEqual(ap.restrict_cancel(["Purchase Order"]), {"Purchase Order": ["Purchase User"]})
		self.assertEqual(ap.cancel_offenders("Purchase Order"), [])
		self.assertEqual(ap.restrict_cancel(["Purchase Order"]), {})

	def test_switch_off_leaves_permissions_alone(self):
		set_param("custom_cancel_only_by_hod", 0)
		update_permission_property("Purchase Order", "Purchase User", 0, "cancel", 1, validate=False)
		frappe.clear_cache(doctype="Purchase Order")
		self.assertEqual(ap.restrict_cancel(["Purchase Order"]), {})
		self.assertIn("Purchase User", ap.cancel_offenders("Purchase Order"))

	def test_user_cannot_cancel_a_receipt_stores_manager_can(self):
		keeper = make_user("pepl.test.cr3.keeper@example.com", ["Stock User"])
		hod = make_user("pepl.test.cr3.storeshod@example.com", ["Stock Manager", "Stock User"])
		self.assertTrue(frappe.has_permission("Purchase Receipt", "submit", user=keeper))
		self.assertFalse(frappe.has_permission("Purchase Receipt", "cancel", user=keeper))
		self.assertTrue(frappe.has_permission("Purchase Receipt", "cancel", user=hod))


class TestBomByProductionManager(PEPLTestCase):
	def test_foreman_reads_boms_only(self):
		self.assertEqual(ap.removal_offenders(), {})
		self.assertEqual(right("PEPL Foreman", "BOM", "read"), YES)
		for ptype in ("create", "write", "submit", "cancel"):
			self.assertEqual(right("PEPL Foreman", "BOM", ptype), "", ptype)
			self.assertEqual(right("PEPL Production Manager", "BOM", ptype), YES, ptype)

	def test_right_given_back_by_hand_is_removed_again(self):
		set_param("custom_bom_by_production_manager_only", 1)
		update_permission_property("BOM", "Manufacturing User", 0, "create", 1, validate=False)
		frappe.clear_cache(doctype="BOM")
		self.assertEqual(ap.restrict_rights(), {"BOM / Manufacturing User": ["create"]})
		self.assertEqual(ap.removal_offenders(), {})


class TestExportByCeo(PEPLTestCase):
	def test_only_the_ceo_and_system_manager_export(self):
		self.assertEqual(ap.export_offenders(), {})

	def test_ceo_exports_business_records(self):
		for doctype in ("Sales Order", "Purchase Order", "Stock Entry", "Item"):
			self.assertEqual(right("PEPL CEO", doctype, "export"), YES, doctype)

	def test_examples_from_the_pack(self):
		for profile in ("PEPL Accounts", "PEPL Purchase Manager", "PEPL Stores", "PEPL Sales Manager"):
			for doctype in ("Item", "Sales Invoice", "Purchase Order", "Stock Entry", "Sales Order"):
				self.assertEqual(right(profile, doctype, "export"), "", f"{profile} / {doctype}")

	def test_tender_users_keep_cr2_export_and_nothing_fights_on_redeploy(self):
		ta.grant_access_rights()
		for doctype in (ta.TENDER, ta.COST_SHEET):
			self.assertTrue(row_of(doctype, ta.ACCESS_ROLE).export, doctype)
		self.assertEqual(ap.restrict_export([ta.TENDER, ta.COST_SHEET]), {})
		self.assertEqual(ta.grant_access_rights(), [])

	def test_export_given_by_hand_is_removed_again(self):
		set_param("custom_restrict_export_to_ceo", 1)
		update_permission_property("Supplier", "Purchase User", 0, "export", 1, validate=False)
		frappe.clear_cache(doctype="Supplier")
		self.assertEqual(ap.restrict_export(["Supplier"]), {"Supplier": ["Purchase User"]})
		self.assertEqual(ap.export_offenders(["Supplier"]), {})

	def test_a_role_listed_in_system_parameters_keeps_export(self):
		set_param("custom_restrict_export_to_ceo", 1)
		set_param("custom_export_also_allowed_roles", "Accounts Manager")
		update_permission_property("Supplier", "Accounts Manager", 0, "export", 1, validate=False)
		frappe.clear_cache(doctype="Supplier")
		self.assertEqual(ap.restrict_export(["Supplier"]), {})
		self.assertTrue(row_of("Supplier", "Accounts Manager").export)

	def test_owner_only_rule_is_handled_on_its_own(self):
		set_param("custom_restrict_export_to_ceo", 1)
		add_permission("Supplier", "Purchase User", 0)
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": "Supplier",
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": "Purchase User",
				"permlevel": 0,
				"if_owner": 1,
				"read": 1,
				"export": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(doctype="Supplier")
		self.assertIn("Purchase User", ap.export_offenders(["Supplier"]).get("Supplier", []))
		ap.restrict_export(["Supplier"])
		self.assertEqual(ap.export_offenders(["Supplier"]), {})

	def test_export_refused_for_a_non_ceo_user(self):
		accountant = make_user("pepl.test.cr3.accounts@example.com", ["Accounts Manager", "Accounts User"])
		ceo = make_user("pepl.test.cr3.ceo@example.com", ["PEPL CEO"])
		frappe.set_user(accountant)
		self.assertFalse(frappe.permissions.can_export("Sales Invoice"))
		frappe.set_user(ceo)
		self.assertTrue(frappe.permissions.can_export("Sales Invoice"))


class TestReportsAndSetup(PEPLTestCase):
	def test_new_roles_open_their_reports_and_report_keeps_its_roles(self):
		self.assertEqual(ap._reports_missing_roles(), {})
		if frappe.db.exists("Report", "Stock Balance"):
			name = frappe.db.get_value("Custom Role", {"report": "Stock Balance"})
			have = set(
				frappe.get_all(
					"Has Role", filters={"parent": name, "parenttype": "Custom Role"}, pluck="role"
				)
			)
			self.assertIn("Stock User", have)  # the report's own roles stay
			self.assertIn(ap.STOCK_VIEWER, have)

	def test_every_check_79_example_holds(self):
		results = ap.example_results()
		self.assertGreaterEqual(len(results), 20)
		self.assertEqual([r for r in results if r["expected"] != r["got"]], [])

	def test_setup_is_safe_to_repeat(self):
		ap.apply_access_plan()
		again = ap.apply_access_plan()
		for key, value in again.items():
			self.assertFalse(value, key)

	def test_cr2_setup_still_repeats_cleanly(self):
		ta.apply_access_setup()
		self.assertEqual(ta.apply_access_setup()["rights"], [])


class TestCancellationSummary(PEPLTestCase):
	def test_window_daily_and_weekly(self):
		monday = getdate("2026-11-23")
		self.assertEqual(ap.summary_window(monday, "Daily"), (getdate("2026-11-22"), getdate("2026-11-22")))
		self.assertEqual(ap.summary_window(monday, "Weekly"), (getdate("2026-11-16"), getdate("2026-11-22")))
		self.assertIsNone(ap.summary_window(getdate("2026-11-24"), "Weekly"))
		self.assertIsNone(ap.summary_window(monday, "Off"))

	def _cancelled_bom(self):
		# A cancelled record of a DocType in the rules: a BOM (made and cancelled as Administrator).
		from pepl_os.pepl_stores import stock_tree as st
		from pepl_os.tests.factories import make_bom, make_item

		rm = make_item("PEPL-TEST-CR3-RM", st.RAW_MATERIAL, heat_tracked=False, valuation_rate=10).name
		fg = make_item("PEPL-TEST-CR3-FG", st.FINISHED_GOODS).name
		bom = make_bom(fg, rm)
		bom.cancel()
		return bom.name

	def test_cancelled_record_is_listed_with_who(self):
		name = self._cancelled_bom()
		rows = ap.cancellations(today(), today())
		row = next((r for r in rows if r["name"] == name), None)
		self.assertTrue(row)
		self.assertEqual(row["doctype"], "BOM")
		self.assertEqual(row["cancelled_by"], "Administrator")
		self.assertIn(name, ap.summary_html(rows, today(), today()))

	def test_nothing_sent_when_nothing_cancelled(self):
		result = ap.send_summary(add_days(today(), 400))
		self.assertEqual(result["sent_to"], [])
		self.assertIn(result["reason"], ("nothing cancelled", "not due today"))

	def test_recipients_from_system_parameters_first(self):
		set_param("custom_cancellation_summary_to", "md@example.com\n\nhod@example.com")
		self.assertEqual(ap.summary_recipients(), ["md@example.com", "hod@example.com"])

	def test_job_is_scheduled_and_switch_off_works(self):
		self.assertIn(
			"pepl_os.pepl_governance.access_plan.daily_cancellation_summary",
			frappe.get_hooks("scheduler_events").get("daily"),
		)
		set_param("custom_cancellation_summary", "Off")
		self.assertEqual(ap.daily_cancellation_summary()["message"], "switched off")
