"""C4-H5 - Statutory register data on the Employee (PF / ESIC / PAN / Aadhaar / bank), payroll-ready, protected.

PEPL (25 / 26 Nov 2026): the CEO sees attendance and leave but not PF / ESIC / PAN / bank; Aadhaar: store the number
only (no copies). Payroll and the statutory returns (ECR, ESIC challan) stay out of scope - this captures the data.

* Fields (Employee, tab "Statutory"): PF applicable, UAN (12 digits, unique), PF number (Frappe HR's "Provident Fund
  Account"), PF joining date, EPS applicable, ESIC applicable, ESIC IP number (10 digits, unique), ESIC dispensary,
  PAN (Frappe HR's "PAN Number", format AAAAA9999A), Aadhaar (encrypted, Verhoeff check, shown as XXXX XXXX 1234),
  father's / husband's name.
* Permission level 6 = statutory: the fields above plus ERPNext / Frappe HR's bank fields (bank name, account no.,
  IBAN, IFSC, MICR) and Cost to Company. Only HR Manager (PEPL HR Manager) and System Manager read and write level 6;
  everybody else - the CEO, the HR Assistant, the department heads - sees the Employee without them.
* The full Aadhaar number is shown only on request (button "Show Aadhaar", HR Manager / System Manager), and each
  showing is recorded (Access Log + a comment on the Employee naming who saw it, without the number).
* Report PEPL Statutory Data Readiness: what each active Employee still lacks.
"""

import re

import frappe
from frappe import _
from frappe.permissions import add_permission
from frappe.utils import cint, now

from pepl_os.pepl_governance.access_plan import set_right

EMPLOYEE = "Employee"
LEVEL = 6
LEVEL_ROLES = ("HR Manager", "System Manager")
# Fields that exist already (ERPNext core, Frappe HR's India set-up) moved to level 6 by Property Setter
PROTECTED_EXISTING = (
	"bank_name",
	"bank_ac_no",
	"iban",
	"ifsc_code",
	"micr_code",
	"pan_number",
	"ctc",
	"provident_fund_account",
)
AADHAAR = "custom_aadhaar"
AADHAAR_MASKED = "custom_aadhaar_masked"
UAN = "custom_uan"
ESIC_IP = "custom_esic_ip_number"

