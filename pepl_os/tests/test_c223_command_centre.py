"""C2-23 - Procurement Command Centre: card methods, funnel, workspaces whose links all resolve."""

import json

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_purchase import command_centre as cc
from pepl_os.tests.utils import PEPLTestCase

WORKSPACES = ("Buyers Desk", "MD Stores Overview")
CARDS = (
	"overdue_deliveries",
	"pos_due_this_week",
	"msme_payments_due",
	"open_po_value",
	"supplier_documents_expiring",
	"scrap_stock_value",
)


class TestCommandCentre(PEPLTestCase):
	def test_every_card_returns_value_and_route(self):
		for method in CARDS:
			with self.subTest(method=method):
				res = getattr(cc, method)()
				self.assertIn(res["fieldtype"], ("Int", "Currency"))
				self.assertGreaterEqual(res["value"], 0)
				self.assertTrue(res["route"])

	def test_msme_card_equals_open_msme_bills(self):
		want = frappe.db.sql(
			"""select ifnull(sum(outstanding_amount), 0) from `tabPurchase Invoice`
			where docstatus = 1 and custom_is_msme = 1 and is_return = 0 and outstanding_amount > 0"""
		)[0][0]
		self.assertEqual(cc.msme_payments_due()["value"], want)

	def test_scrap_card_excludes_csm_scrap(self):
		want = frappe.db.sql(
			"""select ifnull(sum(b.stock_value), 0) from `tabBin` b join `tabWarehouse` w on w.name = b.warehouse
			where w.warehouse_name = 'Scrap Yard'"""
		)[0][0]
		self.assertEqual(cc.scrap_stock_value()["value"], want)

	def test_funnel_rows_are_months(self):
		rows = cc.procurement_funnel({"from_date": add_days(today(), -400), "to_date": today()})
		self.assertTrue(all(len(r.month) == 7 for r in rows))

	def test_tracker_refreshed_line(self):
		info = cc.tracker_last_refreshed()
		self.assertIn("is_today", info)
		self.assertEqual(cc.ensure_command_centre_block(), cc.BLOCK)

	def test_workspace_links_resolve(self):
		for name in WORKSPACES:
			with self.subTest(workspace=name):
				self.assertTrue(frappe.db.exists("Workspace", name))
				ws = frappe.get_doc("Workspace", name)
				for link in ws.links:
					if link.type == "Link":
						self.assertTrue(
							frappe.db.exists(link.link_type, link.link_to), f"{link.link_type} {link.link_to}"
						)
				for shortcut in ws.shortcuts:
					self.assertTrue(frappe.db.exists(shortcut.type, shortcut.link_to), shortcut.link_to)
				for card in ws.number_cards:
					self.assertTrue(
						frappe.db.exists("Number Card", card.number_card_name), card.number_card_name
					)
				for block in json.loads(ws.content):
					if block["type"] == "number_card":
						self.assertTrue(frappe.db.exists("Number Card", block["data"]["number_card_name"]))
					if block["type"] == "shortcut":
						self.assertIn(block["data"]["shortcut_name"], [s.label for s in ws.shortcuts])
