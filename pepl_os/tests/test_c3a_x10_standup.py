"""C3a-X10 - The Daily Stand-up: yesterday's shop floor, stops, missing entries, delivery risk, job work."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, getdate, now, today

from pepl_os.pepl_governance.access_matrix import MATRIX_DOCTYPES
from pepl_os.pepl_production import standup
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_downtime_category,
	make_job_card,
	make_operator,
	make_shift,
	make_spr,
	make_work_order,
	make_workstation,
)
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

DAY = "T-SU Day"  # 08:00-16:30, 480 planned minutes
MILL = "T-SU MILL-01"  # works yesterday
LATHE = "T-SU LATHE-01"  # worked 5 days ago, nothing yesterday
OP = "T-SU-OP1"
NO_LOAD = "T-SU No Load"
SPINDLE = "T-SU Spindle"
GROUP = "T-SU Stand-up"
YESTERDAY = add_days(today(), -1)


def _down(category, start, end):
	return {"downtime_category": category, "from_time": start, "to_time": end}


class TestDailyStandup(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_workstation(MILL, "T-SU MILL")
		make_workstation(LATHE, "T-SU LATHE")
		make_operator(OP, pin="1111")
		make_downtime_category(NO_LOAD, "Planned", 0)
		make_downtime_category(SPINDLE, "Unplanned", 1)
		cls.card = make_job_card(MILL, "T-SU-JC", qty=10, minutes_per_piece=6)
		cls.fg = cls.card.production_item
		if not frappe.db.exists("Email Group", GROUP):
			frappe.get_doc({"doctype": "Email Group", "title": GROUP}).insert(ignore_permissions=True)
			for email in ("foreman@pepl.test", "hod@pepl.test"):
				frappe.get_doc(
					{"doctype": "Email Group Member", "email_group": GROUP, "email": email}
				).insert(ignore_permissions=True)

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 0)
		set_param("skill_check_mode", "Advisory")
		set_param(standup.RISK_DAYS_FIELD, 3)
		set_param(standup.GROUP_FIELD, GROUP)

	def _floor(self):
		"""Yesterday on the mill: 4 h run (8 good, 2 rejected), 1 h spindle breakdown, 3 h no load.
		The lathe worked 5 days ago and has no entry yesterday."""
		doc = make_spr(
			MILL,
			DAY,
			OP,
			YESTERDAY,
			production=[
				{
					"job_card": self.card.name,
					"from_time": "08:00",
					"to_time": "12:00",
					"good_qty": 8,
					"rejected_qty": 2,
					"rejection_reason": "Undersize",
				}
			],
			downtime=[_down(SPINDLE, "12:00", "13:00"), _down(NO_LOAD, "13:00", "16:00")],
		).insert(ignore_permissions=True)
		doc.submit()
		lathe = make_spr(LATHE, DAY, OP, add_days(today(), -5), downtime=[_down(NO_LOAD, "08:00", "16:00")])
		lathe.insert(ignore_permissions=True)
		lathe.submit()

	def test_the_shop_floor_section(self):
		self._floor()
		doc = standup.build(YESTERDAY)
		self.assertEqual(getdate(doc.standup_date), getdate(YESTERDAY))
		self.assertEqual((doc.machines_reported, doc.good_qty, doc.rejected_qty), (1, 8, 2))
		self.assertAlmostEqual(doc.rejection_percent, 20.0, places=2)
		self.assertEqual(doc.breakdowns, 1)
		self.assertIn(MILL, doc.summary)

	def test_top_stops(self):
		self._floor()
		doc = standup.build(YESTERDAY)
		self.assertEqual(doc.top_stop, NO_LOAD)  # 180 minutes, then the spindle's 60
		self.assertEqual(doc.downtime_minutes, 240)
		self.assertIn(SPINDLE, doc.summary)

	def test_machines_without_a_shift_entry(self):
		self._floor()
		doc = standup.build(YESTERDAY)
		self.assertIn(LATHE, standup.machines_without_entry(getdate(YESTERDAY)))
		self.assertNotIn(MILL, standup.machines_without_entry(getdate(YESTERDAY)))
		self.assertGreaterEqual(doc.machines_without_entry, 1)
		self.assertIn(LATHE, doc.summary)

	def test_job_orders_at_delivery_risk(self):
		soon = make_work_order(self.fg, 5, now())
		late = make_work_order(self.fg, 5, now())
		far = make_work_order(self.fg, 5, now())
		frappe.db.set_value("Work Order", soon.name, "expected_delivery_date", add_days(today(), 2))
		frappe.db.set_value("Work Order", late.name, "expected_delivery_date", add_days(today(), -1))
		frappe.db.set_value("Work Order", far.name, "expected_delivery_date", add_days(today(), 10))
		risk = {r.name: r for r in standup.job_orders_at_risk(getdate(YESTERDAY))}
		self.assertIn(soon.name, risk)
		self.assertIn(late.name, risk)
		self.assertNotIn(far.name, risk)
		self.assertTrue(risk[late.name].overdue)
		self.assertFalse(risk[soon.name].overdue)
		doc = standup.build(YESTERDAY)
		self.assertGreaterEqual(doc.job_orders_overdue, 1)
		self.assertIn(late.name, doc.summary)
		set_param(standup.RISK_DAYS_FIELD, 0)
		self.assertNotIn(soon.name, {r.name for r in standup.job_orders_at_risk(getdate(YESTERDAY))})

	def test_a_finished_or_stopped_job_order_is_not_at_risk(self):
		done = make_work_order(self.fg, 5, now())
		frappe.db.set_value("Work Order", done.name, {"expected_delivery_date": today(), "produced_qty": 5})
		stopped = make_work_order(self.fg, 5, now())
		frappe.db.set_value(
			"Work Order", stopped.name, {"expected_delivery_date": today(), "status": "Stopped"}
		)
		risk = {r.name for r in standup.job_orders_at_risk(getdate(YESTERDAY))}
		self.assertNotIn(done.name, risk)
		self.assertNotIn(stopped.name, risk)

	def test_building_again_updates_the_same_day(self):
		first = standup.build(YESTERDAY)
		self._floor()
		second = standup.build(YESTERDAY)
		self.assertEqual(first.name, second.name)
		self.assertEqual(second.machines_reported, 1)
		self.assertEqual(frappe.db.count(standup.DOCTYPE, {"standup_date": YESTERDAY}), 1)

	def test_e_mailed_to_the_standup_group(self):
		frappe.flags.mute_emails = True  # queued only (CI has no outgoing account)
		self.addCleanup(setattr, frappe.flags, "mute_emails", False)
		self._floor()
		doc = standup.build(YESTERDAY)
		sent = standup.send(doc)
		self.assertEqual(sent, ["foreman@pepl.test", "hod@pepl.test"])
		queued = frappe.get_all(
			"Email Queue",
			filters={"reference_doctype": standup.DOCTYPE, "reference_name": doc.name},
			pluck="name",
		)
		self.assertEqual(len(queued), 1)
		to = frappe.get_all("Email Queue Recipient", filters={"parent": queued[0]}, pluck="recipient")
		self.assertEqual(sorted(to), ["foreman@pepl.test", "hod@pepl.test"])
		self.assertIn("hod@pepl.test", frappe.db.get_value(standup.DOCTYPE, doc.name, "emailed_to"))

	def test_no_outgoing_account_keeps_the_record(self):
		doc = standup.build(YESTERDAY)
		with patch("frappe.sendmail", side_effect=frappe.OutgoingEmailError("no account")):
			self.assertEqual(standup.send(doc), [])
		self.assertIn("Not e-mailed", frappe.db.get_value(standup.DOCTYPE, doc.name, "emailed_to"))

	def test_no_group_no_e_mail(self):
		set_param(standup.GROUP_FIELD, "")
		doc = standup.build(YESTERDAY)
		self.assertEqual(standup.send(doc), [])
		self.assertFalse(frappe.db.get_value(standup.DOCTYPE, doc.name, "emailed_to"))

	def test_the_morning_job_builds_yesterday(self):
		name = standup.daily_standup()
		self.assertEqual(
			getdate(frappe.db.get_value(standup.DOCTYPE, name, "standup_date")), getdate(YESTERDAY)
		)

	def test_build_now_is_for_the_production_manager(self):
		frappe.set_user(make_user("pepl.test.su.foreman@example.com", ["Manufacturing User"]))
		with self.assertRaises(frappe.PermissionError):
			standup.build_standup_now()

	def test_set_up(self):
		cron = frappe.get_hooks("scheduler_events")["cron"]
		self.assertIn("pepl_os.pepl_production.standup.daily_standup", cron["45 7 * * *"])
		self.assertIn(standup.DOCTYPE, {doctype for _area, doctype, _label in MATRIX_DOCTYPES})
		self.assertTrue(frappe.get_meta(standup.DOCTYPE).in_create)
		with self.assertRaises(frappe.ValidationError):
			validate_production_params(frappe._dict({standup.RISK_DAYS_FIELD: -1}))