# ---------------- Verhoeff (the Aadhaar check digit) ----------------
_D = (
	(0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
	(1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
	(2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
	(3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
	(4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
	(5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
	(6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
	(7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
	(8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
	(9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
	(0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
	(1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
	(5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
	(8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
	(9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
	(4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
	(2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
	(7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def verhoeff_ok(number):
	c = 0
	for i, digit in enumerate(reversed(str(number))):
		c = _D[c][_P[i % 8][int(digit)]]
	return c == 0


def aadhaar_ok(number):
	"""12 digits, not starting with 0 or 1, valid Verhoeff check digit."""
	return bool(re.fullmatch(r"[2-9]\d{11}", number or "")) and verhoeff_ok(number)


def digits(value):
	return re.sub(r"[\s-]", "", str(value or ""))


def masked(number):
	return "XXXX XXXX " + number[-4:] if number else ""


def is_unchanged_password(value):
	"""Frappe keeps a saved Password field as asterisks in the form."""
	return bool(value) and set(str(value)) == {"*"}


# ---------------- Employee validate ----------------
def validate_employee(doc, method=None):
	"""doc_events: Employee validate - formats, uniqueness, Aadhaar check and mask."""
	errors = []
	uan = digits(doc.get(UAN))
	if uan:
		if not re.fullmatch(r"\d{12}", uan):
			errors.append(_("UAN must be 12 digits ({0}).").format(doc.get(UAN)))
		elif other := frappe.db.get_value(EMPLOYEE, {UAN: uan, "name": ["!=", doc.name or ""]}, "name"):
			errors.append(_("UAN {0} is already on Employee {1}.").format(uan, other))
		doc.set(UAN, uan)
	ip = digits(doc.get(ESIC_IP))
	if ip:
		if not re.fullmatch(r"\d{10}", ip):
			errors.append(_("ESIC IP Number must be 10 digits ({0}).").format(doc.get(ESIC_IP)))
		elif other := frappe.db.get_value(EMPLOYEE, {ESIC_IP: ip, "name": ["!=", doc.name or ""]}, "name"):
			errors.append(_("ESIC IP Number {0} is already on Employee {1}.").format(ip, other))
		doc.set(ESIC_IP, ip)
	if doc.meta.has_field("pan_number") and doc.get("pan_number"):
		pan = str(doc.pan_number).strip().upper()
		if not re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", pan):
			errors.append(_("PAN must look like ABCDE1234F ({0}).").format(doc.pan_number))
		doc.pan_number = pan
	value = doc.get(AADHAAR)
	if value and not is_unchanged_password(value):
		number = digits(value)
		if not aadhaar_ok(number):
			errors.append(_("The Aadhaar number is not valid (12 digits with a correct check digit)."))
		else:
			doc.set(AADHAAR, number)
			doc.set(AADHAAR_MASKED, masked(number))
	elif not value:
		doc.set(AADHAAR_MASKED, "")
	if errors:
		frappe.throw("<br>".join(errors), title=_("Statutory details"))


# ---------------- access ----------------
def ensure_statutory_access():
	"""Level 6 on Employee: HR Manager and System Manager read + write; no other role. Existing fields moved to level
	6. Safe on every migrate. Returns what changed."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	changed = []
	if not frappe.db.exists("DocType", EMPLOYEE):
		return changed
	meta = frappe.get_meta(EMPLOYEE)
	for field in PROTECTED_EXISTING:
		df = meta.get_field(field)
		if df and cint(df.permlevel) != LEVEL:
			make_property_setter(
				EMPLOYEE, field, "permlevel", LEVEL, "Int", validate_fields_for_doctype=False
			)
			changed.append(field)
	for role in LEVEL_ROLES:
		if not frappe.db.exists("Role", role):
			continue
		if not frappe.db.exists("Custom DocPerm", {"parent": EMPLOYEE, "role": role, "permlevel": LEVEL}):
			add_permission(EMPLOYEE, role, LEVEL)
			changed.append(f"{role} level {LEVEL}")
		row = frappe.get_value(
			"Custom DocPerm",
			{"parent": EMPLOYEE, "role": role, "permlevel": LEVEL},
			["read", "write"],
			as_dict=True,
		)
		if row and not (row.read and row.write):
			set_right(EMPLOYEE, role, LEVEL, 0, "read", 1)
			set_right(EMPLOYEE, role, LEVEL, 0, "write", 1)
	for name in frappe.get_all(
		"Custom DocPerm",
		filters={"parent": EMPLOYEE, "permlevel": LEVEL, "role": ["not in", list(LEVEL_ROLES)]},
		pluck="name",
	):
		frappe.delete_doc("Custom DocPerm", name, ignore_permissions=True, force=True)
		changed.append(f"removed {name}")
	if changed:
		frappe.clear_cache(doctype=EMPLOYEE)
	return changed


def level_roles():
	return sorted(
		frappe.get_all(
			"Custom DocPerm",
			filters={"parent": EMPLOYEE, "permlevel": LEVEL, "read": 1},
			pluck="role",
			distinct=True,
		)
	)


# ---------------- Show Aadhaar ----------------
@frappe.whitelist()
def show_aadhaar(employee):
	"""The full Aadhaar number, for HR Manager / System Manager only; every showing is recorded."""
	frappe.only_for(LEVEL_ROLES)
	doc = frappe.get_doc(EMPLOYEE, employee)
	number = doc.get_password(AADHAAR, raise_exception=False)
	if not number:
		return None
	frappe.get_doc(
		{
			"doctype": "Access Log",
			"user": frappe.session.user,
			"export_from": EMPLOYEE,
			"reference_document": employee,
			"timestamp": now(),
			"method": "Show Aadhaar",
		}
	).insert(ignore_permissions=True)
	doc.add_comment("Info", _("Aadhaar number shown to {0}").format(frappe.session.user))
	return number


# ---------------- readiness ----------------
READINESS = (
	("custom_father_or_husband_name", "father's / husband's name"),
	("date_of_birth", "date of birth"),
	("pan_number", "PAN"),
	(AADHAAR_MASKED, "Aadhaar"),
	("bank_ac_no", "bank account"),
	("ifsc_code", "IFSC"),
)


def readiness_rows(status="Active"):
	"""One row per Employee: the statutory details on file and what is still missing."""
	fields = [
		"name",
		"employee_name",
		"employee_number",
		"department",
		"date_of_joining",
		"custom_pf_applicable",
		UAN,
		"custom_esic_applicable",
		ESIC_IP,
		*[f for f, _label in READINESS],
	]
	meta = frappe.get_meta(EMPLOYEE)
	fields = [f for f in fields if f == "name" or meta.has_field(f)]
	rows = []
	for e in frappe.get_all(
		EMPLOYEE, filters={"status": status} if status else {}, fields=fields, order_by="employee_name"
	):
		missing = [label for f, label in READINESS if meta.has_field(f) and not e.get(f)]
		if cint(e.get("custom_pf_applicable")):
			if not e.get(UAN):
				missing.append(_("UAN"))
			if meta.has_field("provident_fund_account") and not frappe.db.get_value(
				EMPLOYEE, e.name, "provident_fund_account"
			):
				missing.append(_("PF number"))
		if cint(e.get("custom_esic_applicable")) and not e.get(ESIC_IP):
			missing.append(_("ESIC IP number"))
		e["missing"] = ", ".join(missing)
		rows.append(e)
	return rows
