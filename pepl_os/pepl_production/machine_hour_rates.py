"""C3a-R1 - Machine-Hour Rates (System Parameters → Production Costing) per machine group (Workstation Type).

The rate rows were typed group names (Cycle 2). They are now links to the machine group the machines belong to,
so a machine's rate is found from its group without spelling mistakes. link_rate_groups() moves old rows across:
case differences are corrected and a missing group is created.
"""

import frappe

SYSTEM_PARAMETERS = "PEPL System Parameters"
RATES_FIELD = "custom_machine_hour_rates"
RATE_DOCTYPE = "PEPL Machine Hour Rate"


def _groups_by_lower():
	return {name.strip().lower(): name for name in frappe.get_all("Workstation Type", pluck="name")}


def link_rate_groups():
	"""Make every rate row point at an existing Workstation Type. Returns {"renamed": [...], "created": [...]}."""
	renamed, created = [], []
	groups = _groups_by_lower()
	for row in frappe.get_all(
		RATE_DOCTYPE,
		filters={"parent": SYSTEM_PARAMETERS, "parentfield": RATES_FIELD},
		fields=["name", "machine_group"],
	):
		typed = (row.machine_group or "").strip()
		if not typed:
			continue
		match = groups.get(typed.lower())
		if not match:
			frappe.get_doc({"doctype": "Workstation Type", "workstation_type": typed}).insert(
				ignore_permissions=True
			)
			match = typed
			groups[typed.lower()] = typed
			created.append(typed)
		if match != row.machine_group:
			frappe.db.set_value(RATE_DOCTYPE, row.name, "machine_group", match, update_modified=False)
			renamed.append(f"{row.machine_group} -> {match}")
	frappe.clear_document_cache(SYSTEM_PARAMETERS, SYSTEM_PARAMETERS)
	return {"renamed": renamed, "created": created}


def rate_for_group(group):
	"""The Machine-Hour Rate of a machine group, or None."""
	if not group:
		return None
	rows = frappe.get_all(
		RATE_DOCTYPE,
		filters={"parent": SYSTEM_PARAMETERS, "parentfield": RATES_FIELD, "machine_group": group},
		pluck="rate_per_hour",
		limit=1,
	)
	return rows[0] if rows else None
