"""C3b-B4 - Drawing-revision mid-production alert: a new revision on the Product Master flags the open Job Orders."""

import frappe
from frappe.utils import now_datetime

from pepl_os.pepl_quality import drawing
from pepl_os.pepl_stores import stock_tree as st
from pepl_os.tests.factories import TEST_COMPANY, make_file, make_job_card, make_work_order, make_workstation
from pepl_os.tests.utils import PEPLTestCase, make_user, set_param

MILL = "T-DRW MILL-01"
OWNER = "pepl.t.drw.owner@example.com"
STORES = "pepl.t.drw.stores@example.com"


def _todos(work_order):
	return frappe.get_all(
		"ToDo",
		filters={
			"reference_type": drawing.WO,
			"reference_name": work_order,
			"status": "Open",
			"description": ["like", f"%{drawing.RULE}%"],
		},
		fields=["allocated_to", "priority"],
	)


class TestDrawingRevision(PEPLTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		st.seed_stock_structure(TEST_COMPANY)
		make_workstation(MILL)
		cls.card = make_job_card(MILL, "T-DRW-JC", qty=10, minutes_per_piece=6)
		cls.item = cls.card.production_item

	def setUp(self):
		set_param("enable_operational_todos", 1)
		set_param(drawing.OWNER_FIELD, make_user(OWNER, ["Manufacturing Manager"]))
		make_user(STORES, ["Stock User"])
		self.product = frappe.get_doc(
			{
				"doctype": drawing.PRODUCT,
				"product_name": "T-DRW Product " + self.item,
				"product_type": "Single Component",
				"status": "Active",
				"linked_item": self.item,
				"drawing_revisions": [
					{
						"revision": "A",
						"issue_date": "2026-01-10",
						"is_current": 1,
						"drawing_file": make_file("t-drw-rev-a.pdf"),
					}
				],
			}
		).insert(ignore_permissions=True)

	def _revise(self, revision, change="Hole moved 2 mm"):
		doc = frappe.get_doc(drawing.PRODUCT, self.product.name)
		for row in doc.drawing_revisions:
			row.is_current = 0
		doc.append(
			"drawing_revisions",
			{
				"revision": revision,
				"issue_date": "2026-11-19",
				"is_current": 1,
				"change_description": change,
				"drawing_file": make_file(f"t-drw-rev-{revision.lower()}.pdf"),
			},
		)
		doc.save(ignore_permissions=True)
		return doc

	def test_job_order_records_its_revision(self):
		wo = make_work_order(self.item, 5, now_datetime())
		self.assertEqual(frappe.db.get_value(drawing.WO, wo.name, drawing.REVISION), "A")
		panel = drawing.get_drawing_panel(wo.name)
		self.assertEqual(
			panel["rows"], [{"text": "Made to drawing Rev A · current Rev A", "colour": "green"}]
		)
		self.assertFalse(panel["can_acknowledge"])

	def test_new_revision_flags_open_job_orders_and_acknowledge_clears(self):
		wo = make_work_order(self.item, 5, now_datetime())
		self._revise("B")
		alert = frappe.db.get_value(drawing.WO, wo.name, drawing.ALERT)
		self.assertIn("Drawing changed from Rev A to Rev B on", alert)
		self.assertIn(": Hole moved 2 mm", alert)
		self.assertEqual([(t.allocated_to, t.priority) for t in _todos(wo.name)], [(OWNER, "High")])
		old = frappe.db.get_value(drawing.WO, self.card.work_order, drawing.ALERT)
		self.assertIn("from Rev A to Rev B", old)  # made before the Product Master: taken as the old revision
		panel = drawing.get_drawing_panel(wo.name)
		self.assertEqual(panel["rows"][0], {"text": alert, "colour": "red"})
		self.assertTrue(panel["can_acknowledge"])
		self.assertTrue(drawing.pending(wo.name))

		frappe.set_user(STORES)
		with self.assertRaises(frappe.PermissionError):
			drawing.acknowledge(wo.name, "B", "Checked the first piece to Rev B")
		frappe.set_user("Administrator")
		with self.assertRaisesRegex(frappe.ValidationError, "at least 10 characters"):
			drawing.acknowledge(wo.name, "B", "ok")
		with self.assertRaisesRegex(frappe.ValidationError, "Work to Rev B"):
			drawing.acknowledge(wo.name, "Z", "Checked the first piece to Rev B")
		drawing.acknowledge(wo.name, "B", "Checked the first piece to Rev B")
		values = frappe.db.get_value(
			drawing.WO, wo.name, [drawing.REVISION, drawing.ACK_BY, drawing.DECISION], as_dict=True
		)
		self.assertEqual(
			(values[drawing.REVISION], values[drawing.ACK_BY], values[drawing.DECISION]),
			("B", "Administrator", "Work to Rev B: Checked the first piece to Rev B"),
		)
		self.assertFalse(_todos(wo.name))
		self.assertFalse(drawing.pending(wo.name))
		rows = drawing.get_drawing_panel(wo.name)["rows"]
		self.assertEqual(rows[0], {"text": "Made to drawing Rev B · current Rev B", "colour": "green"})
		self.assertTrue(
			rows[1]["text"].startswith("Work to Rev B: Checked the first piece to Rev B · acknowledged by")
		)

	def test_job_order_already_on_the_new_revision_or_closed_is_not_flagged(self):
		wo = make_work_order(self.item, 5, now_datetime())
		frappe.db.set_value(drawing.WO, wo.name, drawing.REVISION, "C")
		closed = make_work_order(self.item, 5, now_datetime())
		frappe.db.set_value(drawing.WO, closed.name, "status", "Completed")
		self._revise("C")
		self.assertFalse(frappe.db.get_value(drawing.WO, wo.name, drawing.ALERT))
		self.assertFalse(frappe.db.get_value(drawing.WO, closed.name, drawing.ALERT))

	def test_first_revision_flags_nothing_and_shift_entries_warn(self):
		# setUp gave the product its first revision (A, nothing before): the Job Card's Job Order is not flagged
		self.assertFalse(frappe.db.get_value(drawing.WO, self.card.work_order, drawing.ALERT))
		self.assertEqual(drawing.flag_job_orders(self.item, "A", "A"), [])  # every open job on A already
		wo = make_work_order(self.item, 5, now_datetime())
		self._revise("B")
		frappe.clear_messages()
		drawing.warn_shift_entry(frappe._dict(production=[frappe._dict(work_order=wo.name)]))
		self.assertIn(f"Job Order {wo.name}: Drawing changed from Rev A to Rev B", str(frappe.message_log))
