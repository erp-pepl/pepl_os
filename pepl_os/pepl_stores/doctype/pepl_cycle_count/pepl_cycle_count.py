# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-20 - Cycle Count: blind count sheet, a reason for every variance, HOD approval above the limit."""

from frappe.model.document import Document

from pepl_os.pepl_stores import cycle_count


class PEPLCycleCount(Document):
	def validate(self):
		cycle_count.validate_count(self)

	def on_update(self):
		cycle_count.on_update_count(self)

	def before_submit(self):
		cycle_count.before_submit_count(self)

	def on_submit(self):
		cycle_count.on_submit_count(self)

	def on_cancel(self):
		cycle_count.on_cancel_count(self)
