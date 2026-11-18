"""C3b-P2 - NCR panel: status and age, what / from, disposition and cost, sign-offs, CAPA, dispatch hold, closing."""

import frappe
from frappe.utils import add_days, today

from pepl_os.pepl_quality import capa, dispatch, ncr, ncr_panel
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_item, make_supplier
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

QM = "pepl.t.p2.qm@example.com"
PM = "pepl.t.p2.pm@example.com"
STORES = "pepl.t.p2.stores@example.com"
SUPPLIER = "PEPL T P2 Pins"


def _item(code):
	return make_item(f"PEPL-T-P2-{code}", st.BOUGHT_OUT, valuation_rate=10).name


def _ncr(item, severity=ncr.MINOR, days_ago=0, **fields):
	return frappe.get_doc(
		{
			"doctype": ncr.NCR,
			"source": "Incoming",
			"severity": severity,
			"item": item,
			"qty_affected": 5,
			"raised_on": add_days(today(), -days_ago),
			"defect_type": "Burr",
			"defect_description": "burr on the chamfer",
			**fields,
		}
	).insert(ignore_permissions=True)


def _texts(name):
	return [r["text"] for r in ncr_panel.get_ncr_panel(name)["rows"]]


def _row(name, start):
	return next(r for r in ncr_panel.get_ncr_panel(name)["rows"] if r["text"].startswith(start))


