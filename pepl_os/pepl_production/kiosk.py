"""C3a-B1 - The shift-entry kiosk: one simple web page per machine (portal, not the Desk), and the foreman view.

The kiosk is a tablet or PC beside the machine, logged in once as a kiosk user (role "PEPL Kiosk", no Desk
access). An operator identifies with employee code + PIN; the page then shows his entry for that machine,
shift and day - production blocks against the machine's open Job Cards, stops by downtime category, tool
changes with a photo taken on the spot - with the same help the Desk form gives (gaps, Job Card left, speed,
skill) and saves / submits the very same Shift Production Entry (C3a-X1). Consumables stay with Stores in the Desk.

Safety:
- every call needs the kiosk role (or Manufacturing User / Manager, System Manager) and, after sign-in, the
  operator's kiosk session (a random token kept on the server for "Kiosk: Session Minutes", 30);
- wrong PINs: after "Kiosk: Wrong PIN Tries" (5) wrong PINs an operator is locked for "Kiosk: Lock Minutes" (15);
  the message never says whether the code or the PIN was wrong;
- an operator sees and changes only his own entry of that machine, shift and day; a submitted entry is read-only.

Foreman view: for a day and shift, every machine that runs - entry submitted / draft / missing, minutes not
explained, good / rejected, operator - with the gaps, so the foreman knows whom to chase before the shift ends.
"""

import base64
import json
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, get_time, getdate, now_datetime, today

from pepl_os.common import params
from pepl_os.common.overrides import _clean_reason, log_override
from pepl_os.pepl_production import masters, skill, spr, spr_aids
from pepl_os.pepl_production.job_order_panel import qty_text

KIOSK_ROLE = "PEPL Kiosk"
KIOSK_HOME = "kiosk"  # the page a kiosk login opens after logging in
KIOSK_ROLES = (KIOSK_ROLE, "Manufacturing User", "Manufacturing Manager", "System Manager")
FOREMAN_ROLES = ("PEPL Foreman", "Manufacturing User", "Manufacturing Manager", "System Manager")
TRIES_FIELD = "custom_kiosk_pin_tries"
LOCK_FIELD = "custom_kiosk_lock_minutes"
SESSION_FIELD = "custom_kiosk_session_minutes"
TRIES_RANGE, LOCK_RANGE, SESSION_RANGE = (3, 10), (1, 120), (5, 240)
MAX_PHOTO_BYTES = 3 * 1024 * 1024
SIGN_IN_FAILED = "Employee code or PIN not recognised."


def _bounded(field, default, bounds):
	low, high = bounds
	return min(max(cint(params.get(field, default)) or default, low), high)


def pin_tries():
	return _bounded(TRIES_FIELD, 5, TRIES_RANGE)


def lock_minutes():
	return _bounded(LOCK_FIELD, 15, LOCK_RANGE)


def session_minutes():
	return _bounded(SESSION_FIELD, 30, SESSION_RANGE)


def _require(roles):
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(_("This page is for the shop-floor kiosk."), frappe.PermissionError)


# The kiosk login lands on the kiosk -------------------------------------------------------------------------
# After login Frappe sends a website user to the user's Default App (else to /desk when apps are installed), and a
# kiosk login has no Desk, so it met "Not Permitted". pepl_os is listed as an app whose page is /kiosk (only for
# kiosk logins), and every kiosk login gets pepl_os as its Default App; the PEPL Kiosk role's home page is the kiosk.


def is_kiosk_login(user=None):
	"""A login with the PEPL Kiosk role and no Desk (a Website User)."""
	user = user or frappe.session.user
	if user in ("Guest", "Administrator"):
		return False
	return frappe.db.get_value(
		"User", user, "user_type"
	) == "Website User" and KIOSK_ROLE in frappe.get_roles(user)


def kiosk_app_permission():
	"""add_to_apps_screen has_permission: the "Shift Entry Kiosk" app is shown to kiosk logins only."""
	return is_kiosk_login()


