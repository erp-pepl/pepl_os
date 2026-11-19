"""C3b-CC - Quality Command Centre: the six cards and a workspace that renders."""

import json

import frappe
from frappe.utils import add_days, flt, today

from pepl_os.pepl_production import command_centre as production
from pepl_os.pepl_quality import calibration as cal
from pepl_os.pepl_quality import capa, coq, ncr
from pepl_os.pepl_quality import command_centre as cc
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import PEPLTestCase, set_param

WORKSPACE = "Quality Command Centre"
CARDS = (
	"capas_overdue_for_verification",
	"instruments_due_within_30_days",
	"first_pass_yield",
	"customer_rejections",
	"cost_of_quality_month",
)


def _item(code):
	return make_item(f"PEPL-T-QCC-{code}", st.BOUGHT_OUT, valuation_rate=10).name


def _ncr(item, severity="Minor", **fields):
	return frappe.get_doc(
		{
			"doctype": ncr.NCR,
			"source": "In-Process",
			"severity": severity,
			"item": item,
			"qty_affected": 1,
			"defect_description": "Burr",
			**fields,
		}
	).insert(ignore_permissions=True)


def _value(method):
	return getattr(cc, method)()["value"]


class TestQualityCommandCentre(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)

	def setUp(self):
		set_param(capa.VERIFY_FIELD, 90)
		set_param(capa.WHYS_FIELD, 1)
		for severity, field in ncr.SIGNOFF_FIELDS.items():
			set_param(field, ncr.SIGNOFF_DEFAULTS[severity])

	def test_every_card_returns_value_and_route(self):
		for method in CARDS:
			with self.subTest(method=method):
				res = getattr(cc, method)()
				self.assertIn(res["fieldtype"], ("Percent", "Int", "Currency"))
				self.assertGreaterEqual(res["value"], 0)
				self.assertTrue(res["route"])
				cards = frappe.get_all(
					"Number Card", filters={"method": f"{cc.__name__}.{method}"}, pluck="name"
				)
				self.assertEqual(len(cards), 1, method)

	def test_capas_overdue_for_verification(self):
		before = _value("capas_overdue_for_verification")
		doc = frappe.get_doc(
			capa.CAPA, frappe.db.get_value(ncr.NCR, _ncr(_item("VER"), "Critical").name, "capa")
		)
		doc.why_1 = "Collet worn"
		doc.root_cause = "No collet change interval"
		doc.append("actions", {"action_type": capa.CORRECTIVE, "description": "PM list", "done_on": today()})
		doc.status = capa.CLOSED
		doc.save()
		self.assertEqual(doc.status, capa.AWAITING)
		self.assertEqual(_value("capas_overdue_for_verification"), before)  # due in 90 days
		frappe.db.set_value(capa.CAPA, doc.name, "verification_due_on", add_days(today(), -1))
		self.assertEqual(_value("capas_overdue_for_verification"), before + 1)

	def test_instruments_due_within_30_days(self):
		before = _value("instruments_due_within_30_days")
		for code, days_ago in (("PEPL-T-QCC-SOON", 340), ("PEPL-T-QCC-LATER", 10)):
			if frappe.db.exists(cal.INSTRUMENT, code):
				frappe.delete_doc(cal.INSTRUMENT, code, force=True)
			frappe.get_doc(
				{
					"doctype": cal.INSTRUMENT,
					"instrument_id": code,
					"instrument_name": code,
					"calibration_frequency_days": 365,
				}
			).insert(ignore_permissions=True)
			rec = frappe.get_doc(
				{
					"doctype": cal.RECORD,
					"instrument": code,
					"calibration_date": add_days(today(), -days_ago),
					"result": cal.PASS,
					"certificate_no": f"CERT-{code}",
				}
			).insert(ignore_permissions=True)
			rec.submit()
		self.assertEqual(
			_value("instruments_due_within_30_days"), before + 1
		)  # due in 25 days; the other in 355

	def test_first_pass_yield_of_the_last_seven_days(self):
		first, last = production.window()
		row = frappe.db.sql(
			"""select coalesce(sum(total_good_qty), 0), coalesce(sum(total_rejected_qty), 0)
			from `tabPEPL Shift Production Entry` where docstatus = 1 and posting_date between %s and %s""",
			(first, last),
		)[0]
		good, rejected = flt(row[0]), flt(row[1])
		want = round(100.0 * good / (good + rejected), 1) if good + rejected else 0
		self.assertEqual(_value("first_pass_yield"), want)
		self.assertEqual(cc.first_pass_yield()["route_options"]["docstatus"], 1)

	def test_customer_rejections_and_cost_of_quality(self):
		before = _value("customer_rejections")
		item = _item("CUST")
		_ncr(item, source=ncr.CUSTOMER, estimated_cost=120)
		_ncr(item, source=ncr.CUSTOMER, status=ncr.CANCELLED, cancel_reason="Raised by mistake")
		_ncr(item, source=ncr.CUSTOMER, raised_on=add_days(today(), -45))
		self.assertEqual(_value("customer_rejections"), before + 1)
		res = cc.cost_of_quality_month()
		self.assertEqual(res["value"], coq.month_total())
		self.assertEqual(res["route"], ["query-report", "PEPL Cost of Quality"])

	def test_open_ncrs_by_severity(self):
		before = {r["severity"]: r["count"] for r in cc.open_ncrs_by_severity()["severities"]}
		self.assertEqual(list(before), ["Critical", "Major", "Minor"])
		item = _item("SEV")
		_ncr(item, "Major")
		closed = _ncr(item, "Minor", status=ncr.CANCELLED, cancel_reason="Raised by mistake")
		self.assertTrue(closed)
		data = cc.open_ncrs_by_severity()
		after = {r["severity"]: r["count"] for r in data["severities"]}
		self.assertEqual(after["Major"], before["Major"] + 1)
		self.assertEqual(after["Minor"], before["Minor"])
		self.assertEqual(data["total"], sum(after.values()))

	def test_block_is_installed(self):
		self.assertEqual(cc.ensure_open_ncr_block(), cc.BLOCK)
		self.assertIn("open_ncrs_by_severity", frappe.db.get_value("Custom HTML Block", cc.BLOCK, "script"))

	def test_workspace_renders(self):
		self.assertTrue(frappe.db.exists("Workspace", WORKSPACE))
		ws = frappe.get_doc("Workspace", WORKSPACE)
		self.assertEqual(len(ws.number_cards), 5)
		for link in ws.links:
			if link.type == "Link":
				self.assertTrue(
					frappe.db.exists(link.link_type, link.link_to), f"{link.link_type} {link.link_to}"
				)
		for shortcut in ws.shortcuts:
			self.assertTrue(frappe.db.exists(shortcut.type, shortcut.link_to), shortcut.link_to)
		for card in ws.number_cards:
			self.assertTrue(frappe.db.exists("Number Card", card.number_card_name), card.number_card_name)
		# The render rule (v0.22.7, C2-23): a block is drawn only when its name equals the LABEL of a row.
		tables = {
			"number_card": ("number_card_name", ws.number_cards),
			"custom_block": ("custom_block_name", ws.custom_blocks),
			"shortcut": ("shortcut_name", ws.shortcuts),
			"card": ("card_name", [x for x in ws.links if x.type == "Card Break"]),
		}
		blocks = json.loads(ws.content)
		for block in blocks:
			if block["type"] in tables:
				key, rows = tables[block["type"]]
				self.assertIn(block["data"][key], [r.label for r in rows], block["type"])
		self.assertEqual(
			sum(1 for b in blocks if b["type"] in ("number_card", "custom_block")), 6
		)  # six cards
