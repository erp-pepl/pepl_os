"""C2-03 - Supplier: criticality, MSME, RM groups; approval fields are filled by C2-08."""

import re

import frappe
from frappe import _

UDYAM_PATTERN = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")

APPROVED_STATES = ("Approved", "Conditionally Approved")
BLOCKED_STATES = ("Suspended", "Expired", "Rejected")


def validate_supplier(doc, method=None):
	if doc.get("custom_is_msme"):
		udyam = (doc.get("custom_udyam_number") or "").strip().upper()
		if not udyam:
			frappe.throw(
				_("Udyam Registration Number is required when the supplier is MSME."),
				title=_("MSME supplier"),
			)
		if not UDYAM_PATTERN.match(udyam):
			frappe.throw(
				_("Udyam Registration Number {0} is not in the format UDYAM-XX-00-0000000.").format(udyam),
				title=_("MSME supplier"),
			)
		doc.custom_udyam_number = udyam
	else:
		doc.custom_msme_category = None

	if not doc.get("custom_vendor_criticality"):
		doc.custom_vendor_criticality = "Routine"
