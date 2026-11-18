"""C3b-P3 - The CAPA panel: where the CAPA stands, its NCRs, the five-why, each open action and what stops closing.

One panel ("CAPA") at the top of the PEPL CAPA form, in this order:
  "CAPA (Critical NCR) on PIN-10, In Progress · raised 01-11-2026 (17 day(s) ago) by the system · owner qm@..."
  "Target 01-12-2026: 13 day(s) left"  /  "Target 14-11-2026 - OVERDUE by 4 day(s)" (red)  /  "Closed on ... - target met"
  "NCRs (2): NCR-0001 Major, Closed · NCR-0004 Critical, Open"
  "Containment: Sorted the stock at stores"  /  "Containment: not recorded" (orange)
  "Five-why: 3 of 5 whys answered, root cause missing · next: Why 4"  /  "Five-why: complete · root cause: worn collet"
  "Actions: 3 (Correction 1, Corrective Action 1, Preventive Action 1) · 1 done · 2 open, 1 overdue"
  "Corrective Action: replace collet · ravi@... · due 10-11-2026 - OVERDUE by 8 day(s)"     (one line per open action)
  "To close: no Corrective Action; 2 action(s) not done"  /  "Ready to close: ..."  /  "Cancelled: reason"
(The effectiveness check before final closure is added to this panel by C3b-B3.)
"""

import frappe
from frappe import _
from frappe.utils import date_diff, formatdate, getdate, today

from pepl_os.pepl_quality import capa

SOON_DAYS = 7
ACTION_TYPES = (capa.CORRECTION, capa.CORRECTIVE, capa.PREVENTIVE)
NCRS_SHOWN = 5


def is_open(doc):
	return doc.status not in capa.DONE_STATES


def _days_ago(on):
	days = date_diff(today(), on)
	if days <= 0:
		return _("raised today")
	return _("raised {0} ({1} day(s) ago)").format(formatdate(on), days)


def due_text(due, as_of=None):
	"""(text, colour) for a due date: days left, due today, or overdue."""
	left = date_diff(due, as_of or today())
	if left < 0:
		return _("{0} - OVERDUE by {1} day(s)").format(formatdate(due), -left), "red"
	if left == 0:
		return _("{0} - due today").format(formatdate(due)), "orange"
	return _("{0}: {1} day(s) left").format(formatdate(due), left), "orange" if left <= SOON_DAYS else "green"


def header_row(doc):
	text = _("CAPA ({0}) on {1}, {2}").format(
		_(doc.trigger or capa.MANUAL_TRIGGER), doc.item or "-", _(doc.status)
	)
	if doc.raised_on:
		text += " · " + _days_ago(doc.raised_on)
	if doc.raised_by_system:
		text += " " + _("by the system")
	text += " · " + _("owner {0}").format(doc.capa_owner or _("not set"))
	if doc.status == capa.CLOSED:
		colour = "green"
	elif doc.status == capa.CANCELLED:
		colour = "gray"
	else:
		colour = "red" if doc.target_date and date_diff(today(), doc.target_date) > 0 else "orange"
	return {"text": text, "colour": colour}


def target_row(doc):
	if doc.status == capa.CANCELLED:
		return None
	if doc.status == capa.CLOSED:
		closed = getdate(doc.closed_on) if doc.closed_on else None
		text = _("Closed on {0} by {1}").format(formatdate(closed) if closed else "-", doc.closed_by or "-")
		if closed and doc.target_date:
			late = date_diff(closed, doc.target_date)
			if late > 0:
				return {
					"text": text + " - " + _("{0} day(s) after the target").format(late),
					"colour": "orange",
				}
			return {"text": text + " - " + _("target met"), "colour": "green"}
		return {"text": text, "colour": "green"}
	if not doc.target_date:
		return {"text": _("Target: not set"), "colour": "orange"}
	text, colour = due_text(doc.target_date)
	return {"text": _("Target {0}").format(text), "colour": colour}


