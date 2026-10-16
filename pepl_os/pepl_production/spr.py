"""C3a-X1 - Shift Production Entry (SPR): what one machine did in one shift, entered by one operator.

Rows:
- Production: time blocks against open Job Cards of this machine, with good and rejected quantity.
- Downtime: stops by downtime category (planned / unplanned / PM; breakdowns feed MTBF / MTTR).
- Tool changes: when, which tool, why, and a photo.
- Consumables: what was used on the machine.

On submit the production blocks become Job Card time logs (so the Job Order shows progress and actual
time) and the consumables become one Material Issue against the machine group (counted by the C2-21
consumables report). Cancel takes both back. The OEE and MTBF / MTTR jobs (X3, X4), the kiosk (B1) and
the Scrap Register wiring (B6) all read these rows.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, getdate, strip_html, to_timedelta, today

from pepl_os.common import params
from pepl_os.pepl_production import skill
from pepl_os.pepl_production.masters import DOWNTIME, OPERATOR, SHIFT
from pepl_os.pepl_stores import stock_tree

DOCTYPE = "PEPL Shift Production Entry"
PRODUCTION_ROW = "PEPL SPR Production"
DOWNTIME_ROW = "PEPL SPR Downtime"

GRACE_FIELD = "custom_spr_shift_grace_minutes"
UNACCOUNTED_FIELD = "custom_spr_max_unaccounted_minutes"
PHOTO_FIELD = "custom_spr_tool_photo_required"
GRACE_RANGE = (0, 120)

# Job Card Time Log fields that tie a log to the SPR row it came from.
LOG_SPR_FIELD = "custom_pepl_spr"
LOG_ROW_FIELD = "custom_pepl_spr_row"
STOCK_ENTRY_SPR_FIELD = "custom_shift_production_entry"


# Time --------------------------------------------------------------------------------------------------


def _td(value):
	return to_timedelta(value) if value not in (None, "") else None


def crosses_midnight(shift):
	return _td(shift.end_time) <= _td(shift.start_time)


def shift_window(posting_date, shift):
	"""(start, end) datetimes of the shift that starts on posting_date."""
	day = get_datetime(getdate(posting_date))
	start = day + _td(shift.start_time)
	end = day + _td(shift.end_time)
	if end <= start:
		end += timedelta(days=1)
	return start, end


def time_in_shift(posting_date, shift, value, grace_minutes=0):
	"""The datetime of a clock time inside the shift. In a shift past midnight, an early-morning time
	(up to the shift end plus the grace) belongs to the next day."""
	day = get_datetime(getdate(posting_date))
	t = _td(value)
	if crosses_midnight(shift) and t <= _td(shift.end_time) + timedelta(minutes=cint(grace_minutes)):
		return day + timedelta(days=1) + t
	return day + t


def _minutes(start, end):
	return round((end - start).total_seconds() / 60)


def _clock(value):
	return get_datetime(value).strftime("%H:%M")


def grace_minutes():
	low, high = GRACE_RANGE
	value = params.get_int(GRACE_FIELD, 30)
	return min(max(value, low), high)


# Validate ----------------------------------------------------------------------------------------------


def validate_entry(doc):
	_set_defaults(doc)
	shift = _check_header(doc)
	skill.check_on_save(doc)  # C3a-X7
	grace = grace_minutes()
	window = shift_window(doc.posting_date, shift)
	intervals = []
	for row in doc.get("production") or []:
		_set_times(doc, shift, window, grace, row, _("Production row {0}").format(row.idx))
		intervals.append((row.from_datetime, row.to_datetime, _("Production row {0}").format(row.idx)))
	for row in doc.get("downtime") or []:
		_set_times(doc, shift, window, grace, row, _("Downtime row {0}").format(row.idx))
		intervals.append((row.from_datetime, row.to_datetime, _("Downtime row {0}").format(row.idx)))
	_check_no_overlap(intervals)
	_check_other_entries(doc, intervals)
	_check_production(doc)
	_check_downtime(doc)
	_check_tool_changes(doc, shift, window, grace)
	_check_consumables(doc)
	_set_totals(doc, shift)


def _set_defaults(doc):
	if not doc.company:
		doc.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
	doc.workstation_type = frappe.db.get_value("Workstation", doc.workstation, "workstation_type")
	doc.operator_name = frappe.db.get_value(OPERATOR, doc.operator, "operator_name")
	doc.title = f"{doc.workstation} · {doc.shift} · {doc.posting_date}"


def _check_header(doc):
	if getdate(doc.posting_date) > getdate(today()):
		frappe.throw(_("The shift date {0} is in the future.").format(doc.posting_date))

	shift = frappe.db.get_value(
		SHIFT, doc.shift, ["name", "start_time", "end_time", "planned_minutes", "is_active"], as_dict=True
	)
	if not shift:
		frappe.throw(_("Shift {0} not found.").format(doc.shift))
	if not cint(shift.is_active):
		frappe.throw(_("Shift {0} is inactive.").format(doc.shift))

	if cint(frappe.db.get_value("Workstation", doc.workstation, "disabled")):
		frappe.throw(_("Machine {0} is disabled.").format(doc.workstation))

	if frappe.db.get_value(OPERATOR, doc.operator, "status") != "Active":
		frappe.throw(_("Operator {0} is inactive and cannot enter shift production.").format(doc.operator))

	same = frappe.db.get_value(
		DOCTYPE,
		{
			"posting_date": doc.posting_date,
			"shift": doc.shift,
			"workstation": doc.workstation,
			"operator": doc.operator,
			"docstatus": ["<", 2],
			"name": ["!=", doc.name or ""],
		},
		"name",
	)
	if same:
		frappe.throw(
			_("{0} already has an entry for {1}, {2} shift on {3}: {4}. Open that entry instead.").format(
				doc.operator, doc.workstation, doc.shift, doc.posting_date, same
			)
		)
	return shift


def _set_times(doc, shift, window, grace, row, label):
	if not row.from_time or not row.to_time:
		frappe.throw(_("{0}: From and To times are required.").format(label))
	start = time_in_shift(doc.posting_date, shift, row.from_time, grace)
	end = time_in_shift(doc.posting_date, shift, row.to_time, grace)
	if end <= start:
		frappe.throw(_("{0}: To time must be after From time.").format(label))
	_check_inside(window, grace, start, end, label)
	row.from_datetime, row.to_datetime = start, end
	row.minutes = _minutes(start, end)


def _check_inside(window, grace, start, end, label):
	earliest = window[0] - timedelta(minutes=grace)
	latest = window[1] + timedelta(minutes=grace)
	if start < earliest or end > latest:
		frappe.throw(
			_("{0} ({1}-{2}) is outside the shift ({3}-{4}, {5} minutes allowed before and after).").format(
				label, _clock(start), _clock(end), _clock(window[0]), _clock(window[1]), grace
			)
		)


def _check_no_overlap(intervals):
	"""A machine cannot be producing and stopped, or on two blocks, at the same time."""
	ordered = sorted(intervals, key=lambda x: get_datetime(x[0]))
	latest = None
	for start, end, label in ordered:
		if latest and get_datetime(start) < get_datetime(latest[1]):
			frappe.throw(
				_("{0} ({1}-{2}) overlaps {3} ({4}-{5}).").format(
					label, _clock(start), _clock(end), latest[2], _clock(latest[0]), _clock(latest[1])
				)
			)
		if not latest or get_datetime(end) > get_datetime(latest[1]):
			latest = (start, end, label)


def _check_other_entries(doc, intervals):
	"""No other entry (any operator, draft or submitted) may cover the same minutes on this machine."""
	if not intervals:
		return
	low = min(get_datetime(i[0]) for i in intervals)
	high = max(get_datetime(i[1]) for i in intervals)
	others = []
	for table in (PRODUCTION_ROW, DOWNTIME_ROW):
		others += frappe.db.sql(
			f"""
			select r.parent, r.from_datetime, r.to_datetime
			from `tab{table}` r
			join `tab{DOCTYPE}` s on s.name = r.parent
			where s.workstation = %(workstation)s and s.docstatus < 2 and s.name != %(name)s
				and r.from_datetime < %(high)s and r.to_datetime > %(low)s
			""",
			{"workstation": doc.workstation, "name": doc.name or "", "low": low, "high": high},
			as_dict=True,
		)
	for start, end, label in intervals:
		for other in others:
			if get_datetime(other.from_datetime) < get_datetime(end) and get_datetime(
				other.to_datetime
			) > get_datetime(start):
				frappe.throw(
					_("{0} ({1}-{2}) overlaps entry {3} on the same machine ({4}-{5}).").format(
						label,
						_clock(start),
						_clock(end),
						other.parent,
						_clock(other.from_datetime),
						_clock(other.to_datetime),
					)
				)


def _overproduction_percent():
	return flt(
		frappe.db.get_single_value("Manufacturing Settings", "overproduction_percentage_for_work_order")
	)


def job_card_qty_done(job_card, exclude_spr=None):
	"""Good quantity already logged on the Job Card, leaving out the logs of one SPR."""
	return flt(
		frappe.db.sql(
			f"""
			select sum(completed_qty) from `tabJob Card Time Log`
			where parent = %(card)s and parenttype = 'Job Card' and parentfield = 'time_logs'
				and ifnull({LOG_SPR_FIELD}, '') != %(spr)s
			""",
			{"card": job_card, "spr": exclude_spr or ""},
		)[0][0]
	)


def _check_production(doc):
	by_card = {}
	for row in doc.get("production") or []:
		label = _("Production row {0}").format(row.idx)
		if not row.job_card:
			frappe.throw(_("{0}: pick the Job Card the machine worked on.").format(label))
		card = frappe.db.get_value(
			"Job Card",
			row.job_card,
			["docstatus", "workstation", "for_quantity", "work_order", "production_item", "operation"],
			as_dict=True,
		)
		if not card:
			frappe.throw(_("{0}: Job Card {1} not found.").format(label, row.job_card))
		if card.docstatus != 0 and doc.docstatus == 0:
			frappe.throw(
				_("{0}: Job Card {1} is already submitted or cancelled. Pick an open Job Card.").format(
					label, row.job_card
				)
			)
		if card.workstation != doc.workstation:
			frappe.throw(
				_("{0}: Job Card {1} is for machine {2}, not {3}.").format(
					label, row.job_card, card.workstation or "-", doc.workstation
				)
			)
		row.work_order, row.production_item, row.operation = (
			card.work_order,
			card.production_item,
			card.operation,
		)
		if flt(row.good_qty) < 0 or flt(row.rejected_qty) < 0:
			frappe.throw(_("{0}: quantities cannot be negative.").format(label))
		if flt(row.rejected_qty) > 0 and not (row.rejection_reason or "").strip():
			frappe.throw(_("{0}: give the reason for the {1} rejected.").format(label, flt(row.rejected_qty)))
		by_card.setdefault(row.job_card, [card, 0.0])[1] += flt(row.good_qty)

	extra = _overproduction_percent()
	for name, (card, good) in by_card.items():
		done = job_card_qty_done(name, doc.name)
		allowed = flt(card.for_quantity) * (1 + extra / 100)
		if done + good > allowed + 1e-9:
			frappe.throw(
				_(
					"Job Card {0}: {1} already done + {2} in this entry = {3}, more than the {4} to make."
				).format(name, done, good, done + good, flt(card.for_quantity))
			)


def _check_downtime(doc):
	for row in doc.get("downtime") or []:
		category = frappe.db.get_value(
			DOWNTIME, row.downtime_category, ["stop_type", "is_breakdown", "is_active"], as_dict=True
		)
		if not category:
			frappe.throw(
				_("Downtime row {0}: category {1} not found.").format(row.idx, row.downtime_category)
			)
		if not cint(category.is_active):
			frappe.throw(
				_("Downtime row {0}: category {1} is inactive.").format(row.idx, row.downtime_category)
			)
		row.stop_type, row.is_breakdown = category.stop_type, cint(category.is_breakdown)


def _check_tool_changes(doc, shift, window, grace):
	for row in doc.get("tool_changes") or []:
		label = _("Tool change row {0}").format(row.idx)
		if not row.change_time:
			frappe.throw(_("{0}: the time of the change is required.").format(label))
		at = time_in_shift(doc.posting_date, shift, row.change_time, grace)
		_check_inside(window, grace, at, at, label)
		row.change_datetime = at
		if not (row.tool_item or (row.tool_description or "").strip()):
			frappe.throw(_("{0}: say which tool was changed.").format(label))


def consumables_store(company, item_code, item_group):
	"""Where a consumable is issued from: the item's own default store, else its group's, else Consumables Stores."""
	for parent, parenttype in ((item_code, "Item"), (item_group, "Item Group")):
		store = frappe.db.get_value(
			"Item Default",
			{"parent": parent, "parenttype": parenttype, "company": company},
			"default_warehouse",
		)
		if store:
			return store
	return frappe.db.get_value(
		"Warehouse",
		{
			"company": company,
			"warehouse_name": stock_tree.default_store_for(stock_tree.CONSUMABLES),
			"is_group": 0,
		},
		"name",
	)


def _check_consumables(doc):
	for row in doc.get("consumables") or []:
		label = _("Consumables row {0}").format(row.idx)
		item = frappe.db.get_value(
			"Item",
			row.item_code,
			["item_group", "stock_uom", "is_stock_item", "disabled", "item_name"],
			as_dict=True,
		)
		if not item:
			frappe.throw(_("{0}: item {1} not found.").format(label, row.item_code))
		if stock_tree.stock_class_of(item.item_group) != stock_tree.CONSUMABLES or not cint(
			item.is_stock_item
		):
			frappe.throw(
				_("{0}: {1} is not a Consumables stock item (its group is {2}).").format(
					label, row.item_code, item.item_group
				)
			)
		if flt(row.qty) <= 0:
			frappe.throw(_("{0}: quantity must be more than 0.").format(label))
		row.uom, row.item_name = item.stock_uom, item.item_name
		if not row.warehouse:
			row.warehouse = consumables_store(doc.company, row.item_code, item.item_group)


def _set_totals(doc, shift):
	doc.planned_minutes = cint(shift.planned_minutes)
	doc.production_minutes = sum(cint(r.minutes) for r in doc.get("production") or [])
	doc.downtime_minutes = sum(cint(r.minutes) for r in doc.get("downtime") or [])
	doc.unaccounted_minutes = max(doc.planned_minutes - doc.production_minutes - doc.downtime_minutes, 0)
	doc.total_good_qty = sum(flt(r.good_qty) for r in doc.get("production") or [])
	doc.total_rejected_qty = sum(flt(r.rejected_qty) for r in doc.get("production") or [])
	made = doc.total_good_qty + doc.total_rejected_qty
	doc.rejection_percent = flt(doc.total_rejected_qty / made * 100, 2) if made else 0


# Submit / cancel ---------------------------------------------------------------------------------------


def unaccounted_limit():
	return max(params.get_int(UNACCOUNTED_FIELD, 15), 0)


def tool_photo_required():
	return params.is_enabled(PHOTO_FIELD, 1)


def missing_photos(doc):
	return [row.idx for row in doc.get("tool_changes") or [] if not row.photo]


def before_submit(doc):
	limit = unaccounted_limit()
	if cint(doc.unaccounted_minutes) > limit:
		frappe.throw(
			_(
				"{0} minutes of the shift are not explained (allowed: {1}). Add the production or downtime rows "
				"for that time - for example 'No Plan / No Load' if the machine had no work."
			).format(doc.unaccounted_minutes, limit)
		)
	if tool_photo_required():
		rows = missing_photos(doc)
		if rows:
			frappe.throw(
				_("Attach the photo of the changed tool in tool change row(s) {0}.").format(
					", ".join(str(i) for i in rows)
				)
			)
	skill.check_on_submit(doc)  # C3a-X7: Soft Block needs a reason


def on_submit(doc):
	post_to_job_cards(doc)
	issue_consumables(doc)


def before_cancel(doc):
	for name in sorted({row.job_card for row in doc.get("production") or [] if row.job_card}):
		if frappe.db.get_value("Job Card", name, "docstatus") != 0:
			frappe.throw(
				_(
					"Job Card {0} is already submitted, so the time logs from this entry cannot be taken back. "
					"Cancel or amend the Job Card first."
				).format(name)
			)


def on_cancel(doc):
	remove_from_job_cards(doc)
	cancel_consumables(doc)


def _save_job_card(card, action):
	card.flags.ignore_permissions = True
	try:
		card.save()
	except frappe.ValidationError as e:
		frappe.throw(_("Job Card {0} refused {1}: {2}").format(card.name, action, strip_html(str(e))))


def post_to_job_cards(doc):
	by_card = {}
	for row in doc.get("production") or []:
		by_card.setdefault(row.job_card, []).append(row)
	for name, rows in by_card.items():
		card = frappe.get_doc("Job Card", name)
		for row in rows:
			card.append(
				"time_logs",
				{
					"from_time": row.from_datetime,
					"to_time": row.to_datetime,
					"completed_qty": flt(row.good_qty),
					"operation": card.operation,
					LOG_SPR_FIELD: doc.name,
					LOG_ROW_FIELD: row.name,
				},
			)
		_save_job_card(card, _("the time blocks of {0}").format(doc.name))


def remove_from_job_cards(doc):
	for name in sorted({row.job_card for row in doc.get("production") or [] if row.job_card}):
		card = frappe.get_doc("Job Card", name)
		keep = [log for log in card.time_logs if log.get(LOG_SPR_FIELD) != doc.name]
		if len(keep) == len(card.time_logs):
			continue
		card.set("time_logs", keep)
		_save_job_card(card, _("removing the time blocks of {0}").format(doc.name))


def issue_consumables(doc):
	rows = doc.get("consumables") or []
	if not rows:
		return None
	machine_group = doc.workstation_type or doc.workstation
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Issue",
			"purpose": "Material Issue",
			"company": doc.company,
			"set_posting_time": 1,
			"posting_date": doc.posting_date,
			STOCK_ENTRY_SPR_FIELD: doc.name,
			"remarks": _("Consumables used on {0}, {1} shift, {2} (Shift Production Entry {3}).").format(
				doc.workstation, doc.shift, doc.posting_date, doc.name
			),
			"items": [
				{
					"item_code": row.item_code,
					"qty": flt(row.qty),
					"s_warehouse": row.warehouse,
					"custom_machine_group": machine_group,
				}
				for row in rows
			],
		}
	)
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	doc.db_set("consumables_stock_entry", entry.name)
	return entry.name


def cancel_consumables(doc):
	if not doc.consumables_stock_entry:
		return
	entry = frappe.get_doc("Stock Entry", doc.consumables_stock_entry)
	if entry.docstatus == 1:
		entry.flags.ignore_permissions = True
		entry.cancel()


# Panel -------------------------------------------------------------------------------------------------


@frappe.whitelist()
def get_spr_panel(name):
	"""Rows for the SPR form panel: shift minutes, what is explained, output, photos, postings."""
	frappe.has_permission(DOCTYPE, "read", name, throw=True)
	doc = frappe.get_doc(DOCTYPE, name)
	start = frappe.db.get_value(SHIFT, doc.shift, ["start_time", "end_time"], as_dict=True) or {}
	rows = []
	if start:
		window = shift_window(doc.posting_date, frappe._dict(start))
		rows.append(
			{
				"text": _("{0} shift {1}-{2}: {3} planned minutes").format(
					doc.shift, _clock(window[0]), _clock(window[1]), cint(doc.planned_minutes)
				),
				"colour": "gray",
			}
		)
	limit = unaccounted_limit()
	explained = _("Production {0} min · Downtime {1} min").format(
		cint(doc.production_minutes), cint(doc.downtime_minutes)
	)
	if cint(doc.unaccounted_minutes) > limit:
		rows.append(
			{
				"text": explained
				+ " · "
				+ _("{0} minutes not explained (allowed {1})").format(doc.unaccounted_minutes, limit),
				"colour": "red",
			}
		)
	else:
		rows.append({"text": explained + " · " + _("every minute explained"), "colour": "green"})
	rows.append(skill.panel_row(doc))  # C3a-X7

	made = flt(doc.total_good_qty) + flt(doc.total_rejected_qty)
	if made:
		rows.append(
			{
				"text": _("Good {0} · Rejected {1} ({2}%)").format(
					flt(doc.total_good_qty), flt(doc.total_rejected_qty), flt(doc.rejection_percent)
				),
				"colour": "orange" if flt(doc.total_rejected_qty) else "green",
			}
		)
	breakdowns = [r for r in doc.downtime if cint(r.is_breakdown)]
	if breakdowns:
		rows.append(
			{
				"text": _("{0} breakdown stop(s), {1} min").format(
					len(breakdowns), sum(cint(r.minutes) for r in breakdowns)
				),
				"colour": "red",
			}
		)
	if tool_photo_required() and missing_photos(doc):
		rows.append(
			{
				"text": _("Tool change photo missing in row(s) {0}").format(
					", ".join(str(i) for i in missing_photos(doc))
				),
				"colour": "red",
			}
		)
	if doc.docstatus == 1:
		cards = sorted({r.job_card for r in doc.production if r.job_card})
		if cards:
			rows.append(
				{"text": _("Time logged on Job Card {0}").format(", ".join(cards)), "colour": "green"}
			)
		if doc.consumables_stock_entry:
			rows.append(
				{"text": _("Consumables issued: {0}").format(doc.consumables_stock_entry), "colour": "green"}
			)
	return {"rows": rows}
