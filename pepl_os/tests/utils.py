"""Test helpers shared by every pepl_os test."""

import frappe

try:  # Frappe v15.x+ / v16: the current base class.
	from frappe.tests import IntegrationTestCase as PEPLTestCase
except ImportError:  # Older releases (the class pepl_sales uses).
	from frappe.tests.utils import FrappeTestCase as PEPLTestCase

SYSTEM_PARAMETERS = "PEPL System Parameters"


def set_param(fieldname, value):
	"""Set a System Parameter in a test and make sure the next read sees it."""
	frappe.db.set_single_value(SYSTEM_PARAMETERS, fieldname, value)
	frappe.clear_document_cache(SYSTEM_PARAMETERS, SYSTEM_PARAMETERS)
	cache = getattr(frappe.db, "value_cache", None)
	if isinstance(cache, dict):
		cache.clear()


def make_user(email, roles=None):
	"""Create (once) a plain System User with the given roles."""
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		user.insert(ignore_permissions=True)
		if roles:
			user.add_roles(*roles)
	return email
