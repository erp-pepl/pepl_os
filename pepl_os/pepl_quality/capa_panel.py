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
C3b-B3 adds the effectiveness check:
  "Actions completed on 12-11-2026 - target met"  ·  "Effectiveness check 10-02-2027: 83 day(s) left"
  (red when overdue, or when a Major / Critical NCR was raised on the item since the actions were completed)
  "To close: Verify Effectiveness on or after 10-02-2027"  ·  "Verified effective on ... by ..."  ·
  "Found not effective 1 time(s), last on ...: <remarks>"
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, formatdate, getdate, today

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
	elif doc.status == capa.AWAITING:
		colour = "red" if capa.verification_overdue(doc) else "orange"
	else:
		colour = "red" if doc.target_date and date_diff(today(), doc.target_date) > 0 else "orange"
	return {"text": text, "colour": colour}


def _against_target(doc, done_on):
	"""(" - target met" or " - n day(s) after the target", colour) for the day the actions were complete."""
	if not done_on or not doc.target_date:
		return "", "green"
	late = date_diff(getdate(done_on), doc.target_date)
	if late > 0:
		return " - " + _("{0} day(s) after the target").format(late), "orange"
	return " - " + _("target met"), "green"


def target_row(doc):
	if doc.status == capa.CANCELLED:
		return None
	if doc.status == capa.CLOSED:
		closed = getdate(doc.closed_on) if doc.closed_on else None
		text = _("Closed on {0} by {1}").format(formatdate(closed) if closed else "-", doc.closed_by or "-")
		suffix, colour = _against_target(doc, doc.get("actions_completed_on") or closed)
		return {"text": text + suffix, "colour": colour}
	if doc.status == capa.AWAITING:
		done = doc.get("actions_completed_on")
		suffix, colour = _against_target(doc, done)
		return {
			"text": _("Actions completed on {0}").format(formatdate(getdate(done)) if done else "-") + suffix,
			"colour": colour,
		}
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


def verification_row(doc):
	"""The effectiveness check: when it is due, what it found (C3b-B3)."""
	if doc.status == capa.AWAITING and doc.get("verification_due_on"):
		text, colour = due_text(doc.verification_due_on)
		text = _("Effectiveness check {0}").format(text)
		since = capa.ncrs_since_completion(doc)
		if since:
			text += " · " + _(
				"Major / Critical NCR(s) since the actions were completed: {0} - not effective"
			).format(", ".join(since))
			colour = "red"
		return {"text": text, "colour": colour}
	if doc.status == capa.CLOSED and doc.get("verification_result") == capa.EFFECTIVE:
		return {
			"text": _("Verified effective on {0} by {1}").format(
				formatdate(doc.verified_on) if doc.verified_on else "-", doc.verified_by or "-"
			),
			"colour": "green",
		}
	if is_open(doc) and cint(doc.get("verification_count")):
		last = ((doc.get("verification_remarks") or "").strip().splitlines() or [""])[-1]
		return {
			"text": _("Found not effective {0} time(s), last: {1}").format(
				cint(doc.verification_count), last[:160]
			),
			"colour": "red",
		}
	return None


def closing_row(doc):
	if doc.status == capa.CLOSED:
		return None
	if doc.status == capa.AWAITING:
		due = doc.get("verification_due_on")
		if due and date_diff(due, today()) <= 0:
			return {
				"text": _(
					"To close: press Verify Effectiveness (Effective closes it; Not Effective reopens it)"
				),
				"colour": "red" if capa.verification_overdue(doc) else "orange",
			}
		return {
			"text": _("To close: Verify Effectiveness on or after {0}").format(
				formatdate(due) if due else "-"
			),
			"colour": "gray",
		}
	if doc.status == capa.CANCELLED:
		return {
			"text": _("Cancelled: {0}").format((doc.cancel_reason or "").strip() or "-"),
			"colour": "gray",
		}
	gaps = capa.closing_gaps(doc)
	if gaps:
		return {"text": _("To close: {0}").format("; ".join(gaps)), "colour": "orange"}
	days = capa.verification_days()
	if days:
		return {
			"text": _(
				"Ready: set the Status to Closed and save - the effectiveness check is then due in {0} day(s)"
			).format(days),
			"colour": "green",
		}
	return {"text": _("Ready to close: set the Status to Closed and save"), "colour": "green"}


def panel_rows(doc):
	rows = [header_row(doc), target_row(doc), ncr_row(doc), containment_row(doc), five_why_row(doc)]
	rows += action_rows(doc)
	rows += [verification_row(doc), closing_row(doc)]
	return [r for r in rows if r]


@frappe.whitelist()
def get_capa_panel(name):
	"""Rows for the "CAPA" panel."""
	doc = frappe.get_doc(capa.CAPA, name)
	doc.check_permission("read")
	return panel_rows(doc)
