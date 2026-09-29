"""Values added to frappe.boot for pepl_os client scripts."""

from pepl_os.common import params


def boot_session(bootinfo):
	bootinfo.pepl_supplier_doc_alert_days = params.get_int("custom_supplier_doc_expiry_alert_days", 30)
