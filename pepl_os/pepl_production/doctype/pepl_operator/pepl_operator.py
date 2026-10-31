# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-X2 - Shop-floor operator: kiosk PIN and machine-group skills. C3a-B3: Employee link and eligible shifts."""

from frappe.model.document import Document

from pepl_os.pepl_production import hr_lite, masters


class PEPLOperator(Document):
	def validate(self):
		hr_lite.align_with_employee(self)  # C3a-B3: the Employee leads name, joining date, login, status
		masters.validate_operator(self)
		hr_lite.check_eligible_shifts(self)  # C3a-B3
