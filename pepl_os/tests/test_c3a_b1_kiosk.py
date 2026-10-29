"""C3a-B1 - Shift-entry kiosk (code + PIN, the operator's own entry, photos, submit with a reason) and foreman view."""

import base64
import os

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_production import kiosk, skill, spr
from pepl_os.pepl_production.params import validate_production_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.setup import roles
from pepl_os.tests.factories import (
	TEST_COMPANY,
	make_downtime_category,
	make_job_card,
	make_operator,
	make_shift,
	make_spr,
	make_workstation,
)
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

DAY = "T-B1 Day"  # 08:00-16:30, 30 min break
NIGHT = "T-B1 Night"  # 22:00-06:00
MILL = "T-B1 MILL-01"  # no machine group: skill not checked
LATHE = "T-B1 LATHE-01"  # in a machine group the operator has no skill on
IDLE = "T-B1 DRILL-01"  # ran last week, nothing today
OP = "T-B1-OP1"
PIN = "4321"
NO_LOAD = "T-B1 No Load"
TODAY = today()
# a valid 2 x 2 px PNG (Frappe opens images to strip EXIF data)
PHOTO = (
	"data:image/png;base64,"
	+ base64.b64encode(
		bytes.fromhex(
			"89504e470d0a1a0a0000000d4948445200000002000000020802000000fdd49a730000001649444154789c633c2127c7c0c0c0"
			"c4c0c0c0c0c000000d0401087d71ca660000000049454e44ae426082"
		)
	).decode()
)


