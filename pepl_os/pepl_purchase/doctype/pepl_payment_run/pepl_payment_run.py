# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-17 - the weekly Payment Run: the worklist approved by the Purchase Manager, paid by Accounts."""

from frappe.model.document import Document

from pepl_os.pepl_purchase import payments


class PEPLPaymentRun(Document):
	def validate(self):
		payments.validate_run(self)

	def before_submit(self):
		payments.before_submit_run(self)

	def on_submit(self):
		payments.on_submit_run(self)

	def on_cancel(self):
		payments.on_cancel_run(self)
