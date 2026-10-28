"""C3a-P1 - The Job Order (Work Order) status panel: routing progress and quantity against target.

On a submitted Job Order the panel shows, in plain words:
- Quantity: made (finished goods booked) of the target, and what the shop floor reported good / rejected on the
  Shift Production Entries of this Job Order.
- Routing: each operation in order with its machine, how many are done against the target (from its Job
  Card, including shift entries not yet submitted on the Job Card), its state, and which step is next.
- Delivery: due date and days left or late; when the Sales Order carries LD, the LD on this line so far.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, formatdate, getdate, today

from pepl_os.pepl_production import ld

SPR = "PEPL Shift Production Entry"


def _shop_floor(work_order):
	row = frappe.db.sql(
		f"""select coalesce(sum(p.good_qty), 0), coalesce(sum(p.rejected_qty), 0)
		from `tabPEPL SPR Production` p join `tab{SPR}` s on s.name = p.parent
		where s.docstatus = 1 and p.work_order = %s""",
		work_order,
	)
	return flt(row[0][0]), flt(row[0][1])


def _operations(wo):
	cards = {}
	for card in frappe.get_all(
		"Job Card",
		filters={"work_order": wo.name, "docstatus": ["<", 2]},
		fields=["name", "operation_id", "status", "total_completed_qty", "for_quantity", "docstatus"],
		order_by="creation",
	):
		cards.setdefault(card.operation_id, []).append(card)
	steps = []
	for op in wo.get("operations") or []:
		mine = cards.get(op.name, [])
		done = max(flt(op.completed_qty), sum(flt(c.total_completed_qty) for c in mine))
		steps.append(
			frappe._dict(
				idx=op.idx,
				operation=op.operation,
				workstation=op.workstation or "",
				done=done,
				target=flt(wo.qty),
				status=op.status,
				cards=[c.name for c in mine],
				card_status=", ".join(sorted({c.status for c in mine if c.status})),
			)
		)
	return steps


def panel_rows(wo):
	wo = frappe.get_doc("Work Order", wo) if isinstance(wo, str) else wo
	target = flt(wo.qty)
	made = flt(wo.produced_qty)
	good, rejected = _shop_floor(wo.name)
	rows = []
	percent = round(100.0 * made / target) if target else 0
	rows.append(
		{
			"text": _("Made {0} of {1} ({2}%)").format(flt(made, 3), flt(target, 3), percent)
			+ (
				" · " + _("shop floor reported {0} good, {1} rejected").format(flt(good, 3), flt(rejected, 3))
				if good or rejected
				else ""
			),
			"colour": "green" if made >= target else ("orange" if rejected else "blue"),
		}
	)
	steps = _operations(wo)
	next_step = next((s for s in steps if s.done < s.target), None)
	for s in steps:
		state = _("done") if s.done >= s.target else (s.card_status or _(s.status or "Pending"))
		text = _("Step {0}: {1} on {2} - {3} of {4} ({5})").format(
			s.idx, s.operation, s.workstation or _("no machine"), flt(s.done, 3), flt(s.target, 3), state
		)
		if next_step is s:
			text = "▶ " + text
		colour = "green" if s.done >= s.target else ("blue" if next_step is s else "gray")
		rows.append({"text": text, "colour": colour})
	if not steps:
		rows.append({"text": _("No operations on this Job Order (no routing to follow)."), "colour": "gray"})

	due = wo.get("expected_delivery_date")
	if due and made < target:
		days = date_diff(getdate(due), getdate(today()))
		if days < 0:
			rows.append({"text": _("Due {0}: {1} days late").format(formatdate(due), -days), "colour": "red"})
		else:
			rows.append(
				{
					"text": _("Due {0}: {1} days left").format(formatdate(due), days),
					"colour": "orange" if days <= 3 else "green",
				}
			)
	if wo.get("sales_order") and wo.get("sales_order_item") and made < target:
		if cint(frappe.db.get_value("Sales Order", wo.sales_order, ld.APPLICABLE)):
			result = ld.exposure(wo.sales_order)
			line = next((x for x in result["lines"] if x.so_detail == wo.sales_order_item), None)
			if line and line.amount:
				rows.append(
					{
						"text": _("LD so far on this Sales Order line: {0} ({1} late)").format(
							frappe.format(line.amount, {"fieldtype": "Currency"}), flt(line.late_qty, 3)
						),
						"colour": "red",
					}
				)
	return rows


@frappe.whitelist()
def get_job_order_panel(work_order):
	"""For the Job Order form."""
	frappe.has_permission("Work Order", "read", doc=work_order, throw=True)
	return {"rows": panel_rows(work_order)}