def point_to_kiosk(user):
	"""Make the kiosk the Default App of a kiosk login (an app the user picked by hand is kept)."""
	if not is_kiosk_login(user) or frappe.db.get_value("User", user, "default_app"):
		return False
	frappe.db.set_value("User", user, "default_app", "pepl_os", update_modified=False)
	frappe.clear_document_cache("User", user)
	frappe.cache.hdel("home_page", user)
	return True


def on_user_update(doc, method=None):
	"""doc_events: User on_update - a login given the PEPL Kiosk profile opens the kiosk after logging in."""
	point_to_kiosk(doc.name)


def point_kiosk_logins_home():
	"""Install / migrate: kiosk logins made before this release open the kiosk too."""
	users = frappe.get_all(
		"Has Role", filters={"role": KIOSK_ROLE, "parenttype": "User"}, pluck="parent", distinct=True
	)
	return [user for user in users if point_to_kiosk(user)]


# Shifts and the page --------------------------------------------------------------------------------------


def _shifts():
	return frappe.get_all(
		masters.SHIFT,
		filters={"is_active": 1},
		fields=["name", "start_time", "end_time", "planned_minutes"],
		order_by="start_time asc",
	)


def current_shift(at=None):
	"""(shift, shift date) running at a moment; a night shift after midnight belongs to the day before."""
	at = get_datetime(at or now_datetime())
	for day in (getdate(at), getdate(add_days(at, -1))):
		for s in _shifts():
			start, end = spr.shift_window(day, s)
			if start <= at < end:
				return s.name, str(day)
	return None, str(getdate(at))


@frappe.whitelist()
def kiosk_context(machine):
	"""What the kiosk page needs before anyone signs in."""
	_require(KIOSK_ROLES)
	ws = frappe.db.get_value("Workstation", machine, ["name", "workstation_type", "disabled"], as_dict=True)
	if not ws or cint(ws.disabled):
		frappe.throw(_("Machine {0} not found or disabled.").format(machine))
	shift, day = current_shift()
	return {
		"machine": ws.name,
		"machine_group": ws.workstation_type or "",
		"shifts": [
			{"name": s.name, "start": _clock(s.start_time), "end": _clock(s.end_time)} for s in _shifts()
		],
		"shift": shift,
		"dates": [today(), add_days(today(), -1)],
		"date": day,
		"categories": frappe.get_all(
			masters.DOWNTIME,
			filters={"is_active": 1},
			fields=["name", "stop_type", "is_breakdown"],
			order_by="name",
		),
		"tool_reasons": ["Worn out", "Broken", "Planned change", "Setup / new job", "Other"],
	}


# Sign-in --------------------------------------------------------------------------------------------------


def _lock_key(code):
	return f"pepl_kiosk_lock:{(code or '').strip().upper()}"


def _tries_key(code):
	return f"pepl_kiosk_tries:{(code or '').strip().upper()}"


