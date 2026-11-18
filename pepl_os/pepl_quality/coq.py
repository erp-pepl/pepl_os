"""C3b-B2 - Cost of Quality: what poor quality cost PEPL in rupees - shop-floor rejections, NCR rework and other
NCR costs, customer returns - by month or by item.

Where each rupee comes from (dates: the shift date, the NCR's Raised On, the weighment date):
- Rejection: pieces rejected on submitted Shift Production Entries x the made item's cost a piece (Item Valuation
  Rate; else its stock valuation rate). Pieces of an item with no cost are counted and listed, never priced at 0
  silently.
- Scrap recovered: the value of submitted Scrap Weighments with source "Rejection" (C3a-B6), taken off the rejection
  cost (the scrap is sold). By item, a weighment is shared over the items its shift entry rejected, by pieces.
- NCR rework: "Cost of the Non-Conformance" of NCRs with disposition Rework.
- NCR other (internal): the cost of every other NCR not from a customer - scrap, return to supplier, regrade,
  concession, use as is, or no disposition yet.
- Customer (external): the cost of NCRs with source Customer (returns and complaints).
Cancelled NCRs are left out. An NCR raised by the rejection-rate rule (QA-NCR-RATE) is about pieces already counted
under Rejection, so its own cost is not added again. NCRs whose disposition needs a cost (Rework, Scrap, Return to
Supplier, Regrade) but have none are counted as "NCRs without a cost".

Total = rejection - scrap recovered + NCR rework + NCR other + customer.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, get_last_day, getdate, today

from pepl_os.pepl_quality import ncr

SPR = "PEPL Shift Production Entry"
SPR_ROW = "PEPL SPR Production"
WEIGHMENT = "PEPL Scrap Weighment"
COSTED = ("Rework", "Scrap", "Return to Supplier", "Regrade")
AMOUNTS = ("rejection", "scrap_recovered", "ncr_rework", "ncr_other", "customer")
GROUPS = ("Month", "Item")


def period(filters=None):
	"""(from, to) of the filters; default this month."""
	filters = frappe._dict(filters or {})
	start = getdate(filters.get("from_date") or get_first_day(today()))
	end = getdate(filters.get("to_date") or get_last_day(today()))
	return start, end


def piece_cost(item_code, cache):
	"""The cost of one piece of the item, or None when PEPL OS knows none."""
	if item_code not in cache:
		rate = flt(frappe.db.get_value("Item", item_code, "valuation_rate"))
		if rate <= 0:
			rate = flt(
				frappe.db.get_value(
					"Bin", {"item_code": item_code, "valuation_rate": [">", 0]}, "valuation_rate"
				)
			)
		cache[item_code] = rate if rate > 0 else None
	return cache[item_code]


def rejection_events(start, end):
	"""One event per item and shift date: rejected pieces and their cost."""
	rows = frappe.db.sql(
		f"""select s.name as entry, s.posting_date as day, r.production_item as item, sum(r.rejected_qty) as pieces
		from `tab{SPR_ROW}` r join `tab{SPR}` s on s.name = r.parent
		where s.docstatus = 1 and s.posting_date between %s and %s and r.rejected_qty > 0
		group by s.name, s.posting_date, r.production_item""",
		(start, end),
		as_dict=True,
	)
	cache = {}
	events = []
	for r in rows:
		rate = piece_cost(r.item, cache)
		events.append(
			frappe._dict(
				day=r.day,
				item=r.item,
				entry=r.entry,
				kind="rejection",
				pieces=flt(r.pieces),
				amount=flt(r.pieces) * rate if rate else 0,
				unpriced=flt(r.pieces) if not rate else 0,
			)
		)
	return events


def scrap_events(start, end, rejections):
	"""Scrap recovered from rejected pieces: one event per weighment (by item: shared by the entry's pieces)."""
	rows = frappe.get_all(
		WEIGHMENT,
		filters={"docstatus": 1, "source": "Rejection", "weighment_date": ["between", [start, end]]},
		fields=["name", "weighment_date", "amount", "shift_production_entry"],
	)
	pieces_by_entry = {}
	for e in rejections:
		pieces_by_entry.setdefault(e.entry, {}).setdefault(e.item, 0)
		pieces_by_entry[e.entry][e.item] += e.pieces
	events = []
	for w in rows:
		share = pieces_by_entry.get(w.shift_production_entry)
		if not share and w.shift_production_entry:
			share = {
				r.production_item: flt(r.rejected_qty)
				for r in frappe.get_all(
					SPR_ROW,
					filters={"parent": w.shift_production_entry, "rejected_qty": [">", 0]},
					fields=["production_item", "rejected_qty"],
				)
			}
		total = sum(share.values()) if share else 0
		if not total:
			events.append(
				frappe._dict(day=w.weighment_date, item=None, kind="scrap_recovered", amount=flt(w.amount))
			)
			continue
		for item, pieces in share.items():
			events.append(
				frappe._dict(
					day=w.weighment_date,
					item=item,
					kind="scrap_recovered",
					amount=flt(w.amount) * pieces / total,
				)
			)
	return events


def ncr_events(start, end):
	rows = frappe.get_all(
		ncr.NCR,
		filters={"status": ["!=", ncr.CANCELLED], "raised_on": ["between", [start, end]]},
		fields=["name", "raised_on", "item", "source", "disposition", "estimated_cost", "raise_rule"],
	)
	events = []
	for r in rows:
		if r.raise_rule == ncr.RULE_RATE:
			continue  # its pieces are counted under Rejection
		if r.source == ncr.CUSTOMER:
			kind = "customer"
		elif r.disposition == "Rework":
			kind = "ncr_rework"
		else:
			kind = "ncr_other"
		events.append(
			frappe._dict(
				day=r.raised_on,
				item=r.item,
				kind=kind,
				ncr=r.name,
				amount=flt(r.estimated_cost),
				no_cost=r.disposition in COSTED and flt(r.estimated_cost) <= 0,
			)
		)
	return events


def events(filters=None):
	start, end = period(filters)
	rejections = rejection_events(start, end)
	return rejections + scrap_events(start, end, rejections) + ncr_events(start, end)


def _key(event, group):
	if group == "Item":
		return event.item or _("(not by item)")
	return getdate(event.day).strftime("%Y-%m")


def total_of(row):
	return (
		flt(row.rejection)
		- flt(row.scrap_recovered)
		+ flt(row.ncr_rework)
		+ flt(row.ncr_other)
		+ flt(row.customer)
	)


def rows(filters=None):
	"""One row per month (or item) with every amount, the total, and what is not priced."""
	filters = frappe._dict(filters or {})
	group = filters.get("group_by") if filters.get("group_by") in GROUPS else "Month"
	table = {}
	for e in events(filters):
		key = _key(e, group)
		row = table.setdefault(
			key,
			frappe._dict(
				{
					"key": key,
					**{a: 0.0 for a in AMOUNTS},
					"rejected_pieces": 0.0,
					"unpriced_pieces": 0.0,
					"unpriced_items": set(),
					"ncrs": 0,
					"ncrs_without_cost": 0,
				}
			),
		)
		row[e.kind] += flt(e.amount)
		if e.kind == "rejection":
			row.rejected_pieces += e.pieces
			row.unpriced_pieces += e.unpriced
			if e.unpriced:
				row.unpriced_items.add(e.item)
		elif e.kind in ("ncr_rework", "ncr_other", "customer"):
			row.ncrs += 1
			row.ncrs_without_cost += cint(e.no_cost)
	result = []
	for key in sorted(table):
		row = table[key]
		row.total = total_of(row)
		notes = []
		if row.unpriced_pieces:
			notes.append(
				_("{0} rejected piece(s) without a cost a piece: {1}").format(
					cint(row.unpriced_pieces), ", ".join(sorted(row.unpriced_items))[:200]
				)
			)
		if row.ncrs_without_cost:
			notes.append(_("{0} NCR(s) without a cost").format(row.ncrs_without_cost))
		row.notes = "; ".join(notes)
		del row["unpriced_items"]
		for amount in (*AMOUNTS, "total"):
			row[amount] = round(flt(row[amount]), 2)
		result.append(row)
	return result


def month_total(as_of=None):
	"""Cost of quality of the month of `as_of` (default: this month)."""
	day = getdate(as_of or today())
	data = rows({"from_date": get_first_day(day), "to_date": get_last_day(day), "group_by": "Month"})
	return round(sum(r.total for r in data), 2)
