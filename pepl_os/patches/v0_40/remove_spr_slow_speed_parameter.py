"""C3a-C1 - One measure for "slower or faster than standard".

v0.39.0 (C3a-P5) added "Shift Entry: Slow Below % of Standard Speed". The same question is answered by the
pepl_sales parameters "Cycle Deviation Threshold Low / High" (actual cycle against standard x 0.8 / x 1.2), which
the standard-time governance also uses, so the extra field is removed: one threshold, one place.
"""

import frappe

PARAMS = "PEPL System Parameters"
FIELD = "custom_spr_slow_speed_percent"


def execute():
	name = frappe.db.get_value("Custom Field", {"dt": PARAMS, "fieldname": FIELD}, "name")
	if name:
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
	frappe.db.delete("Singles", {"doctype": PARAMS, "field": FIELD})
	frappe.clear_cache(doctype=PARAMS)
