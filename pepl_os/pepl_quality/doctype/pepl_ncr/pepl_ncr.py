# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3b-Q3 - One non-conformance, its disposition and its sign-offs by severity."""

from frappe.model.document import Document

from pepl_os.pepl_quality import ncr


class PEPLNCR(Document):
	def validate(self):
		ncr.validate_ncr(self)

	def on_update(self):
		ncr.on_update_ncr(self)
