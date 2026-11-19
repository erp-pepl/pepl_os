"""C3b-B4 - Drawing-revision mid-production alert: a new drawing revision on the Product Master flags every open Job
Order of the item.

* Every Job Order (Work Order) records the drawing revision it is made to: on save, while empty, the item's Product
  Master "Current Drawing Revision" (pepl_sales) is copied into "Drawing Revision".
* When a Product Master's current drawing revision changes (Rev B -> Rev C), every open Job Order of its item (draft
  or submitted, not Completed / Stopped / Closed / Cancelled) made to another revision is flagged: "Drawing Change"
  says Rev B -> Rev C, when, and what changed (the revision's Change Description); the Production Notification Owner
  gets one High ToDo per Job Order (PRD-DRAWING-REV).
* The Job Order shows it in red; a Production or Quality Manager presses "Acknowledge Drawing Change" and records
  what the job is made to from now (the new revision, or finished to the old one with the customer's consent) and
  why. That clears the flag and closes the ToDo; the record stays on the Job Order.
* A shift entry booked on a flagged, unacknowledged Job Order warns the operator's supervisor (it is not stopped).
The first revision ever set (nothing before) flags nothing. A failure never stops the Product Master.
"""

import frappe
from frappe import _
from frappe.utils import cstr, formatdate, getdate, now_datetime

from pepl_os.common import alerts

PRODUCT = "PEPL Product Master"
WO = "Work Order"
RULE = "PRD-DRAWING-REV"
OWNER_FIELD = "custom_production_notification_owner"
REVISION, ALERT, ALERT_ON = "custom_drawing_revision", "custom_drawing_alert", "custom_drawing_alert_on"
DECISION, ACK_BY, ACK_ON = (
	"custom_drawing_decision",
	"custom_drawing_acknowledged_by",
	"custom_drawing_acknowledged_on",
)
CLOSED_STATES = ("Completed", "Stopped", "Closed", "Cancelled")
ACK_ROLES = ("Manufacturing Manager", "PEPL Production Manager", "Quality Manager", "System Manager")


def product_of(item):
	if not item or not frappe.db.exists("DocType", PRODUCT):
		return None
	return frappe.db.get_value(
		PRODUCT,
		{"linked_item": item, "status": ["!=", "Obsolete"]},
		["name", "current_drawing_revision"],
		as_dict=True,
	)


def current_revision(item):
	product = product_of(item)
	return (product.current_drawing_revision or "").strip() if product else ""


def stamp_revision(doc, method=None):
	"""Work Order validate: record the drawing revision the job is made to (once)."""
	if not doc.get(REVISION):
		revision = current_revision(doc.production_item)
		if revision:
			doc.set(REVISION, revision)
	return None


def open_job_orders(item):
	return frappe.get_all(
		WO,
		filters={"production_item": item, "docstatus": ["<", 2], "status": ["not in", CLOSED_STATES]},
		fields=["name", REVISION],
		order_by="creation asc",
	)


def _change_description(doc, revision):
	for row in doc.get("drawing_revisions") or []:
		if cstr(row.revision).strip() == revision:
			return (row.change_description or "").strip()
	return ""


def flag_job_orders(item, old, new, change="", product=None):
	"""Flag the open Job Orders of `item` not made to `new`. Returns their names."""
	flagged = []
	when = now_datetime()
	for wo in open_job_orders(item):
		made = (wo.get(REVISION) or old or "").strip()
		if made == new:
			continue
		text = _("Drawing changed from Rev {0} to Rev {1} on {2}{3}{4}").format(
			made or "-",
			new,
			formatdate(getdate(when)),
			_(" (Product {0})").format(product) if product else "",
			": " + change[:300] if change else "",
		)
		frappe.db.set_value(
			WO,
			wo.name,
			{REVISION: made or None, ALERT: text, ALERT_ON: when, DECISION: None, ACK_BY: None, ACK_ON: None},
			update_modified=False,
		)
		alerts.raise_todo(
			RULE,
			WO,
			wo.name,
			_("Job Order {0} ({1}): {2}. Check the job and acknowledge on the Job Order.").format(
				wo.name, item, text
			),
			owner_field=OWNER_FIELD,
			priority="High",
		)
		flagged.append(wo.name)
	return flagged


