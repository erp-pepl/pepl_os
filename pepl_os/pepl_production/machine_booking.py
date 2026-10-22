"""C3a-X6 - A Production Plan may not book a machine twice for the same time.

Each Production Plan row is laid out the way ERPNext lays out a Job Order: from the row's Planned Start, the
BOM's operations one after the other (operations sharing a sequence number run together), each for
quantity x BOM minutes, with Manufacturing Settings' "Time Between Operations" in between. Every operation
is a booking of its machine (Workstation) for that time.

Those bookings are compared, machine by machine, with what already holds the machine:
- the other rows of the same plan,
- open Job Orders (submitted, Not Started / In Process): their operations not yet completed, at the
  planned times ERPNext stored (capacity planning on) or laid out from the Job Order's Planned Start,
- the rows of other open Production Plans not yet turned into Job Orders.

A machine is double-booked when more bookings run at the same moment than its Production Capacity (jobs
it can run at once; 1 for most machines). What happens then follows "Machine Double-Booking Mode" in System
Parameters → Production:
- Advisory: the plan is saved and submitted; the clashes are shown.
- Soft Block: submitting needs a reason, written to the Override Log (rule PRD-DOUBLE-BOOK). When
  "Require a Reason for Every Override" is off, it only warns.
- Hard Block: the plan cannot be submitted until the clashes are resolved.
A draft plan is always saved, so the planner can fix it; the clashes are listed on the plan.
Sub-assembly rows are not laid out (their Job Orders are checked once they exist).
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, format_datetime, get_datetime

from pepl_os.common.overrides import has_recent_override

SYSTEM_PARAMETERS = "PEPL System Parameters"
MODE_FIELD = "custom_double_booking_mode"
ENFORCE_FIELD = "custom_enforce_override_reason"
CLASHES_FIELD = "custom_machine_clashes"
RULE_CODE = "PRD-DOUBLE-BOOK"
ADVISORY, SOFT, HARD = "Advisory", "Soft Block", "Hard Block"
MODES = (ADVISORY, SOFT, HARD)
OPEN_JOB_ORDER = ("Not Started", "In Process")
CLOSED_PLAN = ("Completed", "Closed", "Cancelled")
MAX_LISTED = 10


def _single(doctype, field):
	# cache=False: a change made in System Parameters applies to the very next plan.
	return frappe.db.get_single_value(doctype, field, cache=False)


def mode():
	value = _single(SYSTEM_PARAMETERS, MODE_FIELD)
	return value if value in MODES else SOFT


def reasons_enforced():
	value = _single(SYSTEM_PARAMETERS, ENFORCE_FIELD)
	return True if value in (None, "") else bool(cint(value))


def gap_minutes():
	return flt(_single("Manufacturing Settings", "mins_between_operations"))


def layout(start, operations, gap=0):
	"""ERPNext's own layout of a Job Order's operations.

	operations: dicts with workstation, minutes, sequence_id (in order). Returns them with start / end.
	"""
	result, previous = [], None
	for op in operations:
		if previous is None:
			begin = get_datetime(start)
		elif op.get("sequence_id") and op.get("sequence_id") == previous.get("sequence_id"):
			begin = previous["start"]
		else:
			begin = add_to_date(previous["end"], minutes=gap)
		row = dict(op, start=begin, end=add_to_date(begin, minutes=flt(op["minutes"])))
		result.append(row)
		previous = row
	return result


def _bom_operations(bom_no):
	quantity = flt(frappe.db.get_value("BOM", bom_no, "quantity")) or 1
	rows = frappe.get_all(
		"BOM Operation",
		filters={"parent": bom_no, "parenttype": "BOM"},
		fields=["operation", "workstation", "time_in_mins", "sequence_id"],
		order_by="idx",
	)
	return quantity, rows


def plan_bookings(plan, gap=None):
	"""Bookings of a Production Plan's rows not yet on a Job Order."""
	gap = gap_minutes() if gap is None else gap
	bookings = []
	for row in plan.get("po_items"):
		qty = flt(row.planned_qty) - flt(row.ordered_qty)
		if qty <= 0 or not row.bom_no or not row.planned_start_date:
			continue
		bom_qty, operations = _bom_operations(row.bom_no)
		ops = [
			{
				"workstation": op.workstation,
				"operation": op.operation,
				"minutes": flt(op.time_in_mins) * qty / bom_qty,
				"sequence_id": op.sequence_id,
			}
			for op in operations
		]
		for op in layout(row.planned_start_date, ops, gap):
			if op["workstation"] and op["end"] > op["start"]:
				op.update(
					source="Production Plan",
					reference=plan.name,
					label=_("{0} row {1}: {2}").format(plan.name or _("this plan"), row.idx, row.item_code),
					key=("plan", plan.name, row.idx, op["operation"]),
				)
				bookings.append(op)
	return bookings