def _locked_for(code):
	until = frappe.cache.get_value(_lock_key(code))
	if not until:
		return 0
	left = (get_datetime(until) - now_datetime()).total_seconds()
	return max(int(left // 60) + 1, 1) if left > 0 else 0


def _wrong_pin(code):
	tries = cint(frappe.cache.get_value(_tries_key(code))) + 1
	frappe.cache.set_value(_tries_key(code), tries, expires_in_sec=lock_minutes() * 60)
	if tries >= pin_tries():
		until = now_datetime() + timedelta(minutes=lock_minutes())
		frappe.cache.set_value(_lock_key(code), str(until), expires_in_sec=lock_minutes() * 60)
		frappe.cache.delete_value(_tries_key(code))


def _session_key(token):
	return f"pepl_kiosk_session:{token}"


def _session(token):
	data = frappe.cache.get_value(_session_key(token)) if token else None
	if not data:
		frappe.throw(
			_("Your kiosk session has ended. Sign in again with your code and PIN."),
			frappe.AuthenticationError,
		)
	data = frappe._dict(data)
	frappe.cache.set_value(
		_session_key(token), dict(data), expires_in_sec=session_minutes() * 60
	)  # still working
	return data


@frappe.whitelist()
def sign_in(machine, shift, posting_date, employee_code, pin):
	"""Code + PIN -> a kiosk session for this machine, shift and day, and the operator's entry (if any)."""
	_require(KIOSK_ROLES)
	code = (employee_code or "").strip()
	minutes = _locked_for(code)
	if minutes:
		frappe.throw(
			_("Too many wrong PINs. Try again in {0} minute(s), or ask the foreman.").format(minutes)
		)
	operator = frappe.db.get_value(masters.OPERATOR, {"employee_code": code}, "name") if code else None
	if not operator or not masters.verify_operator_pin(operator, pin):
		_wrong_pin(code)
		frappe.throw(_(SIGN_IN_FAILED))
	frappe.cache.delete_value(_tries_key(code))
	if getdate(posting_date) not in (getdate(today()), getdate(add_days(today(), -1))):
		frappe.throw(
			_("The kiosk takes today's or yesterday's shift only. Ask the foreman for an older one.")
		)
	if not frappe.db.get_value(masters.SHIFT, {"name": shift, "is_active": 1}):
		frappe.throw(_("Choose an active shift."))
	token = frappe.generate_hash(length=32)
	session = {
		"operator": operator,
		"machine": machine,
		"shift": shift,
		"posting_date": str(getdate(posting_date)),
	}
	frappe.cache.set_value(_session_key(token), session, expires_in_sec=session_minutes() * 60)
	return {"token": token, **entry_state(session)}


@frappe.whitelist()
def sign_out(token):
	_require(KIOSK_ROLES)
	frappe.cache.delete_value(_session_key(token))
	return True


# The entry ------------------------------------------------------------------------------------------------


def _entry_name(session):
	return frappe.db.get_value(
		spr.DOCTYPE,
		{
			"workstation": session["machine"],
			"shift": session["shift"],
			"posting_date": session["posting_date"],
			"operator": session["operator"],
			"docstatus": ["<", 2],
		},
		"name",
	)


def open_job_cards(machine):
	cards = frappe.get_all(
		"Job Card",
		filters={"workstation": machine, "docstatus": 0},
		fields=["name", "production_item", "operation", "for_quantity", "work_order"],
		order_by="creation asc",
	)
	for c in cards:
		c.done = spr.job_card_qty_done(c.name)
		c.label = _("{0} · {1} · {2}: {3} of {4} done").format(
			c.name, c.production_item, c.operation, qty_text(c.done), qty_text(c.for_quantity)
		)
	return cards


def _clock(value):
	"""A stored time as HH:MM for the page. The database gives a time as a timedelta, whose text has no leading zero
	("8:00:00"), so cutting the text gave "8:00:", which a time box cannot show (CI #45)."""
	return get_time(value).strftime("%H:%M") if value not in (None, "") else ""


def entry_state(session):
	"""Everything the kiosk shows after sign-in."""
	name = _entry_name(session)
	operator_name = frappe.db.get_value(masters.OPERATOR, session["operator"], "operator_name")
	state = {
		"operator": session["operator"],
		"operator_name": operator_name,
		"machine": session["machine"],
		"shift": session["shift"],
		"posting_date": session["posting_date"],
		"job_cards": open_job_cards(session["machine"]),
		"entry": None,
		"production": [],
		"downtime": [],
		"tool_changes": [],
		"docstatus": 0,
		"aids": [],
		"shift_panel": [],
		"needs_reason": None,
	}
	if not name:
		return state
	doc = frappe.get_doc(spr.DOCTYPE, name)
	state.update(
		entry=name,
		docstatus=doc.docstatus,
		production=[
			{
				"job_card": r.job_card,
				"from_time": _clock(r.from_time),
				"to_time": _clock(r.to_time),
				"good_qty": flt(r.good_qty),
				"rejected_qty": flt(r.rejected_qty),
				"rejection_reason": r.rejection_reason or "",
			}
			for r in doc.production
		],
		downtime=[
			{
				"downtime_category": r.downtime_category,
				"from_time": _clock(r.from_time),
				"to_time": _clock(r.to_time),
			}
			for r in doc.downtime
		],
		tool_changes=[
			{
				"change_time": _clock(r.change_time),
				"tool_description": r.tool_description or r.tool_item or "",
				"reason": r.reason,
				"photo": r.photo or "",
			}
			for r in doc.tool_changes
		],
		aids=spr_aids.aid_rows(doc),
		shift_panel=spr.panel_rows(doc),
		needs_reason=skill.gate_message(doc) if doc.docstatus == 0 else None,
	)
	return state


def entry_company(production=()):
	"""The company of a new kiosk entry. A kiosk login has no default company (C3a-B1 fix found by CI #43), so:
	the company of the first Job Card on the entry, else the site's default company, else the only company."""
	for r in production or []:
		company = r.get("job_card") and frappe.db.get_value("Job Card", r.get("job_card"), "company")
		if company:
			return company
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if company:
		return company
	companies = frappe.get_all("Company", pluck="name", limit=2)
	if len(companies) == 1:
		return companies[0]
	frappe.throw(_("Pick a Job Card on the first row: the kiosk takes the company from it."))


def _attach_photo(doc, data_url, label):
	"""A photo taken on the kiosk (data URL, JPEG / PNG) saved as a private File on the entry."""
	if not data_url or not str(data_url).startswith("data:image/"):
		return None
	header, _sep, encoded = str(data_url).partition(",")
	content = base64.b64decode(encoded)
	if len(content) > MAX_PHOTO_BYTES:
		frappe.throw(_("{0}: the photo is too large (at most 3 MB).").format(label))
	extension = "png" if "png" in header else "jpg"
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"tool-change-{doc.name}-{frappe.generate_hash(length=6)}.{extension}",
			"content": content,
			"attached_to_doctype": spr.DOCTYPE,
			"attached_to_name": doc.name,
			"is_private": 1,
		}
	)
	file.insert(ignore_permissions=True)
	return file.file_url


