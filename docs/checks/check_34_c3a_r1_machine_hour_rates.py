# PEPL OS v0.34.0 - Check 34: C3a-R1 Machine-Hour Rates linked to the machine group (Workstation Type).
# Runs on 0.34.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes this check makes, is undone at the end. Run Check 29 again after this one: the weekly
# machine cost now finds its rate through the link.
VERSION = "0.34.0"
PARAMS = "PEPL System Parameters"
PATCH = "pepl_os.patches.v0_34.link_machine_hour_rate_groups"
passed = []
failed = []


def check(ok, label):
    if ok:
        passed.append(label)
        print("PASS  " + label)
    else:
        failed.append(label)
        print("FAIL  " + label)


def refused(label, action, words):
    try:
        action()
        check(False, label + " (it was accepted)")
        return ""
    except Exception as e:
        text = frappe.utils.strip_html(str(e))
        check(words.lower() in text.lower(), label + " -> " + text[:200])
        return text


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
field = frappe.get_meta("PEPL Machine Hour Rate").get_field("machine_group")
check(field.fieldtype == "Link" and field.options == "Workstation Type", "1. Machine-Hour Rates: Machine Group is now a link to the machine group (Workstation Type)")
check(bool(frappe.db.exists("Patch Log", {"patch": PATCH})), "1. the one-time move of the old rows ran on this site (" + PATCH + ")")

# ---------------- 2. the rows on this site ----------------
rows = frappe.get_all("PEPL Machine Hour Rate", filters={"parent": PARAMS, "parentfield": "custom_machine_hour_rates"}, fields=["machine_group", "rate_per_hour"], order_by="idx")
print("INFO  this site: " + (", ".join(str(r.machine_group) + " = " + str(r.rate_per_hour) for r in rows) if rows else "no Machine-Hour Rates yet"))
check(all(frappe.db.exists("Workstation Type", r.machine_group) for r in rows), "2. every Machine-Hour Rate row points at an existing machine group (" + str(len(rows)) + " row(s))")

# ---------------- 3. new rows must name a machine group ----------------
GROUP = "CHK34 Gear Hobbing " + RUN


def add_rate(group, rate):
    params = frappe.get_doc(PARAMS)
    params.append("custom_machine_hour_rates", {"machine_group": group, "rate_per_hour": rate})
    params.save()


refused("3. a rate for a group that is not a machine group is refused", lambda: add_rate(GROUP, 700), "Could not find")
frappe.get_doc({"doctype": "Workstation Type", "workstation_type": GROUP}).insert()
add_rate(GROUP, 700)
saved = frappe.get_all("PEPL Machine Hour Rate", filters={"parent": PARAMS, "machine_group": GROUP}, pluck="rate_per_hour")
check(saved == [700], "3. once " + GROUP + " exists as a machine group, its rate of 700 is saved")
refused("3. the same machine group twice is refused", lambda: add_rate(GROUP, 750), "listed twice")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved. Now run Check 29 again (weekly machine cost through the link).")
