# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3b-Q2 - One calibration of an instrument, with its certificate and next due date."""

from frappe.model.document import Document

from pepl_os.pepl_quality import calibration


class PEPLCalibrationRecord(Document):
	def validate(self):
		calibration.validate_record(self)

	def before_submit(self):
		calibration.before_submit_record(self)

	def on_submit(self):
		calibration.on_submit_record(self)

	def on_cancel(self):
		calibration.on_cancel_record(self)
