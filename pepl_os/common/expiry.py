"""Generic expiry health: Active / Expiring Soon / Expired / No Expiry Set.

The Cycle 1 calculator reads one fixed parameter and today's date; this one
takes both as arguments so every module (supplier documents, warranties,
calibration, certifications) can reuse it and tests need no clock tricks.
"""

from frappe.utils import cint, date_diff, getdate, today

ACTIVE = "Active"
EXPIRING_SOON = "Expiring Soon"
EXPIRED = "Expired"
NO_EXPIRY = "No Expiry Set"


def health(expiry_date, alert_days, as_of=None):
	"""Return {"days_to_expiry", "status", "message"} for one expiry date."""
	if not expiry_date:
		return {"days_to_expiry": None, "status": NO_EXPIRY, "message": "No expiry date is set."}

	expiry = getdate(expiry_date)
	days = date_diff(expiry, getdate(as_of or today()))
	alert_days = cint(alert_days)

	if days < 0:
		status = EXPIRED
		message = f"Expired on {expiry} ({abs(days)} day(s) ago)."
	elif days <= alert_days:
		status = EXPIRING_SOON
		message = f"Expires in {days} day(s) on {expiry}."
	else:
		status = ACTIVE
		message = ""

	return {"days_to_expiry": days, "status": status, "message": message}
