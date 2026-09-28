"""A3 - Change tracking and view tracking.

track_changes: every field change is stored in Version with old and new value
and the user. track_views: every opening of the record is stored in View Log.
Applied on install and on every migrate; DocTypes that do not exist yet
(e.g. created in a later cycle) are skipped and picked up automatically on
the first migrate after they exist.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from pepl_os.setup.permissions import CORE_DOCTYPES

TRACK_CHANGES_DOCTYPES = CORE_DOCTYPES

TRACK_VIEWS_DOCTYPES = (
	"PEPL System Parameters",
	"PEPL Supplier Approval",  # created in Cycle 2 (C2-08)
	"Vendor Approval Status",
	"PEPL Payment Tracker",
)


def _ensure_doctype_flag(doctype, prop):
	if not frappe.db.exists("DocType", doctype):
		return False
	if frappe.get_meta(doctype).get(prop):
		return False
	make_property_setter(doctype, None, prop, 1, "Check", for_doctype=True)
	frappe.clear_cache(doctype=doctype)
	return True


def apply_property_setters():
	changed = []
	for doctype in TRACK_CHANGES_DOCTYPES:
		if _ensure_doctype_flag(doctype, "track_changes"):
			changed.append((doctype, "track_changes"))
	for doctype in TRACK_VIEWS_DOCTYPES:
		if _ensure_doctype_flag(doctype, "track_views"):
			changed.append((doctype, "track_views"))
	return changed
