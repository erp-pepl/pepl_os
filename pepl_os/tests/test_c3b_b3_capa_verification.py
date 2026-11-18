"""C3b-B3 - CAPA effectiveness verification: awaiting a future-date check before final closure."""

import frappe
from frappe.utils import add_days, formatdate, getdate, today

from pepl_os.pepl_quality import capa, capa_panel, ncr, ncr_panel
from pepl_os.pepl_quality.params import validate_quality_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import SYSTEM_PARAMETERS, PEPLTestCase, make_user, set_param

OWNER = "pepl.t.b3.owner@example.com"
QM = "pepl.t.b3.qm@example.com"
STORES = "pepl.t.b3.stores@example.com"
REMARKS = "Three lots inspected since, all accepted"


def _ncr(item, severity=ncr.CRITICAL):
	return frappe.get_doc(
		{
			"doctype": ncr.NCR,
			"source": "In-Process",
			"severity": severity,
			"item": item,
			"qty_affected": 3,
			"defect_description": f"{severity} defect",
		}
	).insert(ignore_permissions=True)


def _complete_capa(code):
	"""A CAPA (from a Critical NCR) with its five-why, root cause and a done Corrective Action."""
	item = make_item(f"PEPL-T-B3-{code}", st.BOUGHT_OUT, valuation_rate=10).name
	doc = frappe.get_doc(capa.CAPA, frappe.db.get_value(ncr.NCR, _ncr(item).name, "capa"))
	doc.why_1 = "Collet worn"
	doc.root_cause = "No collet change interval"
	doc.append(
		"actions",
		{"action_type": capa.CORRECTIVE, "description": "Collet in the PM list", "done_on": today()},
	)
	doc.save()
	return doc


def _todos(name, rule):
	return frappe.get_all(
		"ToDo",
		filters={
			"reference_type": capa.CAPA,
			"reference_name": name,
			"status": "Open",
			"description": ["like", f"%{rule}%"],
		},
		fields=["allocated_to", "date"],
	)


def _close(doc):
	doc = frappe.get_doc(capa.CAPA, doc.name)
	doc.status = capa.CLOSED
	doc.save()
	return doc


