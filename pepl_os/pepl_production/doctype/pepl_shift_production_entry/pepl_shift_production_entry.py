# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C3a-X1 - Shift Production Entry: one machine, one shift, one operator."""

from frappe.model.document import Document

from pepl_os.pepl_production import machine_week, oee, spr


class PEPLShiftProductionEntry(Document):
	def validate(self):
		spr.validate_entry(self)

	def before_submit(self):
		spr.before_submit(self)

	def on_submit(self):
		spr.on_submit(self)
		oee.on_entry_change(self)  # C3a-X3
		machine_week.on_entry_change(self)  # C3a-X4

	def before_cancel(self):
		spr.before_cancel(self)

	def on_cancel(self):
		spr.on_cancel(self)
		oee.on_entry_change(self)  # C3a-X3
		machine_week.on_entry_change(self)  # C3a-X4
