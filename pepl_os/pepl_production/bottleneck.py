"""C3a-B4 - Bottleneck report: how long work waits in front of each machine group, from the Job Order operation
times.

Times come from the Job Card time logs (the shift entries post their blocks there, C3a-X1; logs typed on the Job
Card count too). For each Job Order the operations are taken in their routing order; for each operation:
- started = its first time log; finished = its last time log, once the operation is complete (good quantity
  logged reaches the Job Card quantity, or the Job Card is submitted).
- wait = this operation's start - the previous operation's finish: the work sat in front of this machine group.
  An operation that started before the previous one finished (pieces passed on in batches) "overlapped": wait 0.
- waiting now = the previous operation is finished, this one has not started and the Job Order is still open:
  hours since the previous operation finished.
The first operation of a Job Order has no previous operation and no wait.

Hours are clock hours (nights and holidays included), so a long wait over a weekend shows as such.
Per machine group: number of waits, average, longest and total wait, overlaps, jobs waiting now and the oldest
of them, and run hours. The group with the longest average wait is the bottleneck; a group whose average wait is
above "Bottleneck: Wait Warning Hours" (System Parameters) is red.
"""

from itertools import pairwise

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime, today

from pepl_os.common import params

WARNING_FIELD = "custom_bottleneck_wait_warning_hours"
DEFAULT_WARNING = 8
OPEN_STATUSES = ("Not Started", "In Process")
NO_GROUP = "(no machine group)"
LOOK_BACK_DAYS = 90


def warning_hours():
	value = params.get(WARNING_FIELD, DEFAULT_WARNING)
	return flt(value) if flt(value) > 0 else DEFAULT_WARNING


def _hours(later, earlier):
	return (get_datetime(later) - get_datetime(earlier)).total_seconds() / 3600.0


def operation_waits(ops, is_open=True, now=None):
	"""Waits of one Job Order. ops: its operations in routing order, dicts with operation, group, start, end,
	finished. Returns one dict per operation after the first: state 'waited' / 'overlapped' / 'waiting' / '' and
	hours."""
	now = get_datetime(now or now_datetime())
	out = []
	for prev, cur in pairwise(ops):
		row = {
			"operation": cur.get("operation"),
			"group": cur.get("group") or NO_GROUP,
			"previous": prev.get("operation"),
			"previous_finished": prev.get("end") if prev.get("finished") else None,
			"started": cur.get("start"),
			"state": "",
			"hours": 0.0,
		}
		if cur.get("start"):
			if prev.get("finished") and prev.get("end"):
				hours = _hours(cur["start"], prev["end"])
				row["state"], row["hours"] = ("waited", hours) if hours >= 0 else ("overlapped", 0.0)
			elif prev.get("start"):
				row["state"] = "overlapped"
		elif is_open and prev.get("finished") and prev.get("end"):
			row["state"], row["hours"] = "waiting", max(0.0, _hours(now, prev["end"]))
		out.append(row)
	return out


def _job_orders(filters):
	conditions = {"docstatus": 1, "status": ["!=", "Cancelled"]}
	if filters.get("company"):
		conditions["company"] = filters["company"]
	if filters.get("job_order"):
		conditions["name"] = filters["job_order"]
	orders = frappe.get_all(
		"Work Order",
		filters=conditions,
		or_filters={
			"status": ["in", OPEN_STATUSES],
			"planned_start_date": [">=", add_days(filters.get("from_date") or today(), -LOOK_BACK_DAYS)],
		},
		fields=["name", "production_item", "status"],
	)
	return orders


def _operations(order_names):
	"""{job order: [operation dicts in routing order]} from Job Cards and their time logs."""
	if not order_names:
		return {}
	ops = {}
	groups = {}

	def group_of(workstation):
		if workstation not in groups:
			groups[workstation] = (
				frappe.db.get_value("Workstation", workstation, "workstation_type") if workstation else None
			) or NO_GROUP
		return groups[workstation]

	for op in frappe.get_all(
		"Work Order Operation",
		filters={"parent": ["in", order_names], "parenttype": "Work Order"},
		fields=["name", "parent", "idx", "operation", "workstation"],
		order_by="parent, idx",
	):
		ops.setdefault(op.parent, []).append(
			{
				"id": op.name,
				"operation": op.operation,
				"workstation": op.workstation,
				"group": group_of(op.workstation),
				"start": None,
				"end": None,
				"done": 0.0,
				"target": 0.0,
				"minutes": 0.0,
				"cards": [],
				"submitted": True,
			}
		)
	by_id = {op["id"]: op for rows in ops.values() for op in rows}
	cards = frappe.get_all(
		"Job Card",
		filters={"work_order": ["in", order_names], "docstatus": ["<", 2]},
		fields=["name", "operation_id", "workstation", "for_quantity", "docstatus"],
	)
	card_op = {}
	for card in cards:
		op = by_id.get(card.operation_id)
		if not op:
			continue
		card_op[card.name] = op
		op["cards"].append(card.name)
		op["target"] += flt(card.for_quantity)
		op["submitted"] = op["submitted"] and card.docstatus == 1
		if card.workstation:
			op["workstation"], op["group"] = card.workstation, group_of(card.workstation)
	if card_op:
		for log in frappe.get_all(
			"Job Card Time Log",
			filters={"parent": ["in", list(card_op)], "parenttype": "Job Card"},
			fields=["parent", "from_time", "to_time", "completed_qty", "time_in_mins"],
		):
			op = card_op[log.parent]
			if log.from_time and (not op["start"] or get_datetime(log.from_time) < get_datetime(op["start"])):
				op["start"] = log.from_time
			if log.to_time and (not op["end"] or get_datetime(log.to_time) > get_datetime(op["end"])):
				op["end"] = log.to_time
			op["done"] += flt(log.completed_qty)
			op["minutes"] += flt(log.time_in_mins) or (
				_hours(log.to_time, log.from_time) * 60 if log.from_time and log.to_time else 0
			)
	for rows in ops.values():
		for op in rows:
			op["finished"] = bool(op["cards"]) and (
				op["submitted"] or (op["target"] > 0 and op["done"] >= op["target"])
			)
	return ops


