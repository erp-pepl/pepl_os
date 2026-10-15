# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-X2 - Shop-floor operator: kiosk PIN and machine-group skills."""

from frappe.model.document import Document

from pepl_os.pepl_production import masters


class PEPLOperator(Document):
	def validate(self):
		masters.validate_operator(self)
