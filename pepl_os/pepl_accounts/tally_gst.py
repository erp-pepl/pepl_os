"""CR1 - PEPL's GST ledgers in ERPNext, named and grouped exactly as in Tally (Duties & Taxes).

Source: PEPL's Tally group summary "GrpSum (GST)" (Nov 2026). Names are copied letter for letter, spelling included,
so the Tally mirror (Work Package R) can match ledgers one to one. ERPNext adds the company abbreviation (" - PEPL").

India Compliance creates its own GST accounts (Output Tax CGST, Input Tax CGST, ... RCM) and builds the tax
templates, Item Tax Templates and GST Settings on them. setup_tally_gst_ledgers() renames and moves those accounts to
the Tally ledgers, so every template and setting keeps working (a rename carries its links), and creates the other
Tally ledgers. India Compliance accounts with no Tally ledger (sales reverse charge, refunds) keep their names.
Safe to run again: what is already in place is left alone.

System Console (Commit ticked):
frappe.call("pepl_os.pepl_accounts.tally_gst.setup_tally_gst_ledgers", company="<Company>")
"""

import frappe
from frappe import _

DUTIES_AND_TAXES = "Duties and Taxes"
SETUP_ROLES = ("System Manager", "Accounts Manager")

# Tally group -> its ledgers (a nested tuple is a sub-group with its own ledgers). Order as in Tally.
TALLY_TREE = (
	("Cash Credit Ledgers", ("CGST Cash Credit", "IGST Cash Crdit", "SGST Cash Credit")),
	(
		"Electronic Credit Ledgers",
		(
			"CGST - Electronic Credit Ledger",
			"IGST - Electronic Credit Ledger",
			"SGST - Electrinic Credit Ledger",
		),
	),
	("Ineligible ITC-GST", ("Ineligible - IGST", "Ineligible ITC- WB CGST", "Ineligible ITC- WB SGST")),
	(
		"Input GST",
		(
			(
				"Intermediate ITC",
				("Intermediate ITC - IGST", "Intermediate ITC - WB CGST", "Intermediate ITC - WB SGST"),
			),
			(
				"Intermediate ITC - RCM",
				("Intermediate ITC - CGST RCM", "Intermediate ITC - IGST RCM", "Intermediate ITC - SGST RCM"),
			),
		),
	),
	("Output - GST", ("CGST", "IGST", "SGST")),
	(
		"Payable Under RCM",
		("Payable Under RCM - CGST", "Payable Under RCM - IGST", "Payable Under RCM -SGST"),
	),
	("Receivable ITC", ("Receivable ITC - IGST", "Receivable ITC -WB CGST", "Receivable ITC - WB SGST")),
	("TDS From GST", ("TDS on GST - CGST", "TDS on GST - SGST", "TDS on IGST")),
)

# India Compliance account -> Tally ledger it becomes.
# Output = tax on PEPL's sales. Input = ITC on purchases, booked first to Intermediate ITC in Tally (to confirm with
# PEPL's accountant before purchase bills are booked). "Input Tax ... RCM" is the reverse-charge tax PEPL owes.
RENAMES = {
	"Output Tax CGST": "CGST",
	"Output Tax SGST": "SGST",
	"Output Tax IGST": "IGST",
	"Input Tax CGST": "Intermediate ITC - WB CGST",
	"Input Tax SGST": "Intermediate ITC - WB SGST",
	"Input Tax IGST": "Intermediate ITC - IGST",
	"Input Tax CGST RCM": "Payable Under RCM - CGST",
	"Input Tax SGST RCM": "Payable Under RCM -SGST",
	"Input Tax IGST RCM": "Payable Under RCM - IGST",
}

TAX_ROW_TABLES = (
	("Sales Taxes and Charges", "Sales Taxes and Charges Template"),
	("Purchase Taxes and Charges", "Purchase Taxes and Charges Template"),
)


def ledger_parents():
	"""{ledger or group name: its Tally parent} (top groups have parent None = Duties and Taxes)."""
	parents = {}

	def walk(entries, parent):
		for entry in entries:
			if isinstance(entry, tuple):
				name, children = entry
				parents[name] = parent
				walk(children, name)
			else:
				parents[entry] = parent

	walk(TALLY_TREE, None)
	return parents