def ncr_row(doc):
	names = [r.ncr for r in doc.get("ncrs") or [] if r.ncr]
	if not names:
		return {"text": _("NCRs: none listed"), "colour": "gray"}
	found = {
		r.name: r
		for r in frappe.get_all(
			capa.NCR, filters={"name": ["in", names]}, fields=["name", "severity", "status"]
		)
	}
	parts = []
	for name in names[:NCRS_SHOWN]:
		r = found.get(name)
		parts.append(f"{name} {_(r.severity)}, {_(r.status)}" if r else name)
	text = _("NCRs ({0}): {1}").format(len(names), " · ".join(parts))
	if len(names) > NCRS_SHOWN:
		text += " " + _("and {0} more").format(len(names) - NCRS_SHOWN)
	return {"text": text, "colour": "gray"}


def containment_row(doc):
	given = (doc.containment or "").strip()
	if given:
		return {"text": _("Containment: {0}").format(given[:160]), "colour": "gray"}
	return {"text": _("Containment: not recorded"), "colour": "orange" if is_open(doc) else "gray"}


def five_why_row(doc):
	filled, required, has_root, complete = capa.five_why_state(doc)
	if complete:
		return {
			"text": _("Five-why: complete · root cause: {0}").format((doc.root_cause or "").strip()[:160]),
			"colour": "green",
		}
	text = _("Five-why: {0} of {1} whys answered, root cause {2}").format(
		filled, required, _("given") if has_root else _("missing")
	)
	gap = next(
		(i for i, f in enumerate(capa.WHY_FIELDS[:required], 1) if not (doc.get(f) or "").strip()), None
	)
	if gap:
		text += " · " + _("next: Why {0}").format(gap)
	return {"text": text, "colour": "orange" if is_open(doc) else "gray"}


def action_rows(doc):
	actions = doc.get("actions") or []
	if not actions:
		return [{"text": _("Actions: none yet"), "colour": "orange" if is_open(doc) else "gray"}]
	counts = [(t, sum(1 for a in actions if a.action_type == t)) for t in ACTION_TYPES]
	open_ = [a for a in actions if not a.done_on]
	late = [a for a in open_ if a.due_date and date_diff(today(), a.due_date) > 0]
	text = _("Actions: {0} ({1}) · {2} done · {3} open").format(
		len(actions),
		", ".join(f"{_(t)} {n}" for t, n in counts if n),
		len(actions) - len(open_),
		len(open_),
	)
	if late:
		text += _(", {0} overdue").format(len(late))
	colour = "red" if late else ("orange" if open_ else "green")
	rows = [{"text": text, "colour": colour}]
	if not is_open(doc):
		return rows
	for a in open_:
		line = f"{_(a.action_type or _('Action'))}: {(a.description or '').strip()[:120] or '-'}"
		line += " · " + (a.responsible or _("no one responsible"))
		if a.due_date:
			due, colour = due_text(a.due_date)
			line += " · " + _("due {0}").format(due)
		else:
			line += " · " + _("no due date")
			colour = "orange"
		if not a.responsible and colour != "red":
			colour = "orange"
		rows.append({"text": line, "colour": colour})
	return rows


def closing_row(doc):
	if doc.status == capa.CLOSED:
		return None
	if doc.status == capa.CANCELLED:
		return {
			"text": _("Cancelled: {0}").format((doc.cancel_reason or "").strip() or "-"),
			"colour": "gray",
		}
	gaps = capa.closing_gaps(doc)
	if gaps:
		return {"text": _("To close: {0}").format("; ".join(gaps)), "colour": "orange"}
	return {"text": _("Ready to close: set the Status to Closed and save"), "colour": "green"}


def panel_rows(doc):
	rows = [header_row(doc), target_row(doc), ncr_row(doc), containment_row(doc), five_why_row(doc)]
	rows += action_rows(doc)
	rows.append(closing_row(doc))
	return [r for r in rows if r]


@frappe.whitelist()
def get_capa_panel(name):
	"""Rows for the "CAPA" panel."""
	doc = frappe.get_doc(capa.CAPA, name)
	doc.check_permission("read")
	return panel_rows(doc)