def operation_rows(filters=None, now=None):
	"""One row per operation (after the first) that waited, overlapped or is waiting now."""
	filters = frappe._dict(filters or {})
	start = getdate(filters.get("from_date") or add_days(today(), -30))
	end = getdate(filters.get("to_date") or today())
	orders = _job_orders(filters)
	info = {o.name: o for o in orders}
	out = []
	for name, ops in _operations([o.name for o in orders]).items():
		order = info[name]
		for i, wait in enumerate(operation_waits(ops, order.status in OPEN_STATUSES, now), start=1):
			if not wait["state"]:
				continue
			if wait["state"] != "waiting" and not start <= getdate(wait["started"]) <= end:
				continue
			if filters.get("workstation_type") and wait["group"] != filters["workstation_type"]:
				continue
			wait.update(
				{
					"job_order": name,
					"item_code": order.production_item,
					"minutes": ops[i]["minutes"],
					"hours": round(wait["hours"], 2),
				}
			)
			out.append(wait)
	return sorted(out, key=lambda r: -r["hours"])


def group_rows(op_rows, warning=None):
	"""Per machine group, longest average wait first; the first group with any wait is the bottleneck."""
	warning = warning_hours() if warning is None else warning
	groups = {}
	for r in op_rows:
		g = groups.setdefault(
			r["group"],
			{
				"group": r["group"],
				"waits": 0,
				"total": 0.0,
				"longest": 0.0,
				"overlapped": 0,
				"waiting_now": 0,
				"oldest": 0.0,
				"run_minutes": 0.0,
			},
		)
		if r["state"] == "waited":
			g["waits"] += 1
			g["total"] += r["hours"]
			g["longest"] = max(g["longest"], r["hours"])
		elif r["state"] == "overlapped":
			g["overlapped"] += 1
		elif r["state"] == "waiting":
			g["waiting_now"] += 1
			g["oldest"] = max(g["oldest"], r["hours"])
		if r["state"] != "waiting":
			g["run_minutes"] += flt(r.get("minutes"))
	out = []
	for g in groups.values():
		average = g["total"] / g["waits"] if g["waits"] else 0.0
		out.append(
			{
				"workstation_type": g["group"],
				"waits": g["waits"],
				"average_hours": round(average, 2),
				"longest_hours": round(g["longest"], 2),
				"total_hours": round(g["total"], 2),
				"overlapped": g["overlapped"],
				"waiting_now": g["waiting_now"],
				"oldest_waiting_hours": round(g["oldest"], 2),
				"run_hours": round(g["run_minutes"] / 60.0, 2),
				"colour": "red" if average > warning else ("orange" if g["waiting_now"] else "green"),
			}
		)
	out.sort(key=lambda r: (-r["average_hours"], -r["oldest_waiting_hours"], r["workstation_type"]))
	for rank, row in enumerate(out, start=1):
		row["rank"] = rank
		row["bottleneck"] = 1 if rank == 1 and (row["average_hours"] > 0 or row["waiting_now"]) else 0
	return out


def summary(groups, warning=None):
	warning = warning_hours() if warning is None else warning
	if not groups or not groups[0]["bottleneck"]:
		return _("No waiting between operations in this period.")
	top = groups[0]
	text = _(
		"Bottleneck: {0} - work waited on average {1} h before its machines (longest {2} h); {3} job(s) waiting in front of it now."
	).format(top["workstation_type"], top["average_hours"], top["longest_hours"], top["waiting_now"])
	red = [g["workstation_type"] for g in groups if g["colour"] == "red"]
	if red:
		text += " " + _("Average wait above {0} h: {1}.").format(
			cint(warning) if warning == int(warning) else warning, ", ".join(red)
		)
	return text
