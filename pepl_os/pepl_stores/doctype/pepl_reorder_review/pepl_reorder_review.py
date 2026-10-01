# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-19 - Reorder Review: suggested levels from consumption, approved by the Stores HOD."""

from frappe.model.document import Document

from pepl_os.pepl_stores import reorder


class PEPLReorderReview(Document):
	def validate(self):
		reorder.validate_review(self)

	def on_submit(self):
		reorder.on_submit_review(self)
