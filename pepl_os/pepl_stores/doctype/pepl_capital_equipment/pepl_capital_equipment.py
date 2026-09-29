# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-05 - Capital Equipment Register: one record per machine, instrument or vehicle."""

from frappe.model.document import Document

from pepl_os.pepl_stores.capital_equipment import core_document_gaps, cover_days_left, stored_days


class PEPLCapitalEquipment(Document):
	def validate(self):
		missing = core_document_gaps(self)
		self.missing_documents = "\n".join(missing)
		self.document_status = "Missing" if missing else "Complete"
		warranty, amc = cover_days_left(self)
		self.warranty_days_left, self.amc_days_left = stored_days(warranty), stored_days(amc)
		if self.equipment_type != "Machine":
			self.workstation = None
