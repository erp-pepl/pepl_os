# PEPL OS v0.79.3 - Check 79 rev 4: CR3 - PEPL's access plan (Access Planning Pack, 24 Nov 2026).
# New Role Profiles (Stores Manager, Accountant, Quality Executive, Production & Quality Viewer, add-ons Item Master,
# Supplier Master, Sales Invoicing), cancel only by the department head, BOMs only by the Production Manager,
# export only by the CEO, the cancellation summary - and CR2's tender rule unchanged.
# System Console, Type = Python, logged in as Administrator (or a System Manager). Leave "Commit" UNTICKED:
# this Check only reads.
VERSION = "0.79.3"
AP = "pepl_os.pepl_governance.access_plan"
passed = []
failed = []


def check(ok, label):
    if ok:
        passed.append(label)
        print("PASS  " + label)
    else:
        failed.append(label)
        print("FAIL  " + label)


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


def short(value):
    text = str(value)
    return text if len(text) < 400 else text[:400] + " ..."


installed = frappe.db.get_value("Installed Application", {"app_name": "pepl_os"}, "app_version")

# ---------------- 1. installed, switches ----------------
check(version_parts(installed) >= version_parts(VERSION), "1. pepl_os " + str(installed) + " installed (needs " + VERSION + ")")
status = frappe.call(AP + ".access_plan_status")
sw = status.get("switches") or {}
check(sw.get("cancel_only_by_hod"), "1. System Parameters -> Access: Cancel Only by the Department Head is ON")
check(sw.get("bom_by_production_manager_only"), "1. BOMs Made Only by the Production Manager is ON")
check(sw.get("restrict_export_to_ceo"), "1. Export to Excel Only by the CEO is ON")
print("INFO  Cancellation Summary E-mail: " + str(sw.get("summary")) + "; goes to: " + (", ".join(status.get("summary_recipients") or []) or "nobody yet (no PEPL CEO login)"))

# ---------------- 2. Role Profiles ----------------
profiles = status.get("profiles") or {}
check(len(profiles) == 20, "2. 20 PEPL Role Profiles in the code (" + str(len(profiles)) + ")")
for name, p in sorted(profiles.items()):
    check(p.get("exists") and not p.get("missing"), "2. Role Profile " + name + " exists with all its roles (missing: " + str(p.get("missing")) + ")")
    if p.get("extra"):
        print("INFO  " + name + " also has, added by hand: " + ", ".join(p.get("extra")))
pm = frappe.get_all("Has Role", filters={"parent": "PEPL Purchase Manager", "parenttype": "Role Profile"}, pluck="role")
check("Item Manager" not in pm, "2. PEPL Purchase Manager no longer makes Items (Item Manager out; Decision 1)")
qm = frappe.get_all("Has Role", filters={"parent": "PEPL Quality Manager", "parenttype": "Role Profile"}, pluck="role")
check("Stock User" not in qm and "PEPL Stock Viewer" in qm, "2. PEPL Quality Manager views stock only (Stock User out, PEPL Stock Viewer in; Decision 8)")

# ---------------- 3. the rules ----------------
check(not status.get("cancel_offenders"), "3. Decision 4: nobody but the HOD can cancel (" + short(status.get("cancel_offenders")) + ")")
check(not status.get("hod_cannot_cancel"), "3. Decision 4: every HOD can cancel their records (" + short(status.get("hod_cannot_cancel")) + ")")
check(not status.get("right_offenders"), "3. Decision 7: the Foreman cannot create or change BOMs (" + short(status.get("right_offenders")) + ")")
check(not status.get("export_offenders"), "3. Decision 9: only the CEO / System Manager can export (" + short(status.get("export_offenders")) + ")")
check(not status.get("ceo_export_missing"), "3. Decision 9: the CEO can export every business record (" + short(status.get("ceo_export_missing")) + ")")
check(not status.get("reports_missing_roles"), "3. the new roles open their reports (" + short(status.get("reports_missing_roles")) + ")")
check(status.get("scheduled"), "3. the daily cancellation summary job is scheduled")

# ---------------- 4. the pack's decisions, profile by profile ----------------
for e in status.get("examples") or []:
    check(e.get("got") == e.get("expected"), "4. " + e.get("label") + ": " + ("yes" if e.get("expected") else "no"))

# ---------------- 5. CR2 tender rule unchanged ----------------
ROLE = "PEPL Tender Access"
tender_in_profiles = frappe.get_all("Has Role", filters={"role": ["in", [ROLE, "PEPL Tender Manager", "PEPL Tender Executive", "PEPL Tender Viewer"]], "parenttype": "Role Profile"}, fields=["parent", "role"])
check(all(r.parent == "PEPL Tender Only" and r.role != ROLE for r in tender_in_profiles), "5. tender roles only in PEPL Tender Only; " + ROLE + " in no profile")
for doctype in ["PEPL Tender", "PEPL CST Cost Sheet"]:
    rows = frappe.get_all("Custom DocPerm", filters={"parent": doctype, "role": ROLE, "permlevel": 0}, fields=["read", "export"])
    check(bool(rows) and rows[0].read and rows[0].export, "5. " + ROLE + " still reads and exports " + doctype)
    check(not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": "PEPL CEO"}), "5. the CEO still has no view of " + doctype)
level5 = frappe.get_all("Custom DocPerm", filters={"parent": "Sales Order", "permlevel": 5, "read": 1}, pluck="role")
check(level5 in ([ROLE], []), "5. Sales Order tender fields (level 5) only for " + ROLE + " (" + ", ".join(level5) + ")")

# ---------------- 6. cancellations the summary would list ----------------
recent = frappe.call(AP + ".preview_cancellations", days=7)
print("INFO  records cancelled in the last 7 days: " + str(len(recent)))
for r in recent[:10]:
    print("INFO    " + r["doctype"] + " " + r["name"] + " by " + r["cancelled_by"] + " on " + str(r["cancelled_on"]))

print("")
print("Check 79: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
