"""before_tests hook for pepl_os (runs once, before the pepl_os test suite).

The CI site is a bare install: ERPNext is installed but its setup wizard has
not run, so there is no Company, fiscal year, warehouse, supplier or item.
Importing erpnext.tests.utils builds ERPNext's own standard test data
(_Test Company, _Test Supplier, _Test Item, ...) exactly as ERPNext's CI does.
pepl_os setup is then applied to that data.
"""

import frappe

TEST_COMPANY = "_Test Company"


def before_tests():
	frappe.flags.in_test = True
	# ERPNext's test items use groups such as "_Test Item Group", outside PEPL's stock classes.
	frappe.flags.pepl_allow_items_outside_tree = True
	try:
		import erpnext.tests.utils  # the module import builds the test data
	finally:
		frappe.flags.pepl_allow_items_outside_tree = False

	from pepl_os.install import ensure_setup
	from pepl_os.pepl_stores.stock_tree import seed_stock_structure

	ensure_setup()
	seed_stock_structure(TEST_COMPANY)
	_notification_owner()
	_outgoing_email_account()
	frappe.db.commit()


FALLBACK_OWNER = "pepl.test.owner@example.com"


def _notification_owner():
	"""A live site names who receives each kind of ToDo; on the bare test site one user takes them all."""
	from pepl_os.tests.utils import SYSTEM_PARAMETERS, make_user

	make_user(FALLBACK_OWNER, ["System Manager"])
	frappe.db.set_single_value(SYSTEM_PARAMETERS, "notification_fallback_owner", FALLBACK_OWNER)


TEST_EMAIL_ACCOUNT = "PEPL Test Outgoing"


def _outgoing_email_account():
	"""The chase letter and RFQ e-mails need a default outgoing e-mail account, as on the live site.
	In tests Frappe skips the SMTP check and sends nothing; the e-mail is only queued."""
	if frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1}):
		return
	frappe.get_doc(
		{
			"doctype": "Email Account",
			"email_account_name": TEST_EMAIL_ACCOUNT,
			"email_id": "pepl.test.outgoing@example.com",
			"enable_outgoing": 1,
			"default_outgoing": 1,
			"smtp_server": "localhost",
			"smtp_port": 25,
			"no_smtp_authentication": 1,
		}
	).insert(ignore_permissions=True)
