"""C3b-Q4 - CAPA: raised by a Critical NCR or repeated Major NCRs, five-why, actions, closing rules."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_quality import capa, ncr
from pepl_os.pepl_quality.params import validate_quality_params
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import SYSTEM_PARAMETERS, PEPLTestCase, make_user, set_param

OWNER = "pepl.t.capa.owner@example.com"
QM = "pepl.t.capa.qm@example.com"
STORES = "pepl.t.capa.stores@example.com"


def _item(code):
	return make_item(f"PEPL-T-CAPA-{code}", st.BOUGHT_OUT, valuation_rate=10).name


def _ncr(item, severity, days_ago=0, **fields):
	return frappe.get_doc(
		{
			"doctype": ncr.NCR,
			"source": "In-Process",
			"severity": severity,
			"item": item,
			"qty_affected": 3,
			"raised_on": add_days(today(), -days_ago),
			"defect_description": f"{severity} defect",
			**fields,
		}
	).insert(ignore_permissions=True)


def _capa_of(ncr_name):
	return frappe.db.get_value(ncr.NCR, ncr_name, "capa")


def _complete(doc, whys=5):
	for n in range(1, whys + 1):
		doc.set(f"why_{n}", f"because {n}")
	doc.root_cause = "Worn collet on the lathe"
	doc.append(
		"actions",
		{"action_type": capa.CORRECTIVE, "description": "Replace collet; add to PM list", "done_on": today()},
	)
	return doc


class TestCAPA(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)

	def setUp(self):
		set_param("enable_operational_todos", 1)
		set_param(capa.OWNER_FIELD, make_user(OWNER, ["Quality Manager"]))
		set_param(capa.COUNT_FIELD, 2)
		set_param(capa.WINDOW_FIELD, 90)
		set_param(capa.WHYS_FIELD, 5)
		set_param(capa.TARGET_FIELD, 30)
		for severity, field in ncr.SIGNOFF_FIELDS.items():
			set_param(field, ncr.SIGNOFF_DEFAULTS[severity])
		make_user(QM, ["Quality Manager"])
		make_user(STORES, ["Stock User"])

	# ---- triggers ----
	def test_critical_ncr_raises_capa(self):
		item = _item("CRIT")
		n = _ncr(item, "Critical")
		name = _capa_of(n.name)
		self.assertTrue(name)
		doc = frappe.get_doc(capa.CAPA, name)
		self.assertEqual(
			(doc.trigger, doc.status, doc.item, doc.raised_by_system),
			(capa.CRITICAL_TRIGGER, capa.OPEN, item, 1),
		)
		self.assertEqual([r.ncr for r in doc.ncrs], [n.name])
		self.assertEqual((doc.capa_owner, str(doc.target_date)), (OWNER, add_days(today(), 30)))
		todo = frappe.get_all(
			"ToDo",
			filters={"reference_type": capa.CAPA, "reference_name": name, "status": "Open"},
			fields=["allocated_to", "priority"],
		)
		self.assertEqual([(t.allocated_to, t.priority) for t in todo], [(OWNER, "High")])

	def test_second_major_within_window_raises_one_capa_for_both(self):
		item = _item("REPEAT")
		first = _ncr(item, "Major", days_ago=30)
		self.assertFalse(_capa_of(first.name))  # one Major alone: no CAPA
		second = _ncr(item, "Major")
		name = _capa_of(second.name)
		self.assertTrue(name)
		self.assertEqual(_capa_of(first.name), name)
		doc = frappe.get_doc(capa.CAPA, name)
		self.assertEqual(doc.trigger, capa.REPEAT_TRIGGER)
		self.assertEqual(sorted(r.ncr for r in doc.ncrs), sorted([first.name, second.name]))
		third = _ncr(item, "Minor")
		self.assertFalse(_capa_of(third.name))  # Minor never
		fourth = _ncr(item, "Major")
		self.assertEqual(_capa_of(fourth.name), name)  # joins the open CAPA
		self.assertEqual(len(frappe.get_doc(capa.CAPA, name).ncrs), 3)

	def test_old_or_cancelled_majors_do_not_count(self):
		item = _item("OLD")
		_ncr(item, "Major", days_ago=120)  # outside 90 days
		cancelled = _ncr(item, "Major", days_ago=5)
		cancelled.status = ncr.CANCELLED
		cancelled.cancel_reason = "Raised twice by mistake"
		cancelled.save()
		latest = _ncr(item, "Major")
		self.assertFalse(_capa_of(latest.name))
		set_param(capa.WINDOW_FIELD, 365)
		self.assertTrue(
			capa.check_ncr(frappe.get_doc(ncr.NCR, latest.name))
		)  # wider window: the old one counts

	def test_count_three_needs_three(self):
		set_param(capa.COUNT_FIELD, 3)
		item = _item("THREE")
		a = _ncr(item, "Major", days_ago=2)
		b = _ncr(item, "Major", days_ago=1)
		self.assertFalse(_capa_of(a.name) or _capa_of(b.name))
		c = _ncr(item, "Major")
		self.assertTrue(_capa_of(c.name))

	# ---- five-why, actions, closing ----
	def test_closing_rules(self):
		item = _item("CLOSE")
		doc = frappe.get_doc(capa.CAPA, _capa_of(_ncr(item, "Critical").name))
		doc.status = capa.CLOSED
		with self.assertRaisesRegex(
			frappe.ValidationError, "0 of 5 whys answered; no root cause; no Corrective Action"
		):
			doc.save()
		doc.reload()
		_complete(doc, whys=3)
		doc.append("actions", {"action_type": capa.PREVENTIVE, "description": "Train setters"})
		doc.save()
		self.assertEqual(doc.status, capa.IN_PROGRESS)  # work started
		self.assertEqual(doc.five_why_status, "3 of 5 whys, root cause given")
		set_param(capa.WHYS_FIELD, 3)
		doc.status = capa.CLOSED
		with self.assertRaisesRegex(frappe.ValidationError, "1 action\\(s\\) not done"):
			doc.save()
		doc.reload()
		doc.actions[1].done_on = today()
		doc.status = capa.CLOSED
		doc.save()
		self.assertEqual((doc.status, bool(doc.closed_on)), (capa.CLOSED, True))
		self.assertFalse(
			frappe.get_all("ToDo", filters={"reference_name": doc.name, "status": "Open"})
		)  # owner's ToDo closed
		state = capa.get_capa_state(doc.name)
		self.assertEqual((state["five_why_complete"], state["closing_gaps"]), (True, []))

	def test_closed_capa_locked_reopen_by_quality(self):
		item = _item("LOCK")
		set_param(capa.WHYS_FIELD, 1)
		doc = frappe.get_doc(capa.CAPA, _capa_of(_ncr(item, "Critical").name))
		_complete(doc, whys=1)
		doc.status = capa.CLOSED
		doc.save()
		doc.reload()
		doc.root_cause = "Something else"
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be changed"):
			doc.save()
		frappe.set_user(STORES)
		doc = frappe.get_doc(capa.CAPA, doc.name)
		doc.status = capa.IN_PROGRESS
		with self.assertRaisesRegex(frappe.ValidationError, "Only a Quality Manager"):
			doc.save(ignore_permissions=True)
		frappe.set_user(QM)
		doc = frappe.get_doc(capa.CAPA, doc.name)
		doc.status = capa.IN_PROGRESS
		doc.save()
		self.assertIsNone(doc.closed_on)

	def test_done_on_not_in_future_and_cancel_needs_reason(self):
		item = _item("RULES")
		doc = frappe.get_doc(capa.CAPA, _capa_of(_ncr(item, "Critical").name))
		doc.append(
			"actions",
			{"action_type": capa.CORRECTION, "description": "Sort stock", "done_on": add_days(today(), 2)},
		)
		with self.assertRaisesRegex(frappe.ValidationError, "future"):
			doc.save()
		doc.reload()
		doc.status = capa.CANCELLED
		with self.assertRaisesRegex(frappe.ValidationError, "reason"):
			doc.save()
		doc.reload()
		doc.status = capa.CANCELLED
		doc.cancel_reason = "NCR raised on the wrong item"
		doc.save()
		doc.reload()
		doc.status = capa.OPEN
		with self.assertRaisesRegex(frappe.ValidationError, "stays cancelled"):
			doc.save()

	def test_manual_capa(self):
		item = _item("MANUAL")
		n = _ncr(item, "Minor")
		doc = frappe.get_doc(
			{
				"doctype": capa.CAPA,
				"item": item,
				"problem_statement": "Customer complaint by phone",
				"ncrs": [{"ncr": n.name}],
			}
		).insert(ignore_permissions=True)
		self.assertEqual((doc.trigger, doc.capa_owner), (capa.MANUAL_TRIGGER, OWNER))
		self.assertEqual(_capa_of(n.name), doc.name)  # the NCR points back

	# ---- settings ----
	def test_settings_validated(self):
		doc = frappe.get_doc(SYSTEM_PARAMETERS)
		for field, bad in (
			(capa.COUNT_FIELD, 1),
			(capa.WINDOW_FIELD, 0),
			(capa.WHYS_FIELD, 6),
			(capa.TARGET_FIELD, 400),
		):
			doc.set(field, bad)
			with self.assertRaisesRegex(
				frappe.ValidationError, capa.LABELS[field].replace("(", "\\(").replace(")", "\\)")
			):
				validate_quality_params(doc)
			doc.set(field, capa.DEFAULTS[field])
		self.assertTrue(frappe.get_meta(capa.CAPA).track_changes)
		self.assertTrue(frappe.get_meta(ncr.NCR).get_field("capa"))
