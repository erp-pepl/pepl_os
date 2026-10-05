"""Test helpers shared by every pepl_os test."""

import frappe

try:  # Frappe v15.x+ / v16: the current base class.
	from frappe.tests import IntegrationTestCase as _FrappeTestCase
except ImportError:  # Older releases (the class pepl_sales uses).
	from frappe.tests.utils import FrappeTestCase as _FrappeTestCase

_EACH_TEST = "pepl_each_test"


class PEPLTestCase(_FrappeTestCase):
	"""Frappe's test case, plus: every test starts from the same data.

	Frappe rolls back only at the end of a test class, so two tests in one class that each post stock
	or create a review would see each other's records. Here every test runs inside a savepoint that is
	rolled back afterwards; what setUpClass created stays for the whole class.
	"""

	def _callSetUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint(_EACH_TEST)
		super()._callSetUp()

	def _callTearDown(self):
		try:
			super()._callTearDown()
		finally:
			frappe.set_user("Administrator")
			try:
				frappe.db.rollback(save_point=_EACH_TEST)
			except Exception:
				pass  # a commit or schema change inside the test ended the savepoint; the class rollback remains
			frappe.cache.delete_keys("document_cache::")  # cached copies of rolled-back records


def reopen(doc):
	"""After a save that was refused on purpose, let the same in-memory doc be saved again.

	A refused save has already stamped the doc with a new modified time, which Frappe would read as
	"changed by someone else". The form in the browser never has this problem.
	"""
	doc.modified = frappe.db.get_value(doc.doctype, doc.name, "modified")
	return doc


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
