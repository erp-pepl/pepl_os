# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-18 - Scrap rate per kg from a date."""

from frappe.model.document import Document

from pepl_os.pepl_stores import scrap


class PEPLScrapRate(Document):
	def validate(self):
		scrap.validate_rate(self)
