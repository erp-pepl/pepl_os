# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-18 - Scrap weighment: gross - tare = net; submit puts it into stock."""

from frappe.model.document import Document

from pepl_os.pepl_stores import scrap


class PEPLScrapWeighment(Document):
	def validate(self):
		scrap.validate_weighment(self)

	def on_submit(self):
		scrap.on_submit_weighment(self)

	def on_cancel(self):
		scrap.on_cancel_weighment(self)
