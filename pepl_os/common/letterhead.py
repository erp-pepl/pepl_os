"""C2-24 - Purchase and Stores documents on the official PEPL letterhead.

The same method Cycle 1 uses for its generated documents (pepl_sales):

1. each PEPL print format reserves the letterhead bands with page margins on `.print-format`
   (60 mm top, 34 mm bottom, 14 mm sides);
2. the page is turned into a PDF by wkhtmltopdf;
3. trailing pages with no text are dropped, so no blank sheet goes out;
4. the controlled letterhead PDF shipped with pepl_sales is laid BEHIND every page,
   so nothing in the document can ever be hidden by the artwork.

Where it applies (only for the formats in LETTERHEAD_FORMATS; every other print is untouched):
- the PDF button in the Print view (frappe.utils.print_format.download_pdf, overridden),
- "Download PDF for Supplier" on the RFQ (erpnext ... request_for_quotation.get_pdf, overridden),
- the RFQ e-mail to suppliers (PEPLRequestforQuotation.send_email),
- the vendor chase e-mail (chase.chase_vendor).
The browser Print button prints the page without the artwork, with the bands left blank,
which suits paper that already carries the letterhead.
"""

from io import BytesIO

import frappe
from frappe import _

LETTERHEAD_APP = "pepl_sales"
LETTERHEAD_FILE = "PEPL_Letterhead_Plain.pdf"

LETTERHEAD_FORMATS = (
	"PEPL Purchase Order",
	"PEPL RFQ Cover Letter",
	"PEPL Vendor Chase Letter",
	"PEPL Scrap Gate Pass",
	"PEPL Scrap Weighment Slip",
	"PEPL Blind Count Sheet",
	"PEPL CSM Return Challan",
)

# The default print format of these DocTypes is set to the PEPL one (once; a later choice stays).
DEFAULT_FORMATS = {
	"Purchase Order": "PEPL Purchase Order",
	"Request for Quotation": "PEPL RFQ Cover Letter",
	"PEPL Scrap Weighment": "PEPL Scrap Weighment Slip",
	"PEPL Scrap Sale": "PEPL Scrap Gate Pass",
	"PEPL Cycle Count": "PEPL Blind Count Sheet",
}

# Same values as Cycle 1 and as the `.print-format` rule inside each print format.
PDF_OPTIONS = {
	"page-size": "A4",
	"margin-top": "60mm",
	"margin-bottom": "34mm",
	"margin-left": "14mm",
	"margin-right": "14mm",
}


def uses_letterhead(print_format):
	return print_format in LETTERHEAD_FORMATS


def default_format(doctype):
	return frappe.get_meta(doctype).default_print_format or "Standard"


def letterhead_path():
	return frappe.get_app_path(LETTERHEAD_APP, "public", "letterhead", LETTERHEAD_FILE)


def _letterhead_bytes():
	try:
		with open(letterhead_path(), "rb") as f:
			content = f.read()
	except OSError as exc:
		frappe.throw(_("The official PEPL letterhead file could not be read: {0}").format(exc))
	if not content:
		frappe.throw(_("The official PEPL letterhead PDF is empty."))
	return content


def drop_blank_tail(pages):
	"""Drop trailing pages that carry no text. At least one page is always kept."""
	pages = list(pages)
	while len(pages) > 1:
		try:
			text = (pages[-1].extract_text() or "").strip()
		except Exception:
			break
		if text:
			break
		pages.pop()
	return pages


def stamp(pdf_content):
	"""Lay the official letterhead behind every page of `pdf_content`; returns the new PDF bytes."""
	from pypdf import PdfReader, PdfWriter

	letterhead = _letterhead_bytes()
	pages = drop_blank_tail(PdfReader(BytesIO(pdf_content)).pages)
	if not pages:
		frappe.throw(_("The document PDF has no pages."))
	probe = PdfReader(BytesIO(letterhead)).pages[0]
	width, height = float(probe.mediabox.width), float(probe.mediabox.height)
	writer = PdfWriter()
	for page in pages:
		if abs(float(page.mediabox.width) - width) > 5 or abs(float(page.mediabox.height) - height) > 5:
			frappe.throw(_("The document is not A4, so it cannot go on the PEPL letterhead."))
		# a fresh copy each time: merge_page changes the page it is called on
		base = PdfReader(BytesIO(letterhead)).pages[0]
		base.merge_page(page, over=True)
		writer.add_page(base)
	out = BytesIO()
	writer.write(out)
	return out.getvalue()


def render(doctype, name, print_format=None, doc=None, language=None):
	"""The document as a PDF on the letterhead (bytes)."""
	from frappe.translate import print_language
	from frappe.utils.pdf import get_pdf

	print_format = print_format or default_format(doctype)
	with print_language(language or frappe.local.lang):
		html = frappe.get_print(
			doctype, name, print_format, doc=doc, no_letterhead=1, pdf_generator="wkhtmltopdf"
		)
		pdf = get_pdf(html, options=dict(PDF_OPTIONS))
	return stamp(pdf)


def file_name(name):
	return name.replace(" ", "-").replace("/", "-") + ".pdf"