class TestKiosk(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_shift(DAY, "08:00:00", "16:30:00", 30)
		make_shift(NIGHT, "22:00:00", "06:00:00", 30)
		make_workstation(MILL)
		make_workstation(LATHE, "T-B1 LATHE GROUP")
		make_workstation(IDLE)
		make_operator(OP, name="Ramesh", pin=PIN)
		make_downtime_category(NO_LOAD, "Planned", 0)

	def setUp(self):
		set_param("custom_spr_shift_grace_minutes", 30)
		set_param("custom_spr_max_unaccounted_minutes", 15)
		set_param("custom_spr_tool_photo_required", 1)
		set_param("skill_check_mode", "Advisory")
		set_param(kiosk.TRIES_FIELD, 3)
		set_param(kiosk.LOCK_FIELD, 15)
		set_param(kiosk.SESSION_FIELD, 30)
		for key in (kiosk._lock_key(OP), kiosk._tries_key(OP)):
			frappe.cache.delete_value(key)
		self.card = make_job_card(MILL, "T-B1-JC", qty=40, minutes_per_piece=6).name

	def _sign_in(self, machine=MILL, pin=PIN, day=TODAY):
		return kiosk.sign_in(machine, DAY, day, OP, pin)

	def _full_shift(self, token, good=38):
		return kiosk.save_entry(
			token,
			production=[
				{
					"job_card": self.card,
					"from_time": "08:00",
					"to_time": "12:00",
					"good_qty": good,
					"rejected_qty": 2,
					"rejection_reason": "Undersize",
				}
			],
			downtime=[{"downtime_category": NO_LOAD, "from_time": "12:00", "to_time": "16:30"}],
		)

	# ---- the page and the shift ----
	def test_current_shift(self):
		self.assertEqual(kiosk.current_shift(f"{TODAY} 10:00:00"), (DAY, TODAY))
		self.assertEqual(
			kiosk.current_shift(f"{TODAY} 02:00:00"), (NIGHT, add_days(TODAY, -1))
		)  # after midnight

	def test_kiosk_context(self):
		ctx = kiosk.kiosk_context(MILL)
		self.assertEqual(ctx["machine"], MILL)
		self.assertIn(DAY, [s["name"] for s in ctx["shifts"]])
		self.assertIn(NO_LOAD, [c.name for c in ctx["categories"]])
		self.assertEqual(ctx["dates"], [TODAY, add_days(TODAY, -1)])

	def test_only_kiosk_and_production_roles(self):
		frappe.set_user(make_user("t-b1-plain@example.com", ["Sales User"]))
		with self.assertRaises(frappe.PermissionError):
			kiosk.kiosk_context(MILL)
		with self.assertRaises(frappe.PermissionError):
			kiosk.foreman_board()

	# ---- sign-in ----
	def test_wrong_pin_then_lock(self):
		for _i in range(2):
			with self.assertRaisesRegex(frappe.ValidationError, "not recognised"):
				self._sign_in(pin="0000")
		with self.assertRaisesRegex(frappe.ValidationError, "not recognised"):
			self._sign_in(pin="0000")  # third wrong PIN locks the code
		with self.assertRaisesRegex(frappe.ValidationError, "Too many wrong PINs"):
			self._sign_in()  # even the right PIN waits

	def test_unknown_code_says_the_same(self):
		with self.assertRaisesRegex(frappe.ValidationError, "not recognised"):
			kiosk.sign_in(MILL, DAY, TODAY, "NO-SUCH-CODE", PIN)

	def test_only_today_or_yesterday(self):
		with self.assertRaisesRegex(frappe.ValidationError, "today's or yesterday's"):
			self._sign_in(day=add_days(TODAY, -3))

	def test_sign_in_gives_a_session_and_the_job_cards(self):
		out = self._sign_in()
		self.assertTrue(out["token"])
		self.assertEqual((out["operator"], out["operator_name"], out["entry"]), (OP, "Ramesh", None))
		self.assertIn(self.card, [c.name for c in out["job_cards"]])

	def test_ended_session(self):
		with self.assertRaises(frappe.AuthenticationError):
			kiosk.save_entry("no-such-token", production=[])
		out = self._sign_in()
		kiosk.sign_out(out["token"])
		with self.assertRaises(frappe.AuthenticationError):
			kiosk.save_entry(out["token"], production=[])

	# ---- the entry ----
	def test_save_creates_then_updates_the_operators_draft(self):
		token = self._sign_in()["token"]
		first = kiosk.save_entry(
			token,
			production=[{"job_card": self.card, "from_time": "08:00", "to_time": "10:00", "good_qty": 20}],
		)
		self.assertTrue(first["entry"])
		self.assertTrue(any("gap" in r["text"] for r in first["aids"]))
		again = self._full_shift(token)
		self.assertEqual(again["entry"], first["entry"])
		doc = frappe.get_doc(spr.DOCTYPE, first["entry"])
		self.assertEqual(
			(doc.operator, doc.workstation, doc.shift, str(doc.posting_date)), (OP, MILL, DAY, TODAY)
		)
		self.assertEqual((len(doc.production), len(doc.downtime), doc.total_good_qty), (1, 1, 38))
		self.assertEqual(again["production"][0]["from_time"], "08:00")

	def test_the_entry_takes_the_company_of_its_job_card(self):
		# Regression (CI #43): a kiosk login has no default company; the entry was refused for a missing company.
		token = self._sign_in()["token"]
		name = self._full_shift(token)["entry"]
		self.assertEqual(
			frappe.db.get_value(spr.DOCTYPE, name, "company"),
			frappe.db.get_value("Job Card", self.card, "company"),
		)

	def test_signing_in_again_brings_back_the_draft(self):
		token = self._sign_in()["token"]
		name = self._full_shift(token)["entry"]
		self.assertEqual(self._sign_in()["entry"], name)

	def test_tool_change_photo_is_attached(self):
		token = self._sign_in()["token"]
		out = kiosk.save_entry(
			token,
			production=[{"job_card": self.card, "from_time": "08:00", "to_time": "10:00", "good_qty": 20}],
			tool_changes=[
				{
					"change_time": "09:00",
					"tool_description": "Insert CNMG",
					"reason": "Worn out",
					"photo": PHOTO,
				}
			],
		)
		photo = out["tool_changes"][0]["photo"]
		self.assertTrue(photo.startswith("/private/files/"))
		self.assertTrue(
			frappe.db.exists(
				"File",
				{"file_url": photo, "attached_to_doctype": spr.DOCTYPE, "attached_to_name": out["entry"]},
			)
		)

	def test_submit_and_then_read_only(self):
		token = self._sign_in()["token"]
		self._full_shift(token)
		out = kiosk.submit_entry(token)
		self.assertEqual(out["docstatus"], 1)
		with self.assertRaisesRegex(frappe.ValidationError, "already submitted"):
			self._full_shift(token)

	def test_soft_block_needs_a_reason_at_the_kiosk(self):
		set_param("skill_check_mode", "Soft Block")
		set_param(skill.ENFORCE_FIELD, 1)
		card = make_job_card(LATHE, "T-B1-JL", qty=40, minutes_per_piece=6).name
		token = self._sign_in(machine=LATHE)["token"]
		kiosk.save_entry(
			token,
			production=[{"job_card": card, "from_time": "08:00", "to_time": "12:00", "good_qty": 40}],
			downtime=[{"downtime_category": NO_LOAD, "from_time": "12:00", "to_time": "16:30"}],
		)
		out = kiosk.submit_entry(token)
		self.assertIn("not qualified", out["needs_reason"])
		self.assertEqual(out["docstatus"], 0)
		with self.assertRaisesRegex(frappe.ValidationError, "at least"):
			kiosk.submit_entry(token, reason="ok")
		out = kiosk.submit_entry(token, reason="Foreman watching the first pieces")
		self.assertEqual(out["docstatus"], 1)
		log = frappe.get_all(
			"PEPL Override Log",
			filters={"rule_code": skill.RULE_CODE, "reference_name": out["entry"]},
			pluck="reason",
		)
		self.assertTrue(log and OP in log[0])

	# ---- foreman view ----
	def test_foreman_board(self):
		old = make_spr(
			IDLE,
			DAY,
			OP,
			add_days(TODAY, -3),
			downtime=[{"downtime_category": NO_LOAD, "from_time": "08:00", "to_time": "16:30"}],
		).insert(ignore_permissions=True)
		old.submit()
		token = self._sign_in()["token"]
		self._full_shift(token)
		board = kiosk.foreman_board(TODAY, DAY)
		rows = {r["machine"]: r for r in board["rows"]}
		self.assertEqual(
			(rows[MILL]["state"], rows[MILL]["operators"], rows[MILL]["good"]), ("Draft", "Ramesh", "38")
		)
		self.assertEqual(rows[IDLE]["state"], "Missing")
		self.assertGreaterEqual(board["missing"], 1)

	# ---- set-up ----
	def test_settings_validated(self):
		for values in ({kiosk.TRIES_FIELD: 1}, {kiosk.LOCK_FIELD: 0}, {kiosk.SESSION_FIELD: 500}):
			with self.assertRaises(frappe.ValidationError, msg=str(values)):
				validate_production_params(frappe._dict(values))

	def test_kiosk_role_has_no_desk(self):
		self.assertEqual(frappe.db.get_value("Role", "PEPL Kiosk", "desk_access"), 0)
		self.assertIn("PEPL Kiosk", roles.ROLE_PROFILES)
		self.assertTrue(frappe.db.exists("Role Profile", "PEPL Kiosk"))

	def test_pages_exist(self):
		for page in ("kiosk.html", "kiosk.js", "foreman.html", "foreman.js"):
			self.assertTrue(os.path.exists(frappe.get_app_path("pepl_os", "www", page)), page)