@frappe.whitelist()
def save_entry(token, production=None, downtime=None, tool_changes=None):
	"""Create or update the operator's draft entry from the kiosk rows. Returns the new state."""
	_require(KIOSK_ROLES)
	session = _session(token)
	production = json.loads(production) if isinstance(production, str) else (production or [])
	downtime = json.loads(downtime) if isinstance(downtime, str) else (downtime or [])
	tool_changes = json.loads(tool_changes) if isinstance(tool_changes, str) else (tool_changes or [])
	name = _entry_name(session)
	if name:
		doc = frappe.get_doc(spr.DOCTYPE, name)
		if doc.docstatus != 0:
			frappe.throw(_("This entry is already submitted. Ask the foreman to change it."))
	else:
		doc = frappe.get_doc(
			{
				"doctype": spr.DOCTYPE,
				"posting_date": session["posting_date"],
				"shift": session["shift"],
				"workstation": session["machine"],
				"operator": session["operator"],
				"company": entry_company(production),
			}
		)
	doc.set("production", [])
	for r in production:
		row = {
			"job_card": r.get("job_card"),
			"from_time": r.get("from_time"),
			"to_time": r.get("to_time"),
			"good_qty": flt(r.get("good_qty")),
			"rejected_qty": flt(r.get("rejected_qty")),
			"rejection_reason": (r.get("rejection_reason") or "").strip(),
		}
		doc.append("production", row)
	doc.set("downtime", [])
	for r in downtime:
		doc.append(
			"downtime",
			{
				"downtime_category": r.get("downtime_category"),
				"from_time": r.get("from_time"),
				"to_time": r.get("to_time"),
			},
		)
	pending_photos = []
	doc.set("tool_changes", [])
	for r in tool_changes:
		photo = r.get("photo") or ""
		row = doc.append(
			"tool_changes",
			{
				"change_time": r.get("change_time"),
				"tool_description": (r.get("tool_description") or "").strip(),
				"reason": r.get("reason") or "Other",
				"photo": photo if photo and not str(photo).startswith("data:") else "",
			},
		)
		if str(photo).startswith("data:"):
			pending_photos.append((row, photo))
	doc.flags.ignore_permissions = True
	if name:
		doc.save()
	else:
		doc.insert()
	if pending_photos:
		for row, data_url in pending_photos:
			row.photo = _attach_photo(doc, data_url, _("Tool change row {0}").format(row.idx))
		doc.save()
	return entry_state(session)


