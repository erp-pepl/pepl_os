# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-08 - One approval record per supplier: document checklist, state and review date."""

from frappe.model.document import Document

from pepl_os.pepl_purchase import supplier_approval


class PEPLSupplierApproval(Document):
	def validate(self):
		supplier_approval.validate_approval(self)

	def on_update(self):
		supplier_approval.mirror_to_supplier(self)