class TestCAPAVerification(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)

	def setUp(self):
		set_param("enable_operational_todos", 1)
		set_param(capa.OWNER_FIELD, make_user(OWNER, ["Quality Manager"]))
		set_param(capa.COUNT_FIELD, 2)
		set_param(capa.WINDOW_FIELD, 90)
		set_param(capa.WHYS_FIELD, 1)
		set_param(capa.TARGET_FIELD, 30)
		set_param(capa.VERIFY_FIELD, 90)
		for severity, field in ncr.SIGNOFF_FIELDS.items():
			set_param(field, ncr.SIGNOFF_DEFAULTS[severity])
		make_user(QM, ["Quality Manager"])
		make_user(STORES, ["Stock User"])

	def test_closing_waits_for_the_effectiveness_check(self):
		doc = _close(_complete_capa("WAIT"))
		due = add_days(today(), 90)
		self.assertEqual(
			(doc.status, str(getdate(doc.actions_completed_on)), str(doc.verification_due_on), doc.closed_on),
			(capa.AWAITING, today(), due, None),
		)
		self.assertFalse(_todos(doc.name, capa.OPEN_RULE))
		self.assertEqual(
			[(t.allocated_to, str(t.date)) for t in _todos(doc.name, capa.VERIFY_RULE)], [(OWNER, due)]
		)
		rows = capa_panel.get_capa_panel(doc.name)
		self.assertEqual(
			rows[1], {"text": f"Actions completed on {formatdate(today())} - target met", "colour": "green"}
		)
		self.assertIn(
			{"text": f"Effectiveness check {formatdate(due)}: 90 day(s) left", "colour": "green"}, rows
		)
		self.assertEqual(
			rows[-1],
			{"text": f"To close: Verify Effectiveness on or after {formatdate(due)}", "colour": "gray"},
		)
		ncr_name = doc.ncrs[0].ncr
		row = next(r for r in ncr_panel.get_ncr_panel(ncr_name)["rows"] if r["text"].startswith("CAPA"))
		self.assertEqual(
			row,
			{
				"text": f"CAPA {doc.name}: Awaiting Verification · effectiveness check due {formatdate(due)}",
				"colour": "orange",
			},
		)

	def test_awaiting_capa_is_locked(self):
		doc = _close(_complete_capa("LOCK"))
		doc.root_cause = "Something else"
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be changed"):
			doc.save()
		doc = frappe.get_doc(capa.CAPA, doc.name)
		doc.status = capa.IN_PROGRESS
		with self.assertRaisesRegex(frappe.ValidationError, "awaiting its effectiveness check"):
			doc.save()
		doc = frappe.get_doc(capa.CAPA, doc.name)
		doc.status = capa.CLOSED
		with self.assertRaisesRegex(frappe.ValidationError, "awaiting its effectiveness check"):
			doc.save()

	def test_effective_only_from_the_due_day_then_closed(self):
		doc = _close(_complete_capa("EFFECTIVE"))
		frappe.set_user(QM)
		with self.assertRaisesRegex(frappe.ValidationError, "due on"):
			capa.verify_capa(doc.name, capa.EFFECTIVE, REMARKS)
		frappe.set_user("Administrator")
		frappe.db.set_value(capa.CAPA, doc.name, "verification_due_on", add_days(today(), -2))
		rows = capa_panel.get_capa_panel(doc.name)
		self.assertEqual(rows[0]["colour"], "red")
		self.assertEqual(
			rows[-1],
			{
				"text": "To close: press Verify Effectiveness (Effective closes it; Not Effective reopens it)",
				"colour": "red",
			},
		)
		frappe.set_user(QM)
		with self.assertRaisesRegex(frappe.ValidationError, "at least 10 characters"):
			capa.verify_capa(doc.name, capa.EFFECTIVE, "ok")
		self.assertEqual(capa.verify_capa(doc.name, capa.EFFECTIVE, REMARKS)["status"], capa.CLOSED)
		frappe.set_user("Administrator")
		doc = frappe.get_doc(capa.CAPA, doc.name)
		self.assertEqual(
			(doc.verification_result, doc.verified_by, str(doc.verified_on), doc.closed_by),
			(capa.EFFECTIVE, QM, today(), QM),
		)
		self.assertTrue(doc.verification_remarks.endswith(f"Effective - {REMARKS} ({QM})"))
		self.assertFalse(_todos(doc.name, capa.VERIFY_RULE))
		rows = capa_panel.get_capa_panel(doc.name)
		self.assertIn(
			{"text": f"Verified effective on {formatdate(today())} by {QM}", "colour": "green"}, rows
		)

	def test_not_effective_reopens_and_a_new_check_follows(self):
		doc = _close(_complete_capa("AGAIN"))
		frappe.set_user(QM)
		self.assertEqual(
			capa.verify_capa(doc.name, capa.NOT_EFFECTIVE, "Two rejections at the lathe again")["status"],
			capa.IN_PROGRESS,
		)
		frappe.set_user("Administrator")
		doc = frappe.get_doc(capa.CAPA, doc.name)
		self.assertEqual(
			(doc.verification_count, doc.verification_due_on, doc.actions_completed_on),
			(1, None, None),
		)
		self.assertFalse(_todos(doc.name, capa.VERIFY_RULE))
		row = next(
			r for r in capa_panel.get_capa_panel(doc.name) if r["text"].startswith("Found not effective")
		)
		self.assertEqual(row["colour"], "red")
		self.assertIn("1 time(s)", row["text"])
		self.assertIn("Two rejections at the lathe again", row["text"])
		doc.append(
			"actions", {"action_type": capa.CORRECTIVE, "description": "New collet type", "done_on": today()}
		)
		doc.status = capa.CLOSED
		doc.save()
		self.assertEqual((doc.status, str(doc.verification_due_on)), (capa.AWAITING, add_days(today(), 90)))

	def test_a_new_ncr_since_completion_means_not_effective(self):
		doc = _close(_complete_capa("REPEAT"))
		frappe.db.set_value(capa.CAPA, doc.name, "verification_due_on", today())
		again = _ncr(doc.item, ncr.MAJOR)
		self.assertEqual(frappe.db.get_value(ncr.NCR, again.name, "capa"), doc.name)  # joins the CAPA
		row = next(
			r for r in capa_panel.get_capa_panel(doc.name) if r["text"].startswith("Effectiveness check")
		)
		self.assertEqual(row["colour"], "red")
		self.assertIn(again.name, row["text"])
		frappe.set_user(QM)
		with self.assertRaisesRegex(frappe.ValidationError, again.name):
			capa.verify_capa(doc.name, capa.EFFECTIVE, REMARKS)

	def test_only_quality_verifies(self):
		doc = _close(_complete_capa("ROLE"))
		frappe.set_user(STORES)
		with self.assertRaises(frappe.PermissionError):
			capa.verify_capa(doc.name, capa.NOT_EFFECTIVE, REMARKS)

	def test_ready_text_and_setting(self):
		doc = _complete_capa("READY")
		self.assertEqual(
			capa_panel.get_capa_panel(doc.name)[-1],
			{
				"text": "Ready: set the Status to Closed and save - the effectiveness check is then due in 90 day(s)",
				"colour": "green",
			},
		)
		params = frappe.get_doc(SYSTEM_PARAMETERS)
		params.set(capa.VERIFY_FIELD, 400)
		with self.assertRaisesRegex(frappe.ValidationError, "Verification After"):
			validate_quality_params(params)
		set_param(capa.VERIFY_FIELD, 0)
		self.assertEqual(_close(doc).status, capa.CLOSED)  # 0 = no check