def job_order_bookings(workstations, exclude_plan=None, gap=None):
	"""Bookings of open Job Orders on these machines (operations not completed)."""
	if not workstations:
		return []
	gap = gap_minutes() if gap is None else gap
	names = frappe.get_all(
		"Work Order Operation",
		filters={"workstation": ["in", list(workstations)], "parenttype": "Work Order"},
		pluck="parent",
		distinct=True,
	)
	if not names:
		return []
	filters = {"name": ["in", names], "docstatus": 1, "status": ["in", OPEN_JOB_ORDER]}
	bookings = []
	for wo in frappe.get_all(
		"Work Order",
		filters=filters,
		fields=["name", "production_item", "planned_start_date", "production_plan"],
	):
		if exclude_plan and wo.production_plan == exclude_plan:
			continue
		operations = frappe.get_all(
			"Work Order Operation",
			filters={"parent": wo.name, "parenttype": "Work Order"},
			fields=[
				"operation",
				"workstation",
				"time_in_mins",
				"sequence_id",
				"status",
				"planned_start_time",
				"planned_end_time",
			],
			order_by="idx",
		)
		ops = [
			{
				"workstation": op.workstation,
				"operation": op.operation,
				"minutes": flt(op.time_in_mins),
				"sequence_id": op.sequence_id,
				"status": op.status,
				"stored": (op.planned_start_time, op.planned_end_time),
			}
			for op in operations
		]
		for op in layout(wo.planned_start_date, ops, gap):
			stored_start, stored_end = op.pop("stored")
			if stored_start and stored_end and get_datetime(stored_end) > get_datetime(stored_start):
				op["start"], op["end"] = get_datetime(stored_start), get_datetime(stored_end)
			if (
				op["workstation"] in workstations
				and op.get("status") != "Completed"
				and op["end"] > op["start"]
			):
				op.update(
					source="Work Order",
					reference=wo.name,
					label=_("Job Order {0}: {1}").format(wo.name, wo.production_item),
					key=("wo", wo.name, op["operation"]),
				)
				bookings.append(op)
	return bookings


def other_plan_bookings(workstations, exclude_plan=None, gap=None):
	"""Bookings of other open Production Plans' rows not yet on a Job Order."""
	if not workstations:
		return []
	bookings = []
	filters = {"docstatus": 1, "status": ["not in", CLOSED_PLAN]}
	if exclude_plan:
		filters["name"] = ["!=", exclude_plan]
	for name in frappe.get_all("Production Plan", filters=filters, pluck="name"):
		plan = frappe.get_doc("Production Plan", name)
		bookings += [b for b in plan_bookings(plan, gap) if b["workstation"] in workstations]
	return bookings


def _peak(intervals):
	"""Most intervals running at the same moment (an end and a start at the same minute do not clash)."""
	events = sorted(
		[(i[0], 1) for i in intervals] + [(i[1], -1) for i in intervals], key=lambda e: (e[0], e[1])
	)
	running = peak = 0
	for _moment, step in events:
		running += step
		peak = max(peak, running)
	return peak


def capacity(workstation):
	return max(cint(frappe.get_cached_value("Workstation", workstation, "production_capacity")), 1)


