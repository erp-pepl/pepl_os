"""C3b-P3 - CAPA panel: status, target, NCRs, containment, five-why, open actions, closing."""

import frappe
from frappe.utils import add_days, formatdate, today

from pepl_os.pepl_quality import capa, capa_panel, ncr
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

OWNER = "pepl.t.p3.owner@example.com"
SETTER = "pepl.t.p3.setter@example.com"


def _item(code):
	return make_item(f"PEPL-T-P3-{code}", st.BOUGHT_OUT, valuation_rate=10).name


def _capa(code):
	"""A Critical NCR and the CAPA it raises."""
	item = _item(code)
	n = frappe.get_doc(
		{
			"doctype": ncr.NCR,
			"source": "In-Process",
			"severity": ncr.CRITICAL,
			"item": item,
			"qty_affected": 3,
			"defect_description": "Critical defect",
		}
	).insert(ignore_permissions=True)
	name = frappe.db.get_value(ncr.NCR, n.name, "capa")
	return frappe.get_doc(capa.CAPA, name), n.name, item


def _rows(name):
	return capa_panel.get_capa_panel(name)


def _row(name, start):
	return next(r for r in _rows(name) if r["text"].startswith(start))


class TestCAPAPanel(PEPLTestCase):
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
		set_param(capa.VERIFY_FIELD, 0)  # closing closes at once; the effectiveness check is tested in C3b-B3
		for severity, field in ncr.SIGNOFF_FIELDS.items():
			set_param(field, ncr.SIGNOFF_DEFAULTS[severity])
		make_user(SETTER, ["Manufacturing User"])

	def test_new_capa(self):
		doc, ncr_name, item = _capa("NEW")
		rows = _rows(doc.name)
		self.assertEqual(
			rows[0],
			{
				"text": f"CAPA (Critical NCR) on {item}, Open · raised today by the system · owner {OWNER}",
				"colour": "orange",
			},
		)
		self.assertEqual(
			rows[1],
			{"text": f"Target {formatdate(add_days(today(), 30))}: 30 day(s) left", "colour": "green"},
		)
		self.assertEqual(rows[2], {"text": f"NCRs (1): {ncr_name} Critical, Open", "colour": "gray"})
		self.assertEqual(rows[3], {"text": "Containment: not recorded", "colour": "orange"})
		self.assertEqual(
			rows[4],
			{"text": "Five-why: 0 of 5 whys answered, root cause missing · next: Why 1", "colour": "orange"},
		)
		self.assertEqual(rows[5], {"text": "Actions: none yet", "colour": "orange"})
		self.assertEqual(
			rows[-1],
			{
				"text": "To close: five-why: 0 of 5 whys answered; no root cause; no Corrective Action",
				"colour": "orange",
			},
		)

	def test_whys_and_actions(self):
		doc, _n, _i = _capa("ACT")
		doc.containment = "Sorted the stock at stores"
		for n in (1, 2, 3):
			doc.set(f"why_{n}", f"because {n}")
		doc.append(
			"actions", {"action_type": capa.CORRECTION, "description": "Sort stock", "done_on": today()}
		)
		doc.append(
			"actions",
			{
				"action_type": capa.CORRECTIVE,
				"description": "Replace collet",
				"responsible": SETTER,
				"due_date": add_days(today(), -3),
			},
		)
		doc.append("actions", {"action_type": capa.PREVENTIVE, "description": "Train setters"})
		doc.save()
		rows = _rows(doc.name)
		texts = [r["text"] for r in rows]
		self.assertIn(", In Progress · ", texts[0])
		self.assertEqual(rows[3], {"text": "Containment: Sorted the stock at stores", "colour": "gray"})
		self.assertEqual(rows[4]["text"], "Five-why: 3 of 5 whys answered, root cause missing · next: Why 4")
		self.assertEqual(
			rows[5],
			{
				"text": "Actions: 3 (Correction 1, Corrective Action 1, Preventive Action 1) · 1 done · 2 open,"
				" 1 overdue",
				"colour": "red",
			},
		)
		self.assertEqual(
			rows[6],
			{
				"text": f"Corrective Action: Replace collet · {SETTER} · due"
				f" {formatdate(add_days(today(), -3))} - OVERDUE by 3 day(s)",
				"colour": "red",
			},
		)
		self.assertEqual(
			rows[7],
			{
				"text": "Preventive Action: Train setters · no one responsible · no due date",
				"colour": "orange",
			},
		)
		self.assertEqual(
			rows[-1]["text"], "To close: five-why: 3 of 5 whys answered; no root cause; 2 action(s) not done"
		)

	def test_target_soon_today_and_overdue(self):
		doc, _n, _i = _capa("TARGET")
		frappe.db.set_value(capa.CAPA, doc.name, "target_date", add_days(today(), 5))
		self.assertEqual(
			_row(doc.name, "Target"),
			{"text": f"Target {formatdate(add_days(today(), 5))}: 5 day(s) left", "colour": "orange"},
		)
		frappe.db.set_value(capa.CAPA, doc.name, "target_date", today())
		self.assertEqual(_row(doc.name, "Target")["text"], f"Target {formatdate(today())} - due today")
		frappe.db.set_value(capa.CAPA, doc.name, "target_date", add_days(today(), -4))
		rows = _rows(doc.name)
		self.assertEqual(rows[0]["colour"], "red")
		self.assertEqual(
			rows[1],
			{"text": f"Target {formatdate(add_days(today(), -4))} - OVERDUE by 4 day(s)", "colour": "red"},
		)

	def test_ready_then_closed(self):
		set_param(capa.WHYS_FIELD, 1)
		doc, _n, _i = _capa("CLOSE")
		doc.why_1 = "Collet worn"
		doc.root_cause = "No collet change interval"
		doc.append(
			"actions",
			{"action_type": capa.CORRECTIVE, "description": "Collet in the PM list", "done_on": today()},
		)
		doc.save()
		rows = _rows(doc.name)
		self.assertEqual(
			rows[4], {"text": "Five-why: complete · root cause: No collet change interval", "colour": "green"}
		)
		self.assertEqual(rows[5]["colour"], "green")
		self.assertEqual(
			rows[-1], {"text": "Ready to close: set the Status to Closed and save", "colour": "green"}
		)
		doc.reload()
		doc.status = capa.CLOSED
		doc.save()
		rows = _rows(doc.name)
		self.assertEqual(rows[0]["colour"], "green")
		self.assertEqual(
			rows[1],
			{"text": f"Closed on {formatdate(today())} by Administrator - target met", "colour": "green"},
		)
		self.assertFalse([r for r in rows if r["text"].startswith(("To close", "Ready to close"))])

	def test_cancelled(self):
		doc, _n, _i = _capa("CANCEL")
		doc.status = capa.CANCELLED
		doc.cancel_reason = "NCR raised on the wrong item"
		doc.save()
		rows = _rows(doc.name)
		self.assertEqual(rows[0]["colour"], "gray")
		self.assertFalse([r for r in rows if r["text"].startswith("Target")])
		self.assertEqual(rows[-1], {"text": "Cancelled: NCR raised on the wrong item", "colour": "gray"})

	def test_manual_capa_without_ncrs(self):
		item = _item("MANUAL")
		doc = frappe.get_doc(
			{
				"doctype": capa.CAPA,
				"trigger": capa.MANUAL_TRIGGER,
				"item": item,
				"raised_on": add_days(today(), -2),
				"problem_statement": "Customer complaint on finish",
			}
		).insert(ignore_permissions=True)
		rows = _rows(doc.name)
		self.assertEqual(
			rows[0]["text"],
			f"CAPA (Manual) on {item}, Open · raised {formatdate(add_days(today(), -2))} (2 day(s) ago) · owner {OWNER}",
		)
		self.assertEqual(rows[2], {"text": "NCRs: none listed", "colour": "gray"})
