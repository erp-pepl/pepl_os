"""Values added to frappe.boot for pepl_os client scripts."""

from pepl_os.common import params
from pepl_os.common.letterhead import LETTERHEAD_FORMATS


def boot_session(bootinfo):
	bootinfo.pepl_supplier_doc_alert_days = params.get_int("custom_supplier_doc_expiry_alert_days", 30)
	# C2-24: the print page's Print button prints these on the PEPL letterhead
	bootinfo.pepl_letterhead_formats = list(LETTERHEAD_FORMATS)
