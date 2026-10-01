"""C2-20 - Cycle count by ABC class.

* classify_abc (monthly): stock items ranked by 12-month consumption value. A = the items
  making up the top "Class A: Share of Value" %, B = the next "Class B" %, C = the rest.
* PEPL Cycle Count: "Generate count sheet" adds every item (and batch, for heat batches)
  in the store that is due - never counted, or last counted at least its class frequency
  ago. The book qty is captured then but hidden from the counter (permission level 1).
* validate: each non-zero variance needs a reason. When the variance value is above
  "Count Variance Needing Approval" % of the counted book value, only the Stores HOD
  (Stock Manager) can submit; a ToDo goes to the Stores owner.
* on_submit: one standard Stock Reconciliation for the variance rows only (current book
  qty + variance, so movements after the sheet was made are kept); every counted item
  gets Last Counted On.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today

from pepl_os.common import params
from pepl_os.common.alerts import close_resolved, raise_todo
from pepl_os.common.jobs import tracked_job

COUNT = "PEPL Cycle Count"
COUNT_ITEM = "PEPL Cycle Count Item"
CLASS_FIELD = "custom_abc_class"
COUNTED_FIELD = "custom_last_counted_on"
HOD_ROLES = ("Stock Manager", "System Manager")
APPROVAL_RULE = "STO-COUNT-APPROVAL"
STORES_OWNER = "custom_stores_notification_owner"
REASONS = ("Wrong issue entry", "Unrecorded receipt", "Damage", "Measurement", "Suspected loss", "Other")
CONSUMING = ("Material Issue", "Manufacture", "Material Consumption for Manufacture")
TRANSFERS = ("Material Transfer", "Material Transfer for Manufacture")


def frequency_days(abc_class):
	return {
		"A": params.get_int("custom_count_frequency_a_days", 30) or 30,
		"B": params.get_int("custom_count_frequency_b_days", 90) or 90,
	}.get(abc_class, params.get_int("custom_count_frequency_c_days", 180) or 180)


# ABC classification ---------------------------------------------------------------------


def consumption_values(as_of=None, days=365):
	"""{item: value consumed} over the period: issues, manufacture, transfers into WIP and dispatches."""
	as_of = getdate(as_of or today())
	start = add_days(as_of, -(days - 1))
	from pepl_os.pepl_stores.reorder import _wip_stores

	wip = _wip_stores()
	rows = frappe.db.sql(
		"""select sle.item_code, -sle.stock_value_difference as value, sle.voucher_type, se.purpose, sed.t_warehouse
		from `tabStock Ledger Entry` sle
		left join `tabStock Entry` se on sle.voucher_type = 'Stock Entry' and se.name = sle.voucher_no
		left join `tabStock Entry Detail` sed on sle.voucher_type = 'Stock Entry' and sed.name = sle.voucher_detail_no
		where sle.is_cancelled = 0 and sle.actual_qty < 0 and sle.posting_date between %s and %s
			and sle.voucher_type in ('Stock Entry', 'Delivery Note', 'Sales Invoice')""",
		(start, as_of),
		as_dict=True,
	)
	values = {}
	for r in rows:
		if r.voucher_type == "Stock Entry":
			if r.purpose in TRANSFERS:
				if r.t_warehouse not in wip:
					continue
			elif r.purpose not in CONSUMING:
				continue
		values[r.item_code] = values.get(r.item_code, 0.0) + flt(r.value)
	return values


def abc_split(values, a_percent, b_percent):
	"""{item: 'A'|'B'|'C'} - an item is A while the value before it is under a%, B while under a+b%."""
	total = sum(v for v in values.values() if v > 0)
	result = {}
	running = 0.0
	for item, value in sorted(values.items(), key=lambda kv: (-kv[1], kv[0])):
		if value <= 0 or not total:
			result[item] = "C"
			continue
		share_before = running / total * 100
		result[item] = (
			"A" if share_before < a_percent else ("B" if share_before < a_percent + b_percent else "C")
		)
		running += value
	return result


def classify_abc(as_of=None):
	a = flt(params.get_float("custom_abc_a_value_percent", 80)) or 80
	b = flt(params.get_float("custom_abc_b_value_percent", 15)) or 15
	values = consumption_values(as_of)
	items = frappe.get_all(
		"Item", filters={"is_stock_item": 1, "disabled": 0, "has_variants": 0}, pluck="name"
	)
	split = abc_split({i: values.get(i, 0.0) for i in items}, a, b)
	changed = 0
	for item, cls in split.items():
		if frappe.get_cached_value("Item", item, CLASS_FIELD) != cls:
			frappe.db.set_value("Item", item, CLASS_FIELD, cls, update_modified=False)
			changed += 1
	return {"records_touched": changed, "message": f"{len(split)} items classed, {changed} changed"}


@tracked_job("Monthly ABC classification")
def monthly_classify_abc():
	return classify_abc()


@frappe.whitelist()
def classify_abc_now():
	frappe.only_for(HOD_ROLES)
	return classify_abc()


# Count sheet ------------------------------------------------------------------------------


def _batches(item_code, warehouse):
	rows = frappe.db.sql(
		"""select sbe.batch_no, sum(sbe.qty) as qty
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		where sbb.item_code = %s and sbb.warehouse = %s and sbb.docstatus = 1 and sbb.is_cancelled = 0
			and ifnull(sbe.batch_no, '') != ''
		group by sbe.batch_no having sum(sbe.qty) != 0""",
		(item_code, warehouse),
		as_dict=True,
	)
	return [(r.batch_no, flt(r.qty)) for r in rows]


def due_items(warehouse, count_date):
	"""[(item, abc class, last counted, book qty, valuation rate)] in this store, due for counting."""
	count_date = getdate(count_date)
	bins = frappe.get_all(
		"Bin",
		filters={"warehouse": warehouse, "actual_qty": ["!=", 0]},
		fields=["item_code", "actual_qty", "valuation_rate"],
		order_by="item_code",
	)
	due = []
	for b in bins:
		cls, last, disabled = frappe.get_cached_value(
			"Item", b.item_code, [CLASS_FIELD, COUNTED_FIELD, "disabled"]
		)
		if disabled:
			continue
		cls = cls or "C"
		if last and add_days(getdate(last), frequency_days(cls)) > count_date:
			continue
		due.append((b.item_code, cls, last, flt(b.actual_qty), flt(b.valuation_rate)))
	return due


@frappe.whitelist()
def generate_count_sheet(name):
	doc = frappe.get_doc(COUNT, name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft count can get a new sheet."))
	doc.set("items", [])
	for item_code, cls, last, qty, rate in due_items(doc.warehouse, doc.count_date):
		lines = [(None, qty)]
		if cint(frappe.get_cached_value("Item", item_code, "has_batch_no")):
			lines = _batches(item_code, doc.warehouse) or lines
		for batch, book in lines:
			doc.append(
				"items",
				{
					"item_code": item_code,
					"batch_no": batch,
					"abc_class": cls,
					"last_counted_on": last,
					"system_qty": book,
					"valuation_rate": rate,
				},
			)
	doc.sheet_generated_on = now_datetime()
	doc.flags.ignore_permissions = True  # the counter may not write the hidden book qty
	doc.save()
	return len(doc.items)


# Validate / submit ---------------------------------------------------------------------------


def validate_count(doc):
	if not doc.counted_by:
		doc.counted_by = frappe.session.user
	missing_reason = []
	book_value = variance_value = 0.0
	for row in doc.items:
		if flt(row.counted_qty) != 0:
			row.counted = 1  # a counted qty of zero (nothing found) is confirmed by ticking Counted
		row.variance_qty = flt(row.counted_qty) - flt(row.system_qty) if row.counted else 0
		row.variance_value = flt(row.variance_qty) * flt(row.valuation_rate)
		if row.counted and abs(flt(row.variance_qty)) > 1e-9 and not row.reason:
			missing_reason.append(row)
		book_value += abs(flt(row.system_qty) * flt(row.valuation_rate))
		variance_value += abs(row.variance_value)
	doc.variance_value = variance_value
	doc.variance_percent = (
		(variance_value / book_value * 100) if book_value else (100 if variance_value else 0)
	)
	limit = flt(params.get_float("custom_count_variance_approval_percent", 0))
	doc.needs_hod_approval = 1 if limit and doc.variance_percent > limit else 0
	if missing_reason:
		frappe.throw(
			_("Give a reason for every line that differs from the book stock: {0}").format(
				", ".join(f"row {r.idx} {r.item_code}" for r in missing_reason)
			),
			title=_("Reason required"),
		)


def on_update_count(doc):
	if doc.docstatus == 0 and doc.needs_hod_approval:
		raise_todo(
			APPROVAL_RULE,
			COUNT,
			doc.name,
			_(
				"Cycle count {0} ({1}): variance {2}% of book value is above the limit. Review and submit."
			).format(doc.name, doc.warehouse, flt(doc.variance_percent, 2)),
			owner_field=STORES_OWNER,
			priority="High",
		)
	sync_approval_todos()


def sync_approval_todos():
	active = frappe.get_all(COUNT, filters={"docstatus": 0, "needs_hod_approval": 1}, pluck="name")
	close_resolved(APPROVAL_RULE, COUNT, active)


def before_submit_count(doc):
	if not doc.items:
		frappe.throw(_("Generate the count sheet first."))
	uncounted = [r for r in doc.items if not r.counted]
	if uncounted:
		frappe.throw(
			_("Enter the counted qty on every line (tick Counted): {0}").format(
				", ".join(f"row {r.idx} {r.item_code}" for r in uncounted[:20])
			)
		)
	if doc.needs_hod_approval:
		if not set(HOD_ROLES) & set(frappe.get_roles()):
			frappe.throw(
				_(
					"The variance ({0}% of book value) is above the approval limit. The Stores HOD must submit this count."
				).format(flt(doc.variance_percent, 2)),
				title=_("Stores HOD approval"),
			)
		doc.approved_by = frappe.session.user


def _book_qty(item_code, warehouse, batch_no=None):
	if batch_no:
		for batch, qty in _batches(item_code, warehouse):
			if batch == batch_no:
				return qty
		return 0.0
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


def on_submit_count(doc):
	rows = [r for r in doc.items if abs(flt(r.variance_qty)) > 1e-9]
	if rows:
		reco = frappe.get_doc(
			{
				"doctype": "Stock Reconciliation",
				"purpose": "Stock Reconciliation",
				"company": doc.company,
				"posting_date": today(),
				"items": [
					{
						"item_code": r.item_code,
						"warehouse": doc.warehouse,
						"qty": max(
							0.0, _book_qty(r.item_code, doc.warehouse, r.batch_no) + flt(r.variance_qty)
						),
						"valuation_rate": flt(r.valuation_rate) or None,
						"batch_no": r.batch_no,
						"use_serial_batch_fields": 1 if r.batch_no else 0,
					}
					for r in rows
				],
			}
		)
		reco.flags.ignore_permissions = True
		reco.insert()
		reco.submit()
		doc.db_set("stock_reconciliation", reco.name)
	for item_code in {r.item_code for r in doc.items}:
		frappe.db.set_value("Item", item_code, COUNTED_FIELD, doc.count_date, update_modified=False)
	sync_approval_todos()


def on_cancel_count(doc):
	if (
		doc.stock_reconciliation
		and frappe.db.get_value("Stock Reconciliation", doc.stock_reconciliation, "docstatus") == 1
	):
		reco = frappe.get_doc("Stock Reconciliation", doc.stock_reconciliation)
		reco.flags.ignore_permissions = True
		reco.cancel()


# Variance log ---------------------------------------------------------------------------


def variance_log(filters=None):
	filters = frappe._dict(filters or {})
	conditions = ["c.docstatus = 1", "abs(i.variance_qty) > 0"]
	values = {}
	for key, column in (("company", "c.company"), ("warehouse", "c.warehouse"), ("reason", "i.reason")):
		if filters.get(key):
			conditions.append(f"{column} = %({key})s")
			values[key] = filters[key]
	if filters.get("from_date"):
		conditions.append("c.count_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("c.count_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	return frappe.db.sql(
		f"""select c.warehouse, i.reason, date_format(c.count_date, '%%Y-%%m') as month,
			count(*) as lines, sum(i.variance_qty) as variance_qty, sum(i.variance_value) as variance_value,
			group_concat(distinct i.item_code separator ', ') as items
		from `tabPEPL Cycle Count Item` i join `tabPEPL Cycle Count` c on c.name = i.parent
		where {" and ".join(conditions)}
		group by c.warehouse, i.reason, month
		order by month desc, c.warehouse, i.reason""",
		values,
		as_dict=True,
	)
