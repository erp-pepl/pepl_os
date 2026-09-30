# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-10 - All quotations for one RFQ side by side; approval creates the Purchase Orders."""

from frappe.model.document import Document

from pepl_os.pepl_purchase import quotation_comparison as qc


class PEPLQuotationComparison(Document):
	def before_insert(self):
		qc.before_insert(self)

	def validate(self):
		qc.validate(self)

	def before_submit(self):
		qc.before_submit(self)

	def on_submit(self):
		qc.on_submit(self)

	def before_cancel(self):
		qc.before_cancel(self)

	def on_cancel(self):
		qc.on_cancel(self)
