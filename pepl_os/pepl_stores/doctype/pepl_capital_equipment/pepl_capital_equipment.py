# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-05 - Capital Equipment Register: one record per machine, instrument or vehicle."""

from frappe.model.document import Document

from pepl_os.pepl_stores.capital_equipment import core_document_gaps, cover_days_left


class PEPLCapitalEquipment(Document):
	def validate(self):
		missing = core_document_gaps(self)
		self.missing_documents = "\n".join(missing)
		self.document_status = "Missing" if missing else "Complete"
		self.warranty_days_left, self.amc_days_left = cover_days_left(self)
		if self.equipment_type != "Machine":
			self.workstation = None
