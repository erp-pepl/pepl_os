"""C2-15 - Heat Number Trace: from receipt to issue, Work Order and dispatch (the recall view).

Sources, all live:
  1. PEPL Receipt Log rows with the heat number (the receipt).
  2. The Batches carrying the heat number, and every submitted stock movement of
     those Batches (Serial and Batch Bundle entries): issues, transfers,
     manufacture, deliveries.
  3. Stock Entry lines that name the heat number in the heat field (items that
     keep the heat in a field instead of a Batch).
  4. The Work Orders those Stock Entries belong to, and the Delivery Notes of
     each Work Order's Sales Order for the item it made.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

HEAT_FIELD = "custom_heat_number"


def _row(stage, posting_date, voucher_type, voucher_no, **extra):
	return frappe._dict(
		stage=stage, posting_date=posting_date, voucher_type=voucher_type, voucher_no=voucher_no, **extra
	)


def _stock_entry_stage(purpose, qty):
	if purpose in ("Manufacture", "Repack"):
		return _("Production")
	if flt(qty) > 0 or purpose in ("Material Receipt",):
		return _("Receipt")
	if purpose in ("Material Transfer", "Material Transfer for Manufacture", "Send to Subcontractor"):
		return _("Issue / Transfer")
	return _("Issue")


def heat_trace(heat):
	heat = (heat or "").strip()
	if not heat:
		return []
	out, seen = [], set()

	for r in frappe.get_all(
		"PEPL Receipt Log",
		filters={"heat_number": heat, "status": "Active"},
		fields=[
			"purchase_receipt",
			"received_on",
			"item_code",
			"qty",
			"warehouse",
			"batch_no",
			"supplier_name",
		],
	):
		out.append(
			_row(
				_("Receipt"),
				getdate(r.received_on),
				"Purchase Receipt",
				r.purchase_receipt,
				purpose=_("Goods inward"),
				item_code=r.item_code,
				qty=r.qty,
				warehouse=r.warehouse,
				batch_no=r.batch_no,
				party=r.supplier_name,
			)
		)
		seen.add(("Purchase Receipt", r.purchase_receipt, r.item_code))

	batches = frappe.get_all("Batch", filters={HEAT_FIELD: heat}, pluck="name")
	stock_entries = set()
	if batches:
		movements = frappe.db.sql(
			"""
			select b.voucher_type, b.voucher_no, b.posting_datetime, b.item_code, b.warehouse,
				e.batch_no, e.qty
			from `tabSerial and Batch Entry` e
			join `tabSerial and Batch Bundle` b on b.name = e.parent
			where e.batch_no in %(batches)s and b.docstatus = 1 and b.is_cancelled = 0
			order by b.posting_datetime
			""",
			{"batches": batches},
			as_dict=True,
		)
		for m in movements:
			if (
				m.voucher_type == "Purchase Receipt"
				and ("Purchase Receipt", m.voucher_no, m.item_code) in seen
			):
				continue
			extra = {"item_code": m.item_code, "qty": m.qty, "warehouse": m.warehouse, "batch_no": m.batch_no}
			if m.voucher_type == "Stock Entry":
				se = (
					frappe.db.get_value("Stock Entry", m.voucher_no, ["purpose", "work_order"], as_dict=True)
					or {}
				)
				stock_entries.add(m.voucher_no)
				out.append(
					_row(
						_stock_entry_stage(se.get("purpose"), m.qty),
						getdate(m.posting_datetime),
						"Stock Entry",
						m.voucher_no,
						purpose=se.get("purpose"),
						work_order=se.get("work_order"),
						**extra,
					)
				)
			elif m.voucher_type == "Delivery Note":
				customer = frappe.db.get_value("Delivery Note", m.voucher_no, "customer_name")
				out.append(
					_row(
						_("Dispatch"),
						getdate(m.posting_datetime),
						"Delivery Note",
						m.voucher_no,
						purpose=_("Delivery"),
						party=customer,
						**extra,
					)
				)
			else:
				out.append(
					_row(_("Movement"), getdate(m.posting_datetime), m.voucher_type, m.voucher_no, **extra)
				)

	for r in frappe.db.sql(
		"""
		select se.name, se.posting_date, se.purpose, se.work_order, d.item_code, d.qty,
			d.s_warehouse, d.t_warehouse, d.batch_no
		from `tabStock Entry Detail` d
		join `tabStock Entry` se on se.name = d.parent
		where d.custom_heat_number = %s and se.docstatus = 1
		""",
		heat,
		as_dict=True,
	):
		if r.name in stock_entries:
			continue
		stock_entries.add(r.name)
		qty = flt(r.qty) if r.t_warehouse and not r.s_warehouse else -flt(r.qty)
		out.append(
			_row(
				_stock_entry_stage(r.purpose, qty),
				getdate(r.posting_date),
				"Stock Entry",
				r.name,
				purpose=r.purpose,
				work_order=r.work_order,
				item_code=r.item_code,
				qty=qty,
				warehouse=r.s_warehouse or r.t_warehouse,
				batch_no=r.batch_no,
			)
		)

	work_orders = sorted({r.work_order for r in out if r.get("work_order")})
	for name in work_orders:
		wo = frappe.db.get_value(
			"Work Order",
			name,
			["production_item", "qty", "sales_order", "planned_start_date", "fg_warehouse"],
			as_dict=True,
		)
		if not wo:
			continue
		out.append(
			_row(
				_("Work Order"),
				getdate(wo.planned_start_date) if wo.planned_start_date else None,
				"Work Order",
				name,
				purpose=_("Makes {0}").format(wo.production_item),
				item_code=wo.production_item,
				qty=wo.qty,
				warehouse=wo.fg_warehouse,
				work_order=name,
			)
		)
		if not wo.sales_order:
			continue
		for dn in frappe.db.sql(
			"""
			select dn.name, dn.posting_date, dn.customer_name, i.qty, i.warehouse
			from `tabDelivery Note Item` i
			join `tabDelivery Note` dn on dn.name = i.parent
			where dn.docstatus = 1 and i.against_sales_order = %s and i.item_code = %s
			""",
			(wo.sales_order, wo.production_item),
			as_dict=True,
		):
			out.append(
				_row(
					_("Dispatch"),
					getdate(dn.posting_date),
					"Delivery Note",
					dn.name,
					purpose=_("Delivery against {0} (via {1})").format(wo.sales_order, name),
					item_code=wo.production_item,
					qty=dn.qty,
					warehouse=dn.warehouse,
					party=dn.customer_name,
					work_order=name,
				)
			)

	order = {
		_("Receipt"): 0,
		_("Issue / Transfer"): 1,
		_("Issue"): 1,
		_("Work Order"): 2,
		_("Production"): 3,
		_("Dispatch"): 4,
	}
	out.sort(key=lambda r: (r.posting_date or getdate("1900-01-01"), order.get(r.stage, 5)))
	return out
