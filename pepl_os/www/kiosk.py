"""C3a-B1 - /kiosk?machine=<Workstation>: the shift-entry page beside one machine (see pepl_production.kiosk)."""

from urllib.parse import quote

import frappe
from frappe import _

from pepl_os.pepl_production.kiosk import KIOSK_ROLES

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(frappe.request.full_path)
		raise frappe.Redirect
	context.no_cache = 1
	context.show_sidebar = False
	context.title = _("Shift Entry Kiosk")
	context.allowed = bool(set(KIOSK_ROLES) & set(frappe.get_roles()))
	context.machine = frappe.form_dict.get("machine") or ""
	context.machines = (
		frappe.get_all("Workstation", filters={"disabled": 0}, pluck="name", order_by="name")
		if context.allowed and not context.machine
		else []
	)
	return context
