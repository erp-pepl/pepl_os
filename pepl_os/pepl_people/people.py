"""C4-H1 - People: the Employee master with the actor / subject distinction, leavers, operators.

* Person Type (on every Employee, set from the data): "Login User" - the person works in ERPNext under his own login
  (an actor: what he does is recorded against his login); "Shop Floor" - no login (a subject: others record his work;
  at the machine he signs in on the kiosk with his operator code and PIN).
* A device login (a role in "Device Login Roles", e.g. the PEPL Kiosk tablet) is never a person's login.
* The operator code (PEPL Operator) and the Employee Number are the same code; a mismatch is refused on both sides.
* ERPNext's own rules that PEPL changed (26 Nov 2026):
  - ERPNext switches the login off when the Employee is no longer Active. PEPL keeps the login on (System
    Parameters -> People: Keep the Login When an Employee Leaves); the 3-hour idle logout still applies.
  - ERPNext restricts a linked login to its own Employee record ("Create User Permission"). PEPL gives access by job
    profile (CR3), so this stays off unless "Restrict a Login to Its Own Employee Record" is ticked.
* A leaver with a login: ToDo PPL-LEAVER-LOGIN to the person named in "Leaver Login ToDo To" (else the Notification
  Fallback Owner), for information.
* Make Operator from an Employee; an operator whose code equals a new Employee's number is linked to it at once.
"""

import frappe
from frappe import _
from frappe.utils import cint

from pepl_os.common import alerts, params

OPERATOR = "PEPL Operator"
PERSON_TYPE_FIELD = "custom_person_type"
LOGIN_USER = "Login User"
SHOP_FLOOR = "Shop Floor"

KEEP_LOGIN_FIELD = "custom_keep_login_when_employee_leaves"
OWN_RECORD_FIELD = "custom_restrict_login_to_own_employee"
LEAVER_TODO_FIELD = "custom_leaver_login_todo_to"
DEVICE_ROLES_FIELD = "custom_device_login_roles"
DEFAULT_DEVICE_ROLES = "PEPL Kiosk"
LEAVER_RULE = "PPL-LEAVER-LOGIN"


def lines(value):
	return [r.strip() for r in str(value or "").splitlines() if r.strip()]


def device_roles():
	return lines(params.get(DEVICE_ROLES_FIELD, DEFAULT_DEVICE_ROLES)) or lines(DEFAULT_DEVICE_ROLES)


def is_device_login(user):
	if not user:
		return False
	roles = set(frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, pluck="role"))
	return bool(roles & set(device_roles()))


def person_type(doc):
	return LOGIN_USER if doc.get("user_id") else SHOP_FLOOR


def operator_of(employee):
	return frappe.db.get_value(OPERATOR, {"employee": employee}, "name") if employee else None


# ---------------- Employee hooks ----------------
def validate_employee(doc, method=None):
	"""doc_events: Employee validate."""
	doc.set(PERSON_TYPE_FIELD, person_type(doc))
	if doc.get("user_id") and is_device_login(doc.user_id):
		frappe.throw(
			_("{0} is a device login (kiosk tablet), not a person's login. Leave User ID empty for {1}.").format(
				doc.user_id, doc.get("employee_name") or doc.name
			)
		)
	if not params.is_enabled(OWN_RECORD_FIELD, 0):
		doc.create_user_permission = 0
	operator = operator_of(doc.name) if not doc.is_new() else None
	if operator and doc.get("employee_number") and operator != doc.employee_number:
		frappe.throw(
			_("Employee Number {0} differs from operator code {1}. They must be the same code.").format(
				doc.employee_number, operator
			)
		)
	# ERPNext's on_update may switch the login off; remember how it was
	doc.flags.pepl_login_was_enabled = (
		cint(frappe.db.get_value("User", doc.user_id, "enabled")) if doc.get("user_id") else 0
	)


def on_employee_update(doc, method=None):
	"""doc_events: Employee on_update (after ERPNext's own on_update)."""
	keep_login(doc)
	leaver_todo(doc)
	link_operator(doc)


def keep_login(doc):
	"""ERPNext disabled the login because the Employee is not Active: PEPL keeps it on. Returns True if re-enabled."""
	if not doc.get("user_id") or doc.status == "Active" or not doc.flags.get("pepl_login_was_enabled"):
		return False
	if not params.is_enabled(KEEP_LOGIN_FIELD, 1):
		return False
	if cint(frappe.db.get_value("User", doc.user_id, "enabled")):
		return False
	frappe.db.set_value("User", doc.user_id, "enabled", 1)
	frappe.clear_cache(user=doc.user_id)
	return True


