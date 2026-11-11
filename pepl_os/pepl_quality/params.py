"""Cycle 3b - Server validation of the Quality rulebook in PEPL System Parameters."""

import frappe

from pepl_os.pepl_quality import incoming_qc


def validate_quality_params(doc, method=None):
	errors = []
	errors += incoming_qc.validate_params(doc)  # C3b-Q1
	if errors:
		frappe.throw("<br>".join(errors), title=frappe._("Check the Quality settings"))
