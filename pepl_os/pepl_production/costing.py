"""C3a-B2 - Estimated against actual cost: the CST estimate of an item against what its Job Orders really cost.

Estimate (a piece) - the item's PEPL CST Cost Sheet:
- which sheet: the CST of the Job Order's Sales Order's tender for this item (not Superseded / Obsolete); else the
  item's latest Approved or Used-in-Bid CST (latest costing date). None found: "No CST estimate".
- material = raw material (manufactured components) + bought-out cost; machining = machining cost; job work &
  other = surface treatment + other charges (component and tender level); overhead = the CST's overhead amount.

Actual (a piece) - the Job Order, the same way as the weekly CPC (C3a-X4):
- material = what its Manufacture entries consumed (stock value), less the scrap they returned. Before the first
  Manufacture entry: the BOM's raw-material cost a piece x pieces worked on the shop floor (good + rejected),
  marked "material from the BOM".
- machining = run minutes on its submitted Shift Production Entries x the machine's Machine-Hour Rate (System
  Parameters, else the machine's own Hour Rate) + the consumables issued by those entries, shared by run minutes.
- job work & other = the extra costs typed on its Manufacture entries (job work, surface treatment, freight).
  ERPNext's own operating-cost rows are left out: machining is counted from the shop floor instead.
- overhead = Overhead (%) of System Parameters on material + machining + job work & other (as the CST does).
- a piece = total ÷ pieces made (finished goods booked; before that, good pieces reported on the shop floor).

Variance % = (actual - estimate) ÷ estimate. Red when above "Costing: Variance Warning %" (System Parameters),
green otherwise. "By item" adds the Job Orders of an item together (totals ÷ pieces).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pepl_os.common import params
from pepl_os.pepl_production import machine_week
from pepl_os.pepl_production.job_order_panel import qty_text

CST = "PEPL CST Cost Sheet"
SPR = "PEPL Shift Production Entry"
WARNING_FIELD = "custom_cost_variance_warning_percent"
DEFAULT_WARNING = 10
ESTIMATE_STATUSES = ("Approved", "Used in Bid")
RETIRED_STATUSES = ("Superseded", "Obsolete")
MANUFACTURE_PURPOSES = ("Manufacture", "Material Consumption for Manufacture")
ELEMENTS = ("material", "machining", "other", "overhead")
STATUSES = ("Completed", "In Process", "Not Started", "Stopped", "Closed")


def warning_percent():
	return flt(params.get(WARNING_FIELD, DEFAULT_WARNING))


# ---------------- the estimate ----------------
def estimate_from_sheet(sheet):
	"""Cost elements of one piece from a CST (a document or a dict with its components), added up exactly as the
	CST adds up its subtotals (a component without a type counts nothing there, so nothing here either)."""
	material = machining = other = 0.0
	for c in sheet.get("components") or []:
		kind = c.get("manufactured_or_bought_out")
		if kind == "Manufactured":
			material += flt(c.get("raw_material_cost"))
			machining += flt(c.get("machining_cost"))
		elif kind == "Bought Out":
			material += flt(c.get("bought_out_cost"))
		else:
			continue
		other += flt(c.get("surface_treatment_cost")) + flt(c.get("component_other_charges"))
	other += flt(sheet.get("tender_other_charges"))
	values = {
		"material": material,
		"machining": machining,
		"other": other,
		"overhead": flt(sheet.get("overhead_amount")),
	}
	values["total"] = sum(values.values())
	return values


def _sheets(filters):
	return frappe.get_all(
		CST,
		filters=filters,
		fields=["name", "status", "costing_date"],
		order_by="costing_date desc, modified desc",
		limit=1,
	)


def tender_of(sales_order):
	if not sales_order or not frappe.db.has_column("Sales Order", "custom_tender_reference"):
		return None
	return frappe.db.get_value("Sales Order", sales_order, "custom_tender_reference")


def choose_sheet(item_code, sales_order=None):
	"""(CST name, basis) for the item, or (None, None)."""
	tender = tender_of(sales_order)
	if tender:
		found = _sheets(
			{"linked_tender": tender, "linked_item": item_code, "status": ["not in", RETIRED_STATUSES]}
		)
		if found:
			return found[0].name, _("CST of tender {0}").format(tender)
	found = _sheets({"linked_item": item_code, "status": ["in", ESTIMATE_STATUSES]})
	if found:
		return found[0].name, _("Latest {0} CST").format(_(found[0].status))
	return None, None


# ---------------- the actual ----------------
def _manufacture_entries(work_order):
	return frappe.get_all(
		"Stock Entry",
		filters={"work_order": work_order, "docstatus": 1, "purpose": ["in", MANUFACTURE_PURPOSES]},
		pluck="name",
	)


def material_value(rows):
	"""Stock value the Manufacture entry rows consumed (raw material and bought-out), less the scrap they returned.
	The finished item's own row is not material."""
	consumed = scrap = 0.0
	for row in rows:
		if cint(row.get("is_scrap_item")):
			scrap += flt(row.get("basic_amount")) if row.get("t_warehouse") else 0.0
		elif not cint(row.get("is_finished_item")) and row.get("s_warehouse"):
			consumed += flt(row.get("basic_amount"))
	return consumed - scrap


