# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-X2 - Shift: start, end and breaks; planned production minutes for OEE."""

from frappe.model.document import Document

from pepl_os.pepl_production import masters


class PEPLShift(Document):
	def validate(self):
		masters.validate_shift(self)
