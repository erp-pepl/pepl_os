# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors

import frappe
from frappe import _
from frappe.model.document import Document

from pepl_os.common.overrides import MIN_REASON_LENGTH


class PEPLOverrideLog(Document):
	def validate(self):
		# Enforced here as well as in log_override(), so no code path can
		# store an override without a real reason.
		if len((self.reason or "").strip()) < MIN_REASON_LENGTH:
			frappe.throw(
				_("Please give a reason of at least {0} characters.").format(MIN_REASON_LENGTH),
				title=_("Reason required"),
			)
		if not self.user:
			self.user = frappe.session.user

		# An override record is evidence: once written its reason never changes.
		if not self.is_new() and self.has_value_changed("reason"):
			frappe.throw(_("An override reason cannot be changed after it is recorded."))
