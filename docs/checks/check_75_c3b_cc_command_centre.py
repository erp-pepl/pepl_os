# PEPL OS v0.75.0 - Check 75: C3b-CC the Quality Command Centre - the workspace and its six cards: Open NCRs by
# Severity, CAPAs Overdue for Verification, Instruments Due Within 30 Days, First-Pass Yield (7 days), Customer
# Rejections (30 days), Cost of Quality (month). Each card moves when the record behind it is made.
# Runs on 0.75.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters change it makes, is undone at the end. Afterwards open the Quality Command Centre (see chat).
VERSION = "0.75.0"
PARAMS = "PEPL System Parameters"
NCR = "PEPL NCR"
CAPA = "PEPL CAPA"
CC = "pepl_os.pepl_quality.command_centre."
WORKSPACE = "Quality Command Centre"
CARDS = ["PEPL CAPAs Overdue for Verification", "PEPL Instruments Due Within 30 Days", "PEPL First-Pass Yield 7 Days",
         "PEPL Customer Rejections 30 Days", "PEPL Cost of Quality Month"]
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


def card(method):
    return frappe.call(CC + method).get("value")


def severities():
    data = frappe.call(CC + "open_ncrs_by_severity")
    counts = {}
    for r in data.get("severities"):
        counts[r.get("severity")] = r.get("count")
    return counts


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.db.exists("Workspace", WORKSPACE)) and all(frappe.db.exists("Number Card", c) for c in CARDS)
      and bool(frappe.db.exists("Custom HTML Block", "PEPL Open NCRs by Severity")), "1. the workspace, its 5 number cards and the 'Open NCRs by Severity' block exist")

# ---------------- 2. this site's cards now ----------------
now = {}
for m in ["capas_overdue_for_verification", "instruments_due_within_30_days", "first_pass_yield", "customer_rejections", "cost_of_quality_month"]:
    now[m] = card(m)
    print("INFO  " + m + " = " + str(now[m]))
sev = severities()
print("INFO  open NCRs: Critical " + str(sev.get("Critical")) + " · Major " + str(sev.get("Major")) + " · Minor " + str(sev.get("Minor")))
first = frappe.utils.add_days(today, -7)
last = frappe.utils.add_days(today, -1)
row = frappe.db.sql("select coalesce(sum(total_good_qty), 0), coalesce(sum(total_rejected_qty), 0) from `tabPEPL Shift Production Entry` "
                    "where docstatus = 1 and posting_date between %s and %s", (first, last))[0]
good = frappe.utils.flt(row[0])
bad = frappe.utils.flt(row[1])
want = round(100.0 * good / (good + bad), 1) if good + bad else 0
check(now["first_pass_yield"] == want, "2. First-Pass Yield (7 days) = good / (good + rejected) = " + str(want) + " %")

# ---------------- 3. each card moves with its record ----------------
params = frappe.get_doc(PARAMS)
params.set("custom_capa_verification_days", 90)
params.set("custom_capa_whys_required", 1)
params.save()


def item(code):
    return frappe.get_doc({"doctype": "Item", "item_code": "CHK75-" + code + "-" + RUN, "item_name": "CHK75 " + code + " " + RUN,
                           "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0,
                           "is_purchase_item": 1, "valuation_rate": 10}).insert().name


def ncr(values):
    base = {"doctype": NCR, "source": "In-Process", "severity": "Minor", "qty_affected": 1, "defect_description": "burr"}
    base.update(values)
    return frappe.get_doc(base).insert()


crit = ncr({"item": item("SHAFT"), "severity": "Critical"})
check(severities().get("Critical") == sev.get("Critical") + 1, "3. a Critical NCR -> Open NCRs by Severity: Critical + 1")
ncr({"item": item("PIN"), "source": "Customer", "estimated_cost": 150})
check(card("customer_rejections") == now["customer_rejections"] + 1, "3. a customer NCR -> Customer Rejections (30 days) + 1")
check(abs(card("cost_of_quality_month") - now["cost_of_quality_month"] - 150) < 0.01, "3. its cost 150 -> Cost of Quality (month) + 150")
doc = frappe.get_doc(CAPA, frappe.db.get_value(NCR, crit.name, "capa"))
doc.why_1 = "Collet worn"
doc.root_cause = "No collet change interval"
doc.append("actions", {"action_type": "Corrective Action", "description": "Collet in the PM list", "done_on": today})
doc.status = "Closed"
doc.save()
frappe.db.set_value(CAPA, doc.name, "verification_due_on", frappe.utils.add_days(today, -1))
check(card("capas_overdue_for_verification") == now["capas_overdue_for_verification"] + 1, "3. a CAPA whose check was due yesterday -> CAPAs Overdue for Verification + 1")
gauge = frappe.get_doc({"doctype": "PEPL Instrument", "instrument_id": "CHK75-VC-" + RUN, "instrument_name": "CHK75 gauge", "calibration_frequency_days": 365}).insert().name
rec = frappe.get_doc({"doctype": "PEPL Calibration Record", "instrument": gauge, "calibration_date": frappe.utils.add_days(today, -340), "result": "Pass",
                      "certificate_no": "CHK75"}).insert()
rec.submit()
check(card("instruments_due_within_30_days") == now["instruments_due_within_30_days"] + 1, "3. a gauge due in 25 days -> Instruments Due Within 30 Days + 1")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