def on_product_update(doc, method=None):
	"""PEPL Product Master on_update: a changed current drawing revision flags the open Job Orders."""
	before = doc.get_doc_before_save()
	old = cstr(before.get("current_drawing_revision")).strip() if before else ""
	new = cstr(doc.get("current_drawing_revision")).strip()
	if not old or not new or old == new or not doc.get("linked_item"):
		return None
	frappe.db.savepoint("pepl_drawing_rev")
	try:
		flag_job_orders(doc.linked_item, old, new, _change_description(doc, new), doc.name)
	except Exception:
		frappe.db.rollback(save_point="pepl_drawing_rev")
		frappe.log_error(title=f"PEPL: drawing change of {doc.name} not flagged on the Job Orders")
	return None


def pending(work_order):
	values = frappe.db.get_value(WO, work_order, [ALERT, ACK_ON], as_dict=True)
	return bool(values and values.get(ALERT) and not values.get(ACK_ON))


@frappe.whitelist()
def acknowledge(work_order, work_to, remarks):
	"""Record what the job is made to after the drawing change; clears the flag and closes the ToDo."""
	frappe.only_for(ACK_ROLES)
	if not pending(work_order):
		frappe.throw(_("Job Order {0} has no drawing change to acknowledge.").format(work_order))
	remarks = (remarks or "").strip()
	if len(remarks) < 10:
		frappe.throw(_("Say what was checked or agreed (at least 10 characters)."))
	item = frappe.db.get_value(WO, work_order, "production_item")
	new = current_revision(item)
	made = frappe.db.get_value(WO, work_order, REVISION)
	if work_to not in (new, made):
		frappe.throw(_("Work to Rev {0} (the new drawing) or Rev {1} (as made).").format(new, made or "-"))
	frappe.db.set_value(
		WO,
		work_order,
		{
			REVISION: work_to,
			DECISION: _("Work to Rev {0}: {1}").format(work_to, remarks)[:500],
			ACK_BY: frappe.session.user,
			ACK_ON: now_datetime(),
		},
		update_modified=False,
	)
	alerts.close_one(RULE, WO, work_order)
	return {"work_to": work_to}


@frappe.whitelist()
def get_drawing_panel(work_order):
	"""For the Job Order form: the revision it is made to, the change, the acknowledgement."""
	frappe.has_permission(WO, "read", doc=work_order, throw=True)
	values = frappe.db.get_value(
		WO, work_order, ["production_item", REVISION, ALERT, ACK_BY, ACK_ON, DECISION], as_dict=True
	)
	current = current_revision(values.production_item)
	if not current and not values.get(ALERT):
		return {"rows": [], "can_acknowledge": False}
	made = values.get(REVISION)
	rows = []
	if values.get(ALERT) and not values.get(ACK_ON):
		rows.append({"text": values.get(ALERT), "colour": "red"})
		rows.append(
			{
				"text": _(
					"Check the job against Rev {0} and acknowledge: work to Rev {0}, or Rev {1} as made"
				).format(current, made or "-"),
				"colour": "red",
			}
		)
	else:
		rows.append(
			{
				"text": _("Made to drawing Rev {0} · current Rev {1}").format(made or "-", current or "-"),
				"colour": "green" if made == current else "orange",
			}
		)
		if values.get(ACK_ON):
			rows.append(
				{
					"text": _("{0} · acknowledged by {1} on {2}").format(
						values.get(DECISION), values.get(ACK_BY), formatdate(getdate(values.get(ACK_ON)))
					),
					"colour": "gray",
				}
			)
	can = (
		bool(values.get(ALERT)) and not values.get(ACK_ON) and bool(set(ACK_ROLES) & set(frappe.get_roles()))
	)
	return {"rows": rows, "can_acknowledge": can, "current": current, "made": made}


def warn_shift_entry(doc, method=None):
	"""PEPL Shift Production Entry validate: warn when a row's Job Order has an unacknowledged drawing change."""
	seen = set()
	for row in doc.get("production") or []:
		wo = row.get("work_order")
		if wo and wo not in seen and pending(wo):
			seen.add(wo)
			frappe.msgprint(
				_("Job Order {0}: {1}. Production has not acknowledged it yet.").format(
					wo, frappe.db.get_value(WO, wo, ALERT)
				),
				title=_("Drawing changed"),
				indicator="orange",
			)
	return None
