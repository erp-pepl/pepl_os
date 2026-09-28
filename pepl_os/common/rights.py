"""Pure permission arithmetic, shared by the PEPL Role Access Matrix report and
the access planning pack. No Frappe imports, so it can run anywhere.

How Frappe decides what a user may do on a DocType (permission level 0):
the user gets every right that ANY of their roles has. A right given only by a
rule marked "If Owner" applies to the user's own records only.
"""

RIGHTS = (
	"read",
	"create",
	"write",
	"submit",
	"cancel",
	"amend",
	"delete",
	"print",
	"email",
	"export",
	"import",
	"report",
	"share",
)

# Roles every desk user has without being given them.
BASELINE_ROLES = ("All", "Guest", "Desk User")

YES = "Yes"
OWN = "Own only"


def combine(perm_rows, roles):
	"""{right: "Yes" | "Own only" | ""} for a user holding `roles`.

	`perm_rows` are dict-likes with role, permlevel, if_owner and the rights.
	"""
	roles = set(roles) | set(BASELINE_ROLES)
	result = {}
	for right in RIGHTS:
		value = ""
		for row in perm_rows:
			if row.get("role") not in roles or (row.get("permlevel") or 0) != 0:
				continue
			if not row.get(right):
				continue
			if row.get("if_owner"):
				value = value or OWN
			else:
				value = YES
				break
		result[right] = value
	# Frappe needs read before anything else is usable on a record.
	if not result["read"]:
		for right in ("write", "submit", "cancel", "amend", "delete", "print", "email", "share"):
			result[right] = ""
	return result


def summarise(rights):
	"""The same rights in plain words, for people who do not use ERPNext terms."""
	if not rights.get("read"):
		return "No access"
	can = []
	if rights.get("create"):
		can.append("create")
	if rights.get("write"):
		can.append("edit")
	if rights.get("submit"):
		can.append("submit (finalise)")
	if rights.get("cancel"):
		can.append("cancel")
	if rights.get("delete"):
		can.append("delete")
	text = "View" if not can else "View, " + ", ".join(can)
	if OWN in rights.values():
		text += " (some rights on own records only)"
	return text
