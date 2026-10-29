"""C3a-B1 - /foreman: the foreman's view of one shift - which machines have entered, which are draft, which are missing."""

from urllib.parse import quote

import frappe
from frappe import _

from pepl_os.pepl_production.kiosk import FOREMAN_ROLES

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(frappe.request.full_path)
		raise frappe.Redirect
	context.no_cache = 1
	context.show_sidebar = False
	context.title = _("Foreman View")
	context.allowed = bool(set(FOREMAN_ROLES) & set(frappe.get_roles()))
	return context