@frappe.whitelist(allow_guest=True)
def download_pdf(
	doctype,
	name,
	format=None,
	doc=None,
	no_letterhead=0,
	language=None,
	letterhead=None,
	pdf_generator=None,
):
	"""Override of frappe.utils.print_format.download_pdf (the Print view's PDF button).

	PEPL letterhead formats come back on the letterhead; every other print goes to Frappe unchanged.
	"""
	if not uses_letterhead(format or default_format(doctype)):
		from frappe.utils.print_format import download_pdf as frappe_download_pdf

		return frappe_download_pdf(
			doctype,
			name,
			format=format,
			doc=doc,
			no_letterhead=no_letterhead,
			language=language,
			letterhead=letterhead,
			pdf_generator=pdf_generator,
		)
	from frappe.www.printview import validate_print_permission

	doc = doc or frappe.get_doc(doctype, name)
	validate_print_permission(doc)
	frappe.local.response.filename = file_name(name)
	frappe.local.response.filecontent = render(doctype, name, format, doc=doc, language=language)
	frappe.local.response.type = "pdf"


@frappe.whitelist()
def rfq_pdf(name, supplier=None, print_format=None, language=None, letterhead=None):
	"""Override of ERPNext's "Download PDF for Supplier" on the Request for Quotation."""
	print_format = print_format or default_format("Request for Quotation")
	if not uses_letterhead(print_format):
		from erpnext.buying.doctype.request_for_quotation.request_for_quotation import get_pdf

		return get_pdf(name, supplier, print_format=print_format, language=language, letterhead=letterhead)
	from frappe.www.printview import validate_print_permission

	doc = frappe.get_doc("Request for Quotation", name)
	validate_print_permission(doc)
	if supplier:
		doc.update_supplier_part_no(supplier)  # also sets doc.vendor, which the cover letter is addressed to
	content = render(doc.doctype, doc.name, print_format, doc=doc, language=language)
	frappe.local.response.filename = file_name(f"{name}-{supplier}" if supplier else name)
	frappe.local.response.filecontent = content
	frappe.local.response.type = "pdf"


def swap_print_attachment(doc, attachments):
	"""In an e-mail's attachments, replace the plain print of `doc` with the letterhead PDF."""
	print_format = default_format(doc.doctype)
	if not uses_letterhead(print_format):
		return attachments
	plain = doc.name.replace(" ", "").replace("/", "-")
	out = []
	for a in attachments or []:
		if isinstance(a, dict) and a.get("fname") in (f"{plain}.pdf", f"{plain}.html"):
			a = {
				"fname": file_name(doc.name),
				"fcontent": render(doc.doctype, doc.name, print_format, doc=doc),
			}
		out.append(a)
	return out


def ensure_default_print_formats():
	"""Install / migrate: make the PEPL format the default where none has been chosen yet."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	changed = []
	for doctype, print_format in DEFAULT_FORMATS.items():
		if not (frappe.db.exists("DocType", doctype) and frappe.db.exists("Print Format", print_format)):
			continue
		if frappe.get_meta(doctype).default_print_format:
			continue
		make_property_setter(doctype, None, "default_print_format", print_format, "Data", for_doctype=True)
		frappe.clear_cache(doctype=doctype)
		changed.append(doctype)
	# the RFQ e-mail attaches the cover letter unless the buyer unticks "Send Document Print"
	rfq = "Request for Quotation"
	if not frappe.db.exists(
		"Property Setter", {"doc_type": rfq, "field_name": "send_document_print", "property": "default"}
	):
		make_property_setter(rfq, "send_document_print", "default", "1", "Text")
		frappe.clear_cache(doctype=rfq)
		changed.append(f"{rfq}.send_document_print")
	return changed


# Jinja ---------------------------------------------------------------------------------


def pepl_rfq_letter(doc):
	"""For the RFQ Cover Letter: who it is addressed to and the message, rendered.

	ERPNext sets doc.vendor to the supplier chosen in "Download PDF for Supplier" and to each
	supplier as it is e-mailed. Otherwise an RFQ with one supplier is addressed to that supplier,
	and one with several to "Dear Supplier".
	"""
	rows = doc.get("suppliers") or []
	supplier = doc.get("vendor")
	if supplier not in [r.supplier for r in rows]:
		supplier = None
	if not supplier and len(rows) == 1:
		supplier = rows[0].supplier
	out = frappe._dict(supplier=supplier, supplier_name=None, address=None, contact=None, message=None)
	if supplier:
		out.supplier_name = frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier
		address = frappe.db.get_value("Supplier", supplier, "supplier_primary_address")
		if address:
			from frappe.contacts.doctype.address.address import get_address_display

			out.address = get_address_display(address)
		for row in rows:
			if row.supplier == supplier and row.get("contact"):
				out.contact = frappe.db.get_value("Contact", row.contact, "full_name") or row.contact
	message = doc.get("message_for_supplier") or ""
	if "{" in message:
		try:
			message = frappe.render_template(
				message,
				{
					"doc": doc,
					"supplier": out.supplier_name or "",
					"supplier_name": out.supplier_name or "",
					"supplier_salutation": out.contact or _("Sir / Madam"),
				},
				restrict_globals=True,
			)
		except Exception:
			pass
	out.message = message
	return out


@frappe.whitelist()
def inspect_pdf(doctype, name, print_format=None):
	"""For the System Console check and for support: make the letterhead PDF and say what is in it."""
	import os

	from pypdf import PdfReader

	frappe.only_for("System Manager")
	pdf = render(doctype, name, print_format)
	texts = [" ".join((p.extract_text() or "").split()) for p in PdfReader(BytesIO(pdf)).pages]
	overrides = frappe.get_hooks("override_whitelisted_methods") or {}
	return {
		"pages": len(texts),
		"letterhead_on_every_page": all("PARASRAMKA" in t for t in texts),
		"page_texts": texts,
		"default_format": default_format(doctype),
		"letterhead_file": os.path.exists(letterhead_path()),
		"pdf_button_overridden": (overrides.get("frappe.utils.print_format.download_pdf") or [None])[-1]
		== "pepl_os.common.letterhead.download_pdf",
	}