def extra_cost_value(rows):
	"""Costs typed on the Manufacture entries (job work, surface treatment, freight), without ERPNext's own
	operating-cost rows: machining is counted from the shop floor."""
	total = 0.0
	for row in rows:
		if cint(row.get("has_operating_cost")) or cint(row.get("has_corrective_cost")):
			continue
		if (row.get("description") or "").strip() == "Additional Operating Cost":
			continue
		total += flt(row.get("base_amount")) or flt(row.get("amount"))
	return total


def _entry_rows(entries):
	if not entries:
		return [], []
	where = {"parent": ["in", entries], "parenttype": "Stock Entry"}
	items = frappe.get_all(
		"Stock Entry Detail",
		filters=where,
		fields=["s_warehouse", "t_warehouse", "basic_amount", "is_finished_item", "is_scrap_item"],
	)
	costs = frappe.get_all(
		"Landed Cost Taxes and Charges",
		filters=where,
		fields=["base_amount", "amount", "description", "has_operating_cost", "has_corrective_cost"],
	)
	return items, costs


def _shop_floor_rows(work_order):
	return frappe.db.sql(
		f"""select p.parent, p.minutes, p.good_qty, p.rejected_qty, s.workstation
		from `tabPEPL SPR Production` p join `tab{SPR}` s on s.name = p.parent
		where s.docstatus = 1 and p.parenttype = %s and p.work_order = %s""",
		(SPR, work_order),
		as_dict=True,
	)


def _machining(rows):
	"""(machine cost, consumables, run minutes, notes) from the shop-floor rows of one Job Order."""
	machine = 0.0
	rates = {}
	notes = []
	for r in rows:
		if r.workstation not in rates:
			rates[r.workstation] = machine_week.machine_rate(r.workstation)[0]
			if not rates[r.workstation]:
				notes.append(_("No machine-hour rate for {0}").format(r.workstation))
		machine += cint(r.minutes) / 60.0 * rates[r.workstation]
	consumables = 0.0
	for entry in {r.parent for r in rows}:
		mine = sum(cint(r.minutes) for r in rows if r.parent == entry)
		whole = flt(
			frappe.db.sql(
				"select coalesce(sum(minutes), 0) from `tabPEPL SPR Production` where parent = %s and parenttype = %s",
				(entry, SPR),
			)[0][0]
		)
		issued = sum(
			flt(v)
			for v in frappe.get_all(
				"Stock Entry",
				filters={"custom_shift_production_entry": entry, "docstatus": 1},
				pluck="total_outgoing_value",
			)
		)
		consumables += issued * mine / whole if whole else 0.0
	return machine, consumables, sum(cint(r.minutes) for r in rows), notes


def actual_for(wo):
	"""Cost of one Job Order: totals of each element, pieces, and notes."""
	wo = frappe.get_doc("Work Order", wo) if isinstance(wo, str) else wo
	entries = _manufacture_entries(wo.name)
	rows = _shop_floor_rows(wo.name)
	good = sum(flt(r.good_qty) for r in rows)
	worked = good + sum(flt(r.rejected_qty) for r in rows)
	notes = []
	items, costs = _entry_rows(entries)
	if entries:
		material = material_value(items)
	else:
		material = machine_week._material_per_piece(wo.bom_no) * worked
		if worked:
			notes.append(_("material from the BOM (no Manufacture entry yet)"))
	machine, consumables, minutes, rate_notes = _machining(rows)
	notes += rate_notes
	other = extra_cost_value(costs)
	base = material + machine + consumables + other
	overhead = base * flt(params.get(machine_week.OVERHEAD_FIELD, 0)) / 100.0
	pieces = flt(wo.produced_qty) or good
	return frappe._dict(
		material=material,
		machining=machine + consumables,
		other=other,
		overhead=overhead,
		total=base + overhead,
		pieces=pieces,
		made=flt(wo.produced_qty),
		shop_floor_good=good,
		run_minutes=minutes,
		notes=notes,
	)


# ---------------- the report ----------------
def variance(actual, estimate):
	"""Variance % of actual against estimate, or None without an estimate."""
	return round((actual - estimate) / estimate * 100.0, 1) if estimate else None


def colour(percent, warning):
	if percent is None:
		return "gray"
	return "red" if percent > warning else "green"


def _job_orders(filters):
	conditions = {"docstatus": 1}
	if filters.get("company"):
		conditions["company"] = filters["company"]
	if filters.get("item_code"):
		conditions["production_item"] = filters["item_code"]
	if filters.get("sales_order"):
		conditions["sales_order"] = filters["sales_order"]
	if filters.get("job_order"):
		conditions["name"] = filters["job_order"]
	if filters.get("status"):
		conditions["status"] = filters["status"]
	if filters.get("from_date") and filters.get("to_date"):
		conditions["planned_start_date"] = [
			"between",
			[str(filters["from_date"]) + " 00:00:00", str(filters["to_date"]) + " 23:59:59"],
		]
	return frappe.get_all(
		"Work Order",
		filters=conditions,
		fields=[
			"name",
			"production_item",
			"item_name",
			"sales_order",
			"status",
			"qty",
			"produced_qty",
			"bom_no",
		],
		order_by="planned_start_date, name",
	)