@frappe.whitelist()
def submit_entry(token, reason=None):
	"""Submit the operator's entry. A Soft Block skill shortfall needs a reason (logged with the operator)."""
	_require(KIOSK_ROLES)
	session = _session(token)
	name = _entry_name(session)
	if not name:
		frappe.throw(_("Save the entry first."))
	doc = frappe.get_doc(spr.DOCTYPE, name)
	if doc.docstatus != 0:
		frappe.throw(_("This entry is already submitted."))
	message = skill.gate_message(doc)
	if message:
		if not (reason or "").strip():
			return {**entry_state(session), "needs_reason": message}
		_clean_reason(reason)  # at least the minimum length, as in the Desk
		log_override(
			skill.RULE_CODE,
			spr.DOCTYPE,
			doc.name,
			message,
			_("{0} (operator {1}, at the kiosk)").format(reason.strip(), session["operator"]),
		)
	doc.flags.ignore_permissions = True
	doc.submit()
	return entry_state(session)


# Foreman view ---------------------------------------------------------------------------------------------


@frappe.whitelist()
def foreman_board(posting_date=None, shift=None):
	"""Every machine that runs: entries of the day and shift, minutes not explained, output, gaps."""
	_require(FOREMAN_ROLES)
	posting_date = str(getdate(posting_date or today()))
	if not shift:
		shift = current_shift()[0] or (_shifts()[0].name if _shifts() else None)
	limit = spr.unaccounted_limit()
	recent = set(
		frappe.get_all(
			spr.DOCTYPE,
			filters={
				"docstatus": 1,
				"posting_date": ["between", [add_days(posting_date, -30), posting_date]],
			},
			pluck="workstation",
			distinct=True,
		)
	)
	entries = frappe.get_all(
		spr.DOCTYPE,
		filters={"posting_date": posting_date, "shift": shift, "docstatus": ["<", 2]},
		fields=[
			"name",
			"workstation",
			"operator",
			"operator_name",
			"docstatus",
			"unaccounted_minutes",
			"total_good_qty",
			"total_rejected_qty",
		],
		order_by="workstation asc",
	)
	machines = sorted(recent | {e.workstation for e in entries})
	rows = []
	for m in machines:
		mine = [e for e in entries if e.workstation == m]
		if not mine:
			rows.append({"machine": m, "state": "Missing", "colour": "red", "text": _("No entry yet")})
			continue
		first = frappe.get_doc(spr.DOCTYPE, mine[0].name)
		gaps = spr_aids.gaps(first)
		gap_text = ", ".join(f"{spr._clock(a)}-{spr._clock(b)}" for a, b, _m in gaps[:4])
		submitted = all(e.docstatus == 1 for e in mine)
		unexplained = min(cint(e.unaccounted_minutes) for e in mine)
		state = "Submitted" if submitted else "Draft"
		colour = "green" if submitted else ("orange" if unexplained > limit else "blue")
		rows.append(
			{
				"machine": m,
				"state": state,
				"colour": colour,
				"entries": [e.name for e in mine],
				"operators": ", ".join(e.operator_name or e.operator for e in mine),
				"good": qty_text(sum(flt(e.total_good_qty) for e in mine)),
				"rejected": qty_text(sum(flt(e.total_rejected_qty) for e in mine)),
				"unexplained": unexplained,
				"text": _("Not covered: {0}").format(gap_text) if gap_text else _("Every minute covered"),
			}
		)
	return {
		"posting_date": posting_date,
		"shift": shift,
		"shifts": [s.name for s in _shifts()],
		"limit": limit,
		"rows": rows,
		"missing": sum(1 for r in rows if r["state"] == "Missing"),
		"drafts": sum(1 for r in rows if r["state"] == "Draft"),
		"submitted": sum(1 for r in rows if r["state"] == "Submitted"),
	}
