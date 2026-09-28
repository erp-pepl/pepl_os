# Copyright (c) 2026, Parasramka Engineering Pvt. Ltd. and contributors
"""PEPL Role Access Matrix: what each PEPL Role Profile can do on each record.

Read live from the site's permissions. Export to Excel to show PEPL exactly
what a profile allows before a person is given it.
"""

from frappe import _

from pepl_os.pepl_governance.access_matrix import get_rows

RIGHT_LABELS = (
	("read", _("View")),
	("create", _("Create")),
	("write", _("Edit")),
	("submit", _("Submit")),
	("cancel", _("Cancel")),
	("amend", _("Amend")),
	("delete", _("Delete")),
	("print", _("Print")),
	("email", _("Email")),
	("export", _("Export")),
	("import", _("Import")),
	("report", _("Reports")),
	("share", _("Share")),
)


def execute(filters=None):
	rows = get_rows(filters)
	message = _(
		"Read live from this site's permissions. 'Own only' means the right applies only to records the user created."
	)
	return get_columns(), rows, message


def get_columns():
	columns = [
		{
			"fieldname": "role_profile",
			"label": _("Role Profile"),
			"fieldtype": "Link",
			"options": "Role Profile",
			"width": 200,
		},
		{"fieldname": "area", "label": _("Area"), "fieldtype": "Data", "width": 100},
		{"fieldname": "document", "label": _("Record"), "fieldtype": "Data", "width": 220},
		{"fieldname": "in_plain_words", "label": _("In plain words"), "fieldtype": "Data", "width": 260},
	]
	columns += [
		{"fieldname": f, "label": label, "fieldtype": "Data", "width": 70} for f, label in RIGHT_LABELS
	]
	columns.append({"fieldname": "doctype", "label": _("ERPNext DocType"), "fieldtype": "Data", "width": 170})
	return columns