def _piece(values, pieces):
	return {k: (values[k] / pieces if pieces else None) for k in (*ELEMENTS, "total")}


def _row(base, est, act, pieces, warning):
	"""One report row: per-piece estimate, actual and variance of each element."""
	per = _piece(act, pieces)
	row = dict(base)
	for key in (*ELEMENTS, "total"):
		row["est_" + key] = round(est[key], 2) if est else None
		row["act_" + key] = round(per[key], 2) if per[key] is not None else None
	row["variance"] = round(per["total"] - est["total"], 2) if est and per["total"] is not None else None
	row["variance_percent"] = (
		variance(per["total"], est["total"]) if est and per["total"] is not None else None
	)
	row["actual_total"] = round(act["total"], 2)
	row["estimate_total"] = round(est["total"] * pieces, 2) if est and pieces else None
	row["pieces"] = pieces
	row["colour"] = colour(row["variance_percent"], warning)
	row["_act"] = {k: act[k] for k in (*ELEMENTS, "total")}
	return row


def rows(filters=None):
	filters = frappe._dict(filters or {})
	warning = warning_percent()
	estimates = {}
	out = []
	for wo in _job_orders(filters):
		key = (wo.production_item, wo.sales_order)
		if key not in estimates:
			name, basis = choose_sheet(wo.production_item, wo.sales_order)
			estimates[key] = (name, basis, estimate_from_sheet(frappe.get_doc(CST, name)) if name else None)
		sheet, basis, est = estimates[key]
		act = actual_for(wo.name)
		notes = list(act.notes)
		if not sheet:
			notes.insert(0, _("No CST estimate for this item"))
		if not act.pieces:
			notes.insert(0, _("Nothing made yet"))
		elif not act.made:
			notes.append(
				_("{0} good on the shop floor, none booked yet").format(qty_text(act.shop_floor_good))
			)
		if wo.status not in ("Completed", "Closed"):
			notes.append(_("still running: figures change"))
		out.append(
			_row(
				{
					"job_order": wo.name,
					"item_code": wo.production_item,
					"item_name": wo.item_name,
					"sales_order": wo.sales_order,
					"status": wo.status,
					"cst": sheet,
					"basis": basis or "",
					"job_orders": 1,
					"notes": "; ".join(notes),
				},
				est,
				act,
				act.pieces,
				warning,
			)
		)
	if filters.get("group_by") == "Item":
		out = by_item(out, warning)
	for r in out:
		r.pop("_act", None)
	return out


def by_item(job_rows, warning):
	"""Adds the Job Orders of each item together: cost totals ÷ pieces; the estimate weighted by pieces."""
	keys = (*ELEMENTS, "total")
	items = {}
	for r in job_rows:
		item = items.setdefault(
			r["item_code"],
			{
				"name": r["item_name"],
				"act": dict.fromkeys(keys, 0.0),
				"est": dict.fromkeys(keys, 0.0),
				"first_est": None,
				"pieces": 0.0,
				"est_pieces": 0.0,
				"count": 0,
				"csts": set(),
				"no_estimate": 0,
			},
		)
		item["count"] += 1
		pieces = flt(r["pieces"])
		item["pieces"] += pieces
		for key in keys:
			item["act"][key] += r["_act"][key]
		if r["est_total"] is None:
			item["no_estimate"] += 1
			continue
		item["csts"].add(r["cst"])
		item["first_est"] = item["first_est"] or {k: r["est_" + k] for k in keys}
		item["est_pieces"] += pieces
		for key in keys:
			item["est"][key] += r["est_" + key] * pieces
	out = []
	for code in sorted(items):
		item = items[code]
		if item["est_pieces"]:
			est = {k: item["est"][k] / item["est_pieces"] for k in keys}
		else:
			est = item["first_est"]
		notes = []
		if item["no_estimate"]:
			notes.append(_("{0} Job Order(s) without a CST estimate").format(item["no_estimate"]))
		if not item["pieces"]:
			notes.append(_("Nothing made yet"))
		out.append(
			_row(
				{
					"job_order": "",
					"item_code": code,
					"item_name": item["name"],
					"sales_order": "",
					"status": "",
					"cst": ", ".join(sorted(item["csts"])),
					"basis": "",
					"job_orders": item["count"],
					"notes": "; ".join(notes),
				},
				est,
				item["act"],
				item["pieces"],
				warning,
			)
		)
	return out


def summary_message(data):
	"""The line above the report: how many rows are over the warning, how many have no estimate."""
	warning = warning_percent()
	over = sum(1 for r in data if r.get("colour") == "red")
	missing = sum(1 for r in data if r.get("est_total") is None)
	text = _(
		"Red: actual a piece above the CST estimate by more than {0}% (System Parameters → Costing: Variance Warning %)."
	).format(qty_text(warning))
	text += " " + _("{0} of {1} row(s) over; {2} without a CST estimate.").format(over, len(data), missing)
	return frappe.utils.escape_html(text)
