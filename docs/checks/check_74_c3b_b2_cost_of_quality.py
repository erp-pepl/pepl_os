# PEPL OS v0.74.0 - Check 74: C3b-B2 Cost of Quality - the report PEPL Cost of Quality: rejected pieces priced at the
# item's cost a piece, scrap recovered taken off, NCR rework, other NCR cost and customer returns, in rupees, by month
# or by item; cancelled NCRs and rejection-rate NCRs (already counted as rejection) left out; what is not priced.
# Runs on 0.74.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the end.
# The first INFO lines are this site's Cost of Quality for the last 12 months. Afterwards open the report (see chat).
VERSION = "0.74.0"
NCR = "PEPL NCR"
REPORT = "PEPL Cost of Quality"
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


def run(filters, show):
    result = frappe.call("frappe.desk.query_report.run", report_name=REPORT, filters=filters)
    rows = [r for r in (result.get("result") or []) if isinstance(r, dict) and r.get("key")]
    if show:
        for r in rows:
            print("INFO  " + str(r.get("key")) + ": rejected " + str(r.get("rejected_pieces")) + " pcs = " + str(r.get("rejection"))
                  + ", scrap -" + str(r.get("scrap_recovered")) + ", NCR rework " + str(r.get("ncr_rework")) + ", NCR other "
                  + str(r.get("ncr_other")) + ", customer " + str(r.get("customer")) + " -> Cost of Quality " + str(r.get("total"))
                  + ((" | not priced: " + r.get("notes")) if r.get("notes") else ""))
    return rows


def find(rows, key):
    for r in rows:
        if r.get("key") == key:
            return r
    return {}


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
MONTH = {"from_date": frappe.utils.get_first_day(today), "to_date": frappe.utils.get_last_day(today), "group_by": "Month"}
YEAR = {"from_date": frappe.utils.get_first_day(frappe.utils.add_months(today, -11)), "to_date": frappe.utils.get_last_day(today), "group_by": "Month"}

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.db.exists("Report", REPORT)), "1. the report PEPL Cost of Quality exists")

# ---------------- 2. this site, last 12 months ----------------
year = run(YEAR, True)
check(all(abs(r.get("total") - (r.get("rejection") - r.get("scrap_recovered") + r.get("ncr_rework") + r.get("ncr_other") + r.get("customer"))) < 0.01 for r in year),
      "2. every month: Cost of Quality = rejection - scrap + NCR rework + NCR other + customer")
unpriced = [r for r in year if "without a cost a piece" in str(r.get("notes"))]
print("INFO  months with rejected pieces that have no cost a piece: " + str(len(unpriced)))

# ---------------- 3. NCRs of each kind on a new item ----------------
before = run(MONTH, False)
before_total = sum([r.get("total") for r in before])
ITEM = frappe.get_doc({"doctype": "Item", "item_code": "CHK74-PIN-" + RUN, "item_name": "CHK74 Pin " + RUN, "item_group": "Bought-Out Components",
                       "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "is_purchase_item": 1, "valuation_rate": 10}).insert().name


def ncr(values):
    base = {"doctype": NCR, "source": "In-Process", "severity": "Minor", "item": ITEM, "qty_affected": 2, "raised_on": today,
            "defect_description": "burr"}
    base.update(values)
    return frappe.get_doc(base).insert().name


ncr({"disposition": "Rework", "estimated_cost": 100})
ncr({"disposition": "Scrap"})
ncr({"source": "Customer", "disposition": "Return to Supplier", "estimated_cost": 200})
ncr({"disposition": "Scrap", "estimated_cost": 999, "status": "Cancelled", "cancel_reason": "Raised by mistake"})
ncr({"disposition": "Scrap", "estimated_cost": 70, "raise_rule": "QA-NCR-RATE"})
row = find(run({"from_date": today, "to_date": today, "group_by": "Item"}, False), ITEM)
print("INFO  " + ITEM + ": " + str(row))
check(row.get("ncr_rework") == 100, "3. NCR Rework = 100 (the Rework NCR)")
check(row.get("ncr_other") == 0 and row.get("notes") == "1 NCR(s) without a cost", "3. the Scrap NCR without a cost: 0, and '1 NCR(s) without a cost'")
check(row.get("customer") == 200, "3. Customer (external) = 200 (the customer NCR)")
check(row.get("ncrs") == 3 and row.get("total") == 300, "3. 3 NCRs, Cost of Quality 300: the cancelled one (999) and the rejection-rate one (70) are left out")

# ---------------- 4. this month's total moves by 300 ----------------
after = run(MONTH, False)
check(abs(sum([r.get("total") for r in after]) - before_total - 300) < 0.01, "4. this month's Cost of Quality went up by exactly 300")
check(len(after) == 1 and after[0].get("key") == today[:7], "4. by month: one row, " + today[:7])

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
