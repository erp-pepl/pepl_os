# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3b-B1 - One inspection lot of a Sales Order line: lot request, proof, bulk lot offer, the agency's IC."""

from frappe.model.document import Document

from pepl_os.pepl_quality import inspection_lot


class PEPLInspectionLot(Document):
	def validate(self):
		inspection_lot.validate_lot(self)

	def on_update(self):
		inspection_lot.on_update_lot(self)