def leaver_todo(doc):
	if doc.status != "Left" or not doc.get("user_id"):
		return None
	before = doc.get_doc_before_save()
	if before and before.status == "Left":
		return None
	description = _(
		"{0} ({1}) has left (relieving date {2}). The login {3} stays enabled (PEPL, 26 Nov 2026); it is logged "
		"out after the idle time. Disable it in User if it should not be used again."
	).format(doc.employee_name, doc.name, doc.get("relieving_date") or "-", doc.user_id)
	return alerts.raise_todo(LEAVER_RULE, "Employee", doc.name, description, owner_field=LEAVER_TODO_FIELD)


def link_operator(doc):
	"""An operator whose code is this Employee's number, not yet linked, is linked now. Returns the operator."""
	number = doc.get("employee_number")
	if not number or operator_of(doc.name) or not frappe.db.exists(OPERATOR, number):
		return None
	if frappe.db.get_value(OPERATOR, number, "employee"):
		return None
	op = frappe.get_doc(OPERATOR, number)
	op.employee = doc.name
	op.flags.ignore_permissions = True
	op.save()
	return op.name


# ---------------- Make Operator ----------------
@frappe.whitelist()
def make_operator(employee):
	"""Create the PEPL Operator of an Employee (code = Employee Number). HR, Production or System Manager."""
	frappe.only_for(("HR Manager", "HR User", "Manufacturing Manager", "System Manager"))
	emp = frappe.get_doc("Employee", employee)
	if operator_of(emp.name):
		frappe.throw(_("{0} is already operator {1}.").format(emp.employee_name, operator_of(emp.name)))
	if not emp.employee_number:
		frappe.throw(_("Set the Employee Number first: it becomes the operator code."))
	if frappe.db.exists(OPERATOR, emp.employee_number):
		frappe.throw(_("Operator {0} already exists for someone else.").format(emp.employee_number))
	op = frappe.get_doc(
		{
			"doctype": OPERATOR,
			"employee_code": emp.employee_number,
			"operator_name": emp.employee_name,
			"employee": emp.name,
			"status": "Active",
		}
	)
	op.insert(ignore_permissions=True)
	return op.name


# ---------------- People Register ----------------
def register_rows():
	"""Every Employee, every operator without an Employee, every desk login without an Employee - with what is
	missing or wrong, in plain words."""
	rows = []
	operators = {o.employee: o for o in frappe.get_all(OPERATOR, fields=["name", "employee", "status"]) if o.employee}
	devices = set(device_roles())
	device_users = set(
		frappe.get_all("Has Role", filters={"role": ["in", list(devices)], "parenttype": "User"}, pluck="parent")
	)
	linked_users = set()
	for e in frappe.get_all(
		"Employee",
		fields=[
			"name",
			"employee_name",
			"employee_number",
			"department",
			"designation",
			"status",
			"user_id",
			"date_of_joining",
			"relieving_date",
		],
		order_by="employee_name",
	):
		gaps = []
		enabled = cint(frappe.db.get_value("User", e.user_id, "enabled")) if e.user_id else None
		if e.user_id:
			linked_users.add(e.user_id)
			if e.user_id in device_users:
				gaps.append(_("login is a device (kiosk) login"))
			if e.status == "Left" and enabled:
				gaps.append(_("has left, login still enabled"))
		if not e.employee_number:
			gaps.append(_("no Employee Number"))
		op = operators.get(e.name)
		if op and e.employee_number and op.name != e.employee_number:
			gaps.append(_("operator code {0} differs from Employee Number").format(op.name))
		rows.append(
			{
				"employee": e.name,
				"employee_name": e.employee_name,
				"employee_number": e.employee_number,
				"department": e.department,
				"designation": e.designation,
				"status": e.status,
				"person_type": LOGIN_USER if e.user_id else SHOP_FLOOR,
				"user_id": e.user_id,
				"login_enabled": "" if enabled is None else (_("Yes") if enabled else _("No")),
				"operator": op.name if op else "",
				"gaps": "; ".join(gaps),
			}
		)
	for o in frappe.get_all(
		OPERATOR, filters={"employee": ["is", "not set"]}, fields=["name", "operator_name", "status"]
	):
		rows.append(
			{
				"employee_name": o.operator_name,
				"status": o.status,
				"person_type": SHOP_FLOOR,
				"operator": o.name,
				"gaps": _("operator without an Employee"),
			}
		)
	for u in frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User", "name": ["not in", ["Administrator", "Guest"]]},
		fields=["name", "full_name"],
	):
		if u.name in linked_users or u.name in device_users:
			continue
		rows.append(
			{
				"employee_name": u.full_name,
				"person_type": LOGIN_USER,
				"user_id": u.name,
				"login_enabled": _("Yes"),
				"gaps": _("login without an Employee"),
			}
		)
	return rows
