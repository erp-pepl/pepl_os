# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3b-Q4 - One corrective and preventive action: five-why, root cause, actions, closing."""

from frappe.model.document import Document

from pepl_os.pepl_quality import capa


class PEPLCAPA(Document):
	def validate(self):
		capa.validate_capa(self)

	def on_update(self):
		capa.on_update_capa(self)
