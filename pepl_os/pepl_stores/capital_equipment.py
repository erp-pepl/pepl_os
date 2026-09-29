"""C2-05 - Capital Equipment: core documents and warranty / AMC expiry alerts."""

import frappe
from frappe.utils import date_diff, getdate, today

from pepl_os.common import alerts, params
from pepl_os.common.jobs import tracked_job

DOCTYPE = "PEPL Capital Equipment"
RULE_CODE = "STO-CAP-EXPIRY"
OWNER_FIELD = "custom_stores_notification_owner"

# The three documents every piece of equipment must have. Warranty and
# guarantee certificates count as the same document.
CORE_DOCUMENTS = (
	("Purchase Invoice PDF", ("Purchase Invoice PDF",)),
	("Manual", ("Manual",)),
	("Warranty / Guarantee Certificate", ("Warranty Certificate", "Guarantee Certificate")),
)


def core_document_gaps(doc):
	have = {row.document_type for row in doc.get("documents") or [] if row.get("file")}
	return [label for label, accepted in CORE_DOCUMENTS if not have.intersection(accepted)]


def _days_left(date_value, as_of=None):
	return date_diff(getdate(date_value), getdate(as_of or today())) if date_value else None


def cover_days_left(doc, as_of=None):
	return _days_left(doc.get("warranty_until"), as_of), _days_left(doc.get("amc_until"), as_of)


def expiring_cover(doc, alert_days, as_of=None):
	"""Lines describing warranty / AMC that expire within alert_days (or already expired)."""
	lines = []
	for label, field in (("Warranty", "warranty_until"), ("AMC", "amc_until")):
		days = _days_left(doc.get(field), as_of)
		if days is None or days > alert_days:
			continue
		if days < 0:
			lines.append(f"{label} expired on {doc.get(field)} ({-days} day(s) ago).")
		else:
			lines.append(f"{label} expires on {doc.get(field)} ({days} day(s) left).")
	return lines


def refresh_equipment_alerts(as_of=None):
	"""Raise one ToDo per equipment whose warranty or AMC is near expiry; close the rest."""
	alert_days = params.get_int("custom_supplier_doc_expiry_alert_days", 30)
	active = []
	for row in frappe.get_all(
		DOCTYPE,
		filters={"status": ["!=", "Disposed"]},
		fields=["name", "equipment_name", "warranty_until", "amc_until"],
	):
		lines = expiring_cover(row, alert_days, as_of)
		if not lines:
			continue
		active.append(row.name)
		alerts.raise_todo(
			RULE_CODE,
			DOCTYPE,
			row.name,
			f"{row.equipment_name} ({row.name}): " + " ".join(lines) + " Renew and update the dates.",
			owner_field=OWNER_FIELD,
			priority="High" if any("expired" in line for line in lines) else "Medium",
		)
	closed = alerts.close_resolved(RULE_CODE, DOCTYPE, active)
	return {"records_touched": len(active) + closed, "message": f"{len(active)} open, {closed} closed"}


@tracked_job("Capital equipment warranty and AMC alerts")
def daily_equipment_alerts():
	refresh_days_left()
	return refresh_equipment_alerts()


def refresh_days_left():
	"""Keep the stored 'days left' current for list views and reports."""
	for row in frappe.get_all(
		DOCTYPE, filters={"status": ["!=", "Disposed"]}, fields=["name", "warranty_until", "amc_until"]
	):
		warranty, amc = cover_days_left(row)
		frappe.db.set_value(
			DOCTYPE, row.name, {"warranty_days_left": warranty, "amc_days_left": amc}, update_modified=False
		)
