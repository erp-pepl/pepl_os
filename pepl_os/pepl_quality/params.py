"""Cycle 3b - Server validation of the Quality rulebook in PEPL System Parameters."""

import frappe

from pepl_os.pepl_quality import calibration, capa, dispatch, incoming_qc, ncr, scorecard


def validate_quality_params(doc, method=None):
	errors = []
	errors += incoming_qc.validate_params(doc)  # C3b-Q1
	errors += calibration.validate_params(doc)  # C3b-Q2
	errors += ncr.validate_params(doc)  # C3b-Q3
	errors += capa.validate_params(doc)  # C3b-Q4
	errors += dispatch.validate_params(doc)  # C3b-Q5
	errors += scorecard.validate_params(doc)  # C3b-Q6
	if errors:
		frappe.throw("<br>".join(errors), title=frappe._("Check the Quality settings"))