def groups():
	"""Tally group names, parents before children."""
	found = []

	def walk(entries):
		for entry in entries:
			if isinstance(entry, tuple):
				found.append(entry[0])
				walk(entry[1])

	walk(TALLY_TREE)
	return found


def account_name(name, abbr):
	return f"{name} - {abbr}"


@frappe.whitelist()
def setup_tally_gst_ledgers(company):
	"""Build the Tally GST ledgers of `company` under Duties and Taxes. Returns what was done."""
	frappe.only_for(SETUP_ROLES)
	abbr = frappe.get_cached_value("Company", company, "abbr")
	if not abbr:
		frappe.throw(_("Company {0} not found.").format(company))
	root = frappe.db.get_value(
		"Account", {"company": company, "account_name": DUTIES_AND_TAXES, "is_group": 1}, "name"
	)
	if not root:
		frappe.throw(
			_("Company {0} has no '{1}' group in its Chart of Accounts.").format(company, DUTIES_AND_TAXES)
		)

	result = {
		"india_compliance_defaults": False,
		"groups_created": [],
		"renamed": [],
		"moved": [],
		"created": [],
	}
	if "india_compliance" in frappe.get_installed_apps() and not _has_any(
		company, list(RENAMES) + list(RENAMES.values())
	):
		# A company set up before India Compliance: let it make its accounts and templates first.
		from india_compliance.gst_india.overrides.company import make_default_tax_templates

		make_default_tax_templates(company)
		result["india_compliance_defaults"] = True

	parents = ledger_parents()
	tally_names = {}
	for group in groups():
		parent = tally_names.get(parents[group], root)
		name = account_name(group, abbr)
		if not frappe.db.exists("Account", name):
			_new_account(company, group, parent, is_group=1)
			result["groups_created"].append(name)
		else:
			_place(name, parent, result)
		tally_names[group] = name

	for old, new in RENAMES.items():
		target = account_name(new, abbr)
		source = account_name(old, abbr)
		if not frappe.db.exists("Account", target) and frappe.db.exists("Account", source):
			_rename(source, new, abbr)
			result["renamed"].append(f"{source} → {target}")

	for ledger, parent_group in parents.items():
		if ledger in tally_names:
			continue
		name = account_name(ledger, abbr)
		parent = tally_names[parent_group]
		if frappe.db.exists("Account", name):
			_place(name, parent, result)
		else:
			_new_account(company, ledger, parent, is_group=0)
			result["created"].append(name)

	_sync_tax_row_descriptions(abbr)
	frappe.clear_cache()
	return result


def _has_any(company, names):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	return any(frappe.db.exists("Account", account_name(name, abbr)) for name in names)


def _new_account(company, name, parent, is_group):
	frappe.get_doc(
		{
			"doctype": "Account",
			"company": company,
			"account_name": name,
			"parent_account": parent,
			"is_group": is_group,
			"account_type": "Tax",
		}
	).insert(ignore_permissions=True)


def _place(name, parent, result):
	"""Move an existing account under its Tally group (ERPNext re-sets root type from the new parent)."""
	if frappe.db.get_value("Account", name, "parent_account") == parent:
		return
	account = frappe.get_doc("Account", name)
	account.parent_account = parent
	account.save(ignore_permissions=True)
	result["moved"].append(f"{name} → {parent}")


def _rename(source, new_account_name, abbr):
	"""ERPNext's own way of renaming an account without a number: account_name, then the record name."""
	frappe.db.set_value("Account", source, "account_name", new_account_name)
	frappe.rename_doc("Account", source, account_name(new_account_name, abbr), force=True)


def _sync_tax_row_descriptions(abbr):
	"""A template row's description is the account's old name; prints show it, so it follows the rename."""
	for old, new in RENAMES.items():
		for table, parenttype in TAX_ROW_TABLES:
			frappe.db.sql(
				f"""update `tab{table}` set description = %s
				where parenttype = %s and account_head = %s and description = %s""",
				(new, parenttype, account_name(new, abbr), old),
			)
