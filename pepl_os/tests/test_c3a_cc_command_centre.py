"""C3a-CC - Production Command Centre: the five cards, the downtime-by-cause report, a workspace that renders."""

import json

import frappe
from frappe.utils import add_days, flt, today

from pepl_os.pepl_production import command_centre as cc
from pepl_os.pepl_production import job_work, standup
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_downtime_category,
	make_job_card,
	make_operator,
	make_shift,
	make_spr,
	make_workstation,
)
from pepl_os.tests.utils import PEPLTestCase, set_param

WORKSPACE = "Production Command Centre"
CARDS = ("yesterdays_oee", "jobs_at_delivery_risk", "job_work_outside", "rejection_percent")
DAY = "T-CC Day"
MILL = "T-CC MILL-01"
OP = "T-CC-OP1"
SETTER = "T-CC Tool Setting"  # Unplanned stop used only by this test
YESTERDAY = add_days(today(), -1)


class TestProductionCommandCentre(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(MILL, "T-CC MILL")
		make_operator(OP, pin="1111")
		make_downtime_category(SETTER, "Unplanned", 0)

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")

	def _shift_entry(self, good=38, rejected=2):
		card = make_job_card(MILL, "T-CC-JC", qty=40, minutes_per_piece=6).name
		row = {"job_card": card, "from_time": "08:00", "to_time": "12:00", "good_qty": good}
		if rejected:
			row.update({"rejected_qty": rejected, "rejection_reason": "Undersize"})
		doc = make_spr(
			MILL,
			DAY,
			OP,
			YESTERDAY,
			production=[row],
			downtime=[{"downtime_category": SETTER, "from_time": "12:00", "to_time": "16:00"}],
		).insert(ignore_permissions=True)
		doc.submit()
		return doc

	# ---- cards ----
	def test_every_card_returns_value_and_route(self):
		for method in CARDS:
			with self.subTest(method=method):
				res = getattr(cc, method)()
				self.assertIn(res["fieldtype"], ("Percent", "Int", "Float"))
				self.assertGreaterEqual(res["value"], 0)
				self.assertTrue(res["route"])
				card = frappe.get_all(
					"Number Card", filters={"method": f"{cc.__name__}.{method}"}, pluck="name"
				)
				self.assertEqual(len(card), 1, method)
				self.assertFalse(frappe.db.get_value("Number Card", card[0], "currency"), card[0])

	def test_yesterdays_oee_is_weighted_by_planned_production_time(self):
		self._shift_entry()
		rows = frappe.get_all(
			cc.OEE, filters={"oee_date": YESTERDAY}, fields=["oee", "planned_production_minutes"]
		)
		weight = sum(r.planned_production_minutes for r in rows)
		want = round(sum(flt(r.oee) * r.planned_production_minutes for r in rows) / weight, 1)
		res = cc.yesterdays_oee()
		self.assertEqual(res["value"], want)
		self.assertEqual(res["route_options"], {"oee_date": YESTERDAY})

	def test_jobs_at_delivery_risk_is_the_stand_up_list(self):
		self.assertEqual(cc.jobs_at_delivery_risk()["value"], len(standup.job_orders_at_risk(today())))

	def test_job_work_outside_is_the_reconciliation_total(self):
		want = round(sum(flt(r.balance) for r in job_work.reconcile() if flt(r.balance) > 0), 3)
		res = cc.job_work_outside()
		self.assertEqual(res["value"], want)
		self.assertEqual(res["fieldtype"], "Int" if want == int(want) else "Float")

	def test_rejection_percent_of_the_last_seven_days(self):
		self._shift_entry(good=38, rejected=2)
		first, last = cc.window()
		row = frappe.db.sql(
			"""select sum(total_good_qty), sum(total_rejected_qty) from `tabPEPL Shift Production Entry`
			where docstatus = 1 and posting_date between %s and %s""",
			(first, last),
		)[0]
		want = round(100.0 * flt(row[1]) / (flt(row[0]) + flt(row[1])), 1)
		self.assertEqual(cc.rejection_percent()["value"], want)
		self.assertGreater(want, 0)

	def test_today_is_not_in_the_seven_days(self):
		first, last = cc.window()
		self.assertEqual((str(first), str(last)), (add_days(today(), -7), YESTERDAY))

	# ---- top downtime cause ----
	def test_downtime_by_cause_and_the_top_cause(self):
		self._shift_entry()
		rows = cc.downtime_by_cause()
		mine = next(r for r in rows if r.downtime_category == SETTER)
		self.assertEqual((mine.minutes, mine.stops, mine.stop_type), (240, 1, "Unplanned"))
		self.assertAlmostEqual(sum(r.share for r in rows), 100, delta=0.5)
		top = cc.top_downtime_cause()
		self.assertEqual(top["cause"], rows[0].downtime_category)
		self.assertIn(f"{rows[0].minutes} min", top["text"])
		from pepl_os.pepl_production.report.pepl_downtime_by_cause import pepl_downtime_by_cause as report

		self.assertEqual(len(report.execute({"days": 7})[1]), len(rows))

	def test_top_cause_block_is_installed(self):
		self.assertEqual(cc.ensure_top_downtime_block(), cc.BLOCK)
		self.assertIn("top_downtime_cause", frappe.db.get_value("Custom HTML Block", cc.BLOCK, "script"))

	# ---- workspace ----
	def test_workspace_renders(self):
		self.assertTrue(frappe.db.exists("Workspace", WORKSPACE))
		self.assertNotIn(
			"'", frappe.db.get_value("Workspace", WORKSPACE, "title")
		)  # the address is made from it
		ws = frappe.get_doc("Workspace", WORKSPACE)
		self.assertEqual(len(ws.number_cards), 4)
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
			sum(1 for b in blocks if b["type"] in ("number_card", "custom_block")), 5
		)  # five cards
