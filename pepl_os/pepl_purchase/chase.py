"""C2-13 - Daily chase list, the vendor chase letter, the PUR-CHASE ToDos and Open PO Ageing.

Everything reads the Purchase Tracker lines (C2-12), so it is always as fresh
as the last recompute (on every PO or receipt change, every morning, and
"Refresh now").
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, now_datetime, today

from pepl_os.common import alerts
from pepl_os.pepl_purchase import tracker as trk

CHASE_STATUSES = (trk.OVERDUE, trk.DUE_TODAY, trk.DUE_SOON)
CRITICALITY_ORDER = {"Critical": 0, "Important": 1, "Routine": 2}
CHASE_RULE = "PUR-CHASE"
LETTER_FORMAT = "PEPL Vendor Chase Letter"
OPEN_TRACKER = ["not in", [trk.COMPLETED, trk.CANCELLED]]


def criticality_rank(value):
	return CRITICALITY_ORDER.get(value or "", 3)


def open_lines(statuses=None, supplier=None, company=None, buyer=None):
	"""Open tracker lines (pending > 0), with their tracker and supplier details."""
	filters = {"status": OPEN_TRACKER}
	for field, value in (("supplier", supplier), ("company", company), ("buyer", buyer)):
		if value:
			filters[field] = value
	trackers = {
		t.name: t
		for t in frappe.get_all(
			trk.DOCTYPE,
			filters=filters,
			fields=[
				"name",
				"purchase_order",
				"supplier",
				"supplier_name",
				"vendor_criticality",
				"buyer",
				"company",
				"last_chased_on",
				"chase_count",
				"vendor_revised_date",
			],
		)
	}
	if not trackers:
		return []
	line_filters = {"parent": ["in", list(trackers)], "parenttype": trk.DOCTYPE, "pending_qty": [">", 0]}
	if statuses:
		line_filters["line_status"] = ["in", list(statuses)]
	lines = frappe.get_all(
		"PEPL Purchase Tracker Line",
		filters=line_filters,
		fields=[
			"parent",
			"po_item",
			"item_code",
			"item_name",
			"pending_qty",
			"uom",
			"promised_date",
			"revised_date",
			"days_overdue",
			"line_status",
		],
	)
	out = []
	for line in lines:
		t = trackers[line.parent]
		out.append(frappe._dict({**t, **line, "tracker": t.name}))
	return out


def _contact(supplier):
	s = (
		frappe.db.get_value(
			"Supplier", supplier, ["mobile_no", "email_id", "supplier_primary_contact"], as_dict=True
		)
		or frappe._dict()
	)
	email, phone = s.email_id, s.mobile_no
	if s.supplier_primary_contact and not (email and phone):
		c = (
			frappe.db.get_value(
				"Contact", s.supplier_primary_contact, ["email_id", "mobile_no", "phone"], as_dict=True
			)
			or frappe._dict()
		)
		email = email or c.email_id
		phone = phone or c.mobile_no or c.phone
	return phone, email


def chase_list(filters=None):
	"""Rows for the chase list: Overdue, Due Today and Due Soon lines.

	Grouped by supplier; suppliers sorted by criticality, then their worst days
	overdue; lines within a supplier by days overdue, then promised date.
	"""
	filters = frappe._dict(filters or {})
	lines = open_lines(CHASE_STATUSES, filters.supplier, filters.company, filters.buyer)
	worst = {}
	for line in lines:
		worst[line.supplier] = max(worst.get(line.supplier, 0), cint(line.days_overdue))
	lines.sort(
		key=lambda r: (
			criticality_rank(r.vendor_criticality),
			-worst[r.supplier],
			r.supplier,
			-cint(r.days_overdue),
			getdate(r.promised_date),
		)
	)
	contacts = {}
	for r in lines:
		if r.supplier not in contacts:
			contacts[r.supplier] = _contact(r.supplier)
		r.phone, r.email = contacts[r.supplier]
	return lines


# The PUR-CHASE ToDos -------------------------------------------------------------


def sync_chase_todos():
	"""One open ToDo per Overdue tracker for the Purchase owner; closed when no longer Overdue."""
	overdue = frappe.get_all(
		trk.DOCTYPE,
		filters={"status": trk.OVERDUE},
		fields=["name", "purchase_order", "supplier_name", "worst_days_overdue", "open_lines"],
	)
	for t in overdue:
		try:
			alerts.raise_todo(
				CHASE_RULE,
				trk.DOCTYPE,
				t.name,
				_("Chase {0}: Purchase Order {1} is {2} day(s) overdue ({3} open line(s)).").format(
					t.supplier_name, t.purchase_order, t.worst_days_overdue, t.open_lines
				),
				owner_field="custom_purchase_notification_owner",
				priority="High",
			)
		except Exception:
			frappe.log_error(title=f"PEPL: chase ToDo not raised for {t.name}")
	alerts.close_resolved(CHASE_RULE, trk.DOCTYPE, [t.name for t in overdue])
	return len(overdue)


@frappe.whitelist()
def refresh_chase_todos():
	"""Run the PUR-CHASE ToDo update now (it also runs every morning after the tracker recompute)."""
	frappe.only_for(("System Manager", "Purchase Manager"))
	return sync_chase_todos()


# The vendor chase letter -----------------------------------------------------------


def pepl_chase_lines(supplier):
	"""Jinja method for the Vendor Chase Letter: every pending line of this supplier, oldest due first."""
	lines = open_lines(supplier=supplier)
	lines.sort(key=lambda r: (getdate(r.promised_date), r.purchase_order))
	return lines


def chase_vendor(supplier, send_email=True):
	"""E-mail the supplier the chase letter (all pending lines) and stamp its trackers. Returns the trackers."""
	lines = open_lines(supplier=supplier)
	if not lines:
		frappe.throw(_("{0} has nothing pending.").format(supplier), title=_("Nothing to chase"))
	_phone, email = _contact(supplier)
	if send_email:
		if not email:
			frappe.throw(
				_(
					"{0} has no e-mail. Add it on the Supplier (or its primary contact), then chase again."
				).format(supplier),
				title=_("No e-mail"),
			)
		from frappe.core.doctype.communication.email import make

		from pepl_os.common.letterhead import file_name, render

		name = frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier
		# C2-24: the chase letter goes as a PDF on the official letterhead
		letter = {
			"fname": file_name(f"Pending-Deliveries-{supplier}"),
			"fcontent": render("Supplier", supplier, LETTER_FORMAT),
		}
		make(
			doctype="Supplier",
			name=supplier,
			recipients=email,
			subject=_("Pending deliveries: {0}").format(name),
			content=_(
				"Dear {0},<br><br>Please find attached the list of items pending delivery against our "
				"Purchase Orders. Kindly confirm the dispatch dates by return.<br><br>Regards"
			).format(frappe.utils.escape_html(name)),
			send_email=True,
			attachments=[letter],
		)
	stamped = []
	for tracker in sorted({line.tracker for line in lines}):
		frappe.db.set_value(
			trk.DOCTYPE,
			tracker,
			{
				"last_chased_on": now_datetime(),
				"chase_count": cint(frappe.db.get_value(trk.DOCTYPE, tracker, "chase_count")) + 1,
			},
			update_modified=False,
		)
		stamped.append(tracker)
	return stamped


@frappe.whitelist()
def chase_vendor_now(supplier=None, tracker=None):
	"""Chase vendor button, on the tracker (pass tracker) or in the chase list (pass supplier)."""
	if tracker and not supplier:
		supplier = frappe.db.get_value(trk.DOCTYPE, tracker, "supplier")
	if not supplier:
		frappe.throw(_("Choose a supplier."))
	frappe.has_permission(trk.DOCTYPE, "write", throw=True)
	stamped = chase_vendor(supplier)
	return {"supplier": supplier, "trackers": stamped}


# Open PO Ageing ------------------------------------------------------------------------

AGE_BUCKETS = ((0, 30, "age_0_30"), (31, 60, "age_31_60"), (61, 90, "age_61_90"), (91, None, "age_90_plus"))
OVERDUE_BUCKETS = (
	(1, 30, "overdue_1_30"),
	(31, 60, "overdue_31_60"),
	(61, 90, "overdue_61_90"),
	(91, None, "overdue_90_plus"),
)


def _bucket(days, buckets):
	for low, high, key in buckets:
		if days >= low and (high is None or days <= high):
			return key
	return None


def open_po_ageing(filters=None):
	"""Open PO value per supplier by age since PO date and by days overdue since the promised date.

	Computed live from the tracker lines and the PO rates at `as_of`, so it never goes stale.
	"""
	filters = frappe._dict(filters or {})
	as_of = getdate(filters.as_of or today())
	lines = open_lines(supplier=filters.supplier, company=filters.company)
	if not lines:
		return []
	po_items = {
		r.name: r
		for r in frappe.get_all(
			"Purchase Order Item",
			filters={"name": ["in", [line.po_item for line in lines]]},
			fields=["name", "parent", "base_net_rate"],
		)
	}
	po_dates = dict(
		frappe.get_all(
			"Purchase Order",
			filters={"name": ["in", list({line.purchase_order for line in lines})]},
			fields=["name", "transaction_date"],
			as_list=True,
		)
	)
	rows = {}
	keys = [k for *_x, k in AGE_BUCKETS] + ["not_overdue"] + [k for *_x, k in OVERDUE_BUCKETS]
	for line in lines:
		item = po_items.get(line.po_item)
		if not item:
			continue
		value = flt(line.pending_qty) * flt(item.base_net_rate)
		row = rows.setdefault(
			line.supplier,
			frappe._dict(
				{
					"supplier": line.supplier,
					"supplier_name": line.supplier_name,
					"vendor_criticality": line.vendor_criticality,
					"open_value": 0.0,
					"orders": set(),
					**{k: 0.0 for k in keys},
				}
			),
		)
		row.open_value += value
		row.orders.add(line.purchase_order)
		age = date_diff(as_of, po_dates.get(line.purchase_order) or as_of)
		row[_bucket(max(age, 0), AGE_BUCKETS)] += value
		late = date_diff(as_of, line.promised_date) if line.promised_date else 0
		row[_bucket(late, OVERDUE_BUCKETS) or "not_overdue"] += value
	out = []
	for row in sorted(
		rows.values(), key=lambda r: (criticality_rank(r.vendor_criticality), -r.open_value, r.supplier)
	):
		row.open_orders = len(row.pop("orders"))
		out.append(row)
	return out
