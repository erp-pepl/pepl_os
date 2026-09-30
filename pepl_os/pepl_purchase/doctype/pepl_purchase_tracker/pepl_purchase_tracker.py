# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""C2-12 - One tracker per submitted Purchase Order, recomputed line by line against the promised dates."""

from frappe.model.document import Document

from pepl_os.pepl_purchase import tracker


class PEPLPurchaseTracker(Document):
	def validate(self):
		tracker.compute(self, as_of=self.flags.as_of)
