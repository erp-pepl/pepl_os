# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3b-Q2 - One gauge or measuring instrument and its calibration state."""

from frappe.model.document import Document

from pepl_os.pepl_quality import calibration


class PEPLInstrument(Document):
	def validate(self):
		calibration.validate_instrument(self)

	def on_update(self):
		calibration.refresh_alert(self.name)