class TestNCRPanel(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		if not frappe.db.exists("Supplier", SUPPLIER):
			make_supplier(SUPPLIER).insert(ignore_permissions=True)

	def setUp(self):
		set_param("enable_operational_todos", 1)
		set_param(capa.COUNT_FIELD, 2)
		set_param(capa.WINDOW_FIELD, 90)
		set_param(capa.WHYS_FIELD, 5)
		set_param(capa.TARGET_FIELD, 30)
		set_param(dispatch.MODE_FIELD, dispatch.SOFT_BLOCK)
		for severity, field in ncr.SIGNOFF_FIELDS.items():
			set_param(field, ncr.SIGNOFF_DEFAULTS[severity])
		make_user(QM, ["Quality Manager"])
		make_user(PM, ["Manufacturing Manager"])
		make_user(STORES, ["Stock User"])

	def test_open_minor_ncr_shows_what_is_missing(self):
		item = _item("MINOR")
		doc = _ncr(item, days_ago=3, supplier=SUPPLIER)
		rows = ncr_panel.get_ncr_panel(doc.name)["rows"]
		self.assertEqual(
			rows[0],
			{
				"text": f"Minor NCR, Open · Incoming · raised {frappe.utils.formatdate(add_days(today(), -3))} (3 day(s) ago)",
				"colour": "orange",
			},
		)
		self.assertEqual(rows[1]["text"], f"What: 5 Nos of {item} · Burr: burr on the chamfer")
		self.assertEqual(rows[2]["text"], f"From: supplier {SUPPLIER}")
		self.assertEqual(rows[3], {"text": "Disposition: not chosen yet", "colour": "orange"})
		self.assertIn({"text": "Still to sign: Quality Manager", "colour": "orange"}, rows)
		self.assertIn({"text": "CAPA: not needed for a Minor NCR", "colour": "gray"}, rows)
		self.assertIn(
			{
				"text": f"Dispatch: {item} needs a reason at dispatch until this NCR is closed (gate: Soft Block)",
				"colour": "orange",
			},
			rows,
		)
		self.assertEqual(
			rows[-1],
			{"text": "To close: choose the disposition · still to sign: Quality Manager", "colour": "orange"},
		)

	def test_cost_hint_and_cost(self):
		item = _item("COST")
		doc = _ncr(item, disposition="Scrap")
		row = _row(doc.name, "Disposition")
		self.assertEqual(row["colour"], "orange")
		self.assertIn("Disposition: Scrap · cost not entered yet (about ", row["text"])
		self.assertIn("50", row["text"])  # 5 x valuation 10
		doc.estimated_cost = 75
		doc.save()
		row = _row(doc.name, "Disposition")
		self.assertEqual(row["colour"], "gray")
		self.assertIn("Disposition: Scrap · cost ", row["text"])
		self.assertIn("75", row["text"])
		doc.disposition = "Use As Is"
		doc.estimated_cost = 0
		doc.save()
		self.assertEqual(_row(doc.name, "Disposition")["text"], "Disposition: Use As Is · no cost")

	def test_signed_ready_then_closed(self):
		doc = _ncr(_item("CLOSE"), disposition="Rework")
		frappe.set_user(STORES)
		self.assertFalse(ncr_panel.get_ncr_panel(doc.name)["can_sign"])
		frappe.set_user(QM)
		self.assertTrue(ncr_panel.get_ncr_panel(doc.name)["can_sign"])
		ncr.sign_off(doc.name)
		state = ncr_panel.get_ncr_panel(doc.name)
		self.assertFalse(state["can_sign"])
		texts = [r["text"] for r in state["rows"]]
		self.assertTrue(texts[0].startswith("Minor NCR, Under Review"))
		self.assertIn(f"Signed: Quality Manager by {QM} on {frappe.utils.formatdate(today())}", texts)
		self.assertEqual(
			state["rows"][-1],
			{"text": "Ready to close: set the Status to Closed and save", "colour": "green"},
		)
		doc = frappe.get_doc(ncr.NCR, doc.name)
		doc.status = ncr.CLOSED
		doc.save()
		rows = ncr_panel.get_ncr_panel(doc.name)["rows"]
		self.assertEqual(rows[0]["colour"], "green")
		self.assertEqual(rows[-1]["text"], f"Closed on {frappe.utils.formatdate(today())} by {QM}")
		self.assertFalse([r for r in rows if r["text"].startswith("Dispatch")])

	def test_critical_capa_and_overdue(self):
		doc = _ncr(_item("CRIT"), ncr.CRITICAL)
		name = frappe.db.get_value(ncr.NCR, doc.name, "capa")
		self.assertTrue(name)
		rows = ncr_panel.get_ncr_panel(doc.name)["rows"]
		self.assertEqual(rows[0]["colour"], "red")
		row = next(r for r in rows if r["text"].startswith("CAPA"))
		target = frappe.utils.formatdate(add_days(today(), 30))
		self.assertEqual(
			row,
			{
				"text": f"CAPA {name}: Open · target {target} · five-why: 0 of 5 whys answered; no root cause;"
				" no Corrective Action",
				"colour": "orange",
			},
		)
		frappe.db.set_value(capa.CAPA, name, "target_date", add_days(today(), -4))
		row = _row(doc.name, "CAPA")
		self.assertEqual(row["colour"], "red")
		self.assertIn("- OVERDUE by 4 day(s)", row["text"])

	def test_major_without_capa_counts_towards_one(self):
		item = _item("MAJOR")
		doc = _ncr(item, ncr.MAJOR)
		self.assertEqual(
			_row(doc.name, "CAPA"),
			{
				"text": f"CAPA: none yet · 1 of 2 Major / Critical NCRs on {item} within 90 days raise one",
				"colour": "gray",
			},
		)

	def test_cancelled_and_hard_block(self):
		set_param(dispatch.MODE_FIELD, dispatch.HARD_BLOCK)
		doc = _ncr(_item("CANCEL"))
		self.assertIn(
			f"Dispatch: {doc.item} cannot be dispatched until this NCR is closed (gate: Hard Block)",
			_texts(doc.name),
		)
		doc.status = ncr.CANCELLED
		doc.cancel_reason = "Raised against the wrong item"
		doc.save()
		rows = ncr_panel.get_ncr_panel(doc.name)["rows"]
		self.assertEqual(rows[0]["colour"], "gray")
		self.assertEqual(rows[-1], {"text": "Cancelled: Raised against the wrong item", "colour": "gray"})
		texts = [r["text"] for r in rows]
		self.assertFalse(
			[t for t in texts if t.startswith(("Dispatch", "CAPA", "Disposition", "Still to sign"))]
		)
