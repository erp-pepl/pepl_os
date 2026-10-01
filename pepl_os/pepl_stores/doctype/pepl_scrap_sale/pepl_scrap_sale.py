# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-18 - Scrap sale: submit takes it out of stock; prints a gate pass."""

from frappe.model.document import Document

from pepl_os.pepl_stores import scrap


class PEPLScrapSale(Document):
	def validate(self):
		scrap.validate_sale(self)

	def on_submit(self):
		scrap.on_submit_sale(self)

	def on_cancel(self):
		scrap.on_cancel_sale(self)
