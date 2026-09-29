"""C2-02 - Server validation of the Purchase & Stores rulebook in PEPL System Parameters."""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pepl_os.setup.custom_fields import PURCHASE_STORES_FIELDS


def _fields_of_type(fieldtype):
	return [f for f in PURCHASE_STORES_FIELDS if f["fieldtype"] == fieldtype]


def validate_purchase_params(doc, method=None):
	"""Refuse values that would break a rule: negative days, % outside 0-100, A + B >= 100."""
	errors = []
	for field in _fields_of_type("Int"):
		value = doc.get(field["fieldname"])
		if value not in (None, "") and cint(value) < 0:
			errors.append(_("{0} cannot be negative.").format(_(field["label"])))

	for field in _fields_of_type("Percent"):
		value = doc.get(field["fieldname"])
		if value not in (None, "") and not 0 <= flt(value) <= 100:
			errors.append(_("{0} must be between 0 and 100.").format(_(field["label"])))

	for field in _fields_of_type("Currency"):
		value = doc.get(field["fieldname"])
		if value not in (None, "") and flt(value) < 0:
			errors.append(_("{0} cannot be negative.").format(_(field["label"])))

	a, b = flt(doc.get("custom_abc_a_value_percent")), flt(doc.get("custom_abc_b_value_percent"))
	if a + b >= 100:
		errors.append(
			_("Class A % ({0}) plus Class B % ({1}) must be below 100, so that class C exists.").format(a, b)
		)

	seen = set()
	for row in doc.get("custom_machine_hour_rates") or []:
		group = (row.machine_group or "").strip().lower()
		if group in seen:
			errors.append(
				_("Machine group {0} is listed twice in Machine-Hour Rates.").format(row.machine_group)
			)
		seen.add(group)
		if flt(row.rate_per_hour) < 0:
			errors.append(_("Machine-hour rate for {0} cannot be negative.").format(row.machine_group))

	if errors:
		frappe.throw("<br>".join(errors), title=_("Purchase & Stores rules"))