def find_clashes(plan):
	"""[{booking, others: [bookings], capacity}] for each of the plan's bookings that overbooks its machine."""
	gap = gap_minutes()
	mine = plan_bookings(plan, gap)
	machines = {b["workstation"] for b in mine}
	held = job_order_bookings(machines, plan.name, gap) + other_plan_bookings(machines, plan.name, gap)
	clashes = []
	for index, booking in enumerate(mine):
		# held bookings, plus this plan's earlier rows (each pair within the plan is reported once)
		pool = held + mine[:index]
		others = [
			b
			for b in pool
			if b["workstation"] == booking["workstation"]
			and b["start"] < booking["end"]
			and booking["start"] < b["end"]
		]
		if not others:
			continue
		limit = capacity(booking["workstation"])
		clipped = [(max(b["start"], booking["start"]), min(b["end"], booking["end"])) for b in others]
		if _peak(clipped) + 1 > limit:
			clashes.append({"booking": booking, "others": others, "capacity": limit})
	return clashes


def _when(booking):
	start = format_datetime(booking["start"], "dd-MM-yyyy HH:mm")
	return f"{start} - {format_datetime(booking['end'], 'HH:mm')}"


def describe(clashes):
	"""One line per clash, for the plan's field and the messages."""
	lines = []
	for clash in clashes[:MAX_LISTED]:
		booking = clash["booking"]
		others = "; ".join(f"{b['label']} ({b['operation']}, {_when(b)})" for b in clash["others"])
		lines.append(
			_("Machine {0} (runs {1} job(s) at a time): {2} ({3}, {4}) clashes with {5}").format(
				booking["workstation"],
				clash["capacity"],
				booking["label"],
				booking["operation"],
				_when(booking),
				others,
			)
		)
	if len(clashes) > MAX_LISTED:
		lines.append(_("... and {0} more.").format(len(clashes) - MAX_LISTED))
	return lines


def check_on_save(doc, method=None):
	"""doc_events: Production Plan validate (save and submit) - list the clashes on the plan.

	A draft is never refused; submit is decided in before_submit.
	"""
	lines = describe(find_clashes(doc))
	doc.set(CLASHES_FIELD, "\n".join(lines))
	if lines and (doc.docstatus == 0 or mode() == ADVISORY):
		frappe.msgprint(
			"<br>".join(lines) + "<br><br>" + _("Machine Double-Booking Mode: {0}.").format(mode()),
			title=_("Machine double-booked"),
			indicator="orange",
		)


def gate_message(doc):
	"""Why submit must stop or ask for a reason, else None. Returns (message, needs_reason)."""
	if not doc.get(CLASHES_FIELD):
		return None
	current = mode()
	first = doc.get(CLASHES_FIELD).split("\n")[0]
	if current == HARD:
		return (
			_(
				"{0} Machine Double-Booking Mode is Hard Block: move the Planned Start of the clashing rows "
				"or free the machine, then submit."
			).format(first),
			False,
		)
	if current == SOFT and reasons_enforced():
		if doc.name and has_recent_override(RULE_CODE, doc.doctype, doc.name):
			return None
		return (_("The plan double-books a machine. {0}").format(first), True)
	return None


def check_on_submit(doc, method=None):
	"""doc_events: Production Plan before_submit (after validate has listed the clashes)."""
	result = gate_message(doc)
	if not result:
		return
	message, needs_reason = result
	if needs_reason:
		frappe.throw(
			f"[{RULE_CODE}] " + message + " " + _("A reason is required to continue."),
			title=_("Reason required"),
		)
	frappe.throw(message, title=_("Machine double-booked"))


@frappe.whitelist()
def booking_gate_check(name):
	"""For the form: {rule_code, message} when a reason must be given before submit, else None."""
	doc = frappe.get_doc("Production Plan", name)
	doc.check_permission("read")
	doc.set(CLASHES_FIELD, "\n".join(describe(find_clashes(doc))))
	result = gate_message(doc)
	if result and result[1]:
		return {"rule_code": RULE_CODE, "message": result[0]}
	return None
