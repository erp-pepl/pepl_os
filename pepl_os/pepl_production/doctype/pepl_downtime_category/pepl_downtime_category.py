# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-X2 - Downtime category: planned / unplanned / PM, and whether it is a breakdown (MTBF / MTTR)."""

from frappe.model.document import Document

from pepl_os.pepl_production import masters


class PEPLDowntimeCategory(Document):
	def validate(self):
		masters.validate_downtime_category(self)
