# PEPL OS v0.35.0 - Check 35: C3a-P1 the Job Order status panel - quantity against target, routing progress
# (next step marked), delivery days late / left, LD so far on the Sales Order line.
# Runs on 0.35.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at
# the end. After the check, open any submitted Job Order to see the panel on the form.
VERSION = "0.35.0"
PARAMS = "PEPL System Parameters"
SPR = "PEPL Shift Production Entry"
PANEL = "pepl_os.pepl_production.job_order_panel.get_job_order_panel"
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


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
yesterday = frappe.utils.add_days(today, -1)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def panel(work_order):
    rows = frappe.call(PANEL, work_order=work_order)["rows"]
    print("INFO  panel of " + work_order + ": " + " | ".join(r["text"] for r in rows))
    return rows


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")

params = frappe.get_doc(PARAMS)
params.custom_spr_tool_photo_required = 0
params.save()
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.overproduction_percentage_for_work_order = 0
settings.save()

# ---------------- 2. a Job Order with two steps ----------------
# Machines without a machine group: the skill check says "Not checked" and never blocks, whatever this site's mode.
# The finished part is a sales item with an 8-digit HSN code (India Compliance checks the Sales Order).
DAY = "CHK35 Day " + RUN
MILL = "CHK35 MILL-01 " + RUN
DRILL = "CHK35 DRILL-02 " + RUN
OP = "CHK35-OP-" + RUN
NO_LOAD = "CHK35 No Load " + RUN
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": DRILL}).insert()
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Check " + OP, "pin": pin}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    hsn = codes[0] if codes else ""
fg_values = {"doctype": "Item", "item_code": "CHK35-FG-" + RUN, "item_name": "CHK35 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 1 if hsn else 0}
if hsn:
    fg_values["gst_hsn_code"] = hsn
fg = frappe.get_doc(fg_values).insert().name
bo = frappe.get_doc({"doctype": "Item", "item_code": "CHK35-BO-" + RUN, "item_name": "CHK35 Bought-out " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
MILLING = "CHK35 Milling " + RUN
DRILLING = "CHK35 Drilling " + RUN
frappe.get_doc({"doctype": "Operation", "name": MILLING, "workstation": MILL}).insert()
frappe.get_doc({"doctype": "Operation", "name": DRILLING, "workstation": DRILL}).insert()
bom = frappe.get_doc({
    "doctype": "BOM", "item": fg, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
    "currency": frappe.db.get_value("Company", company, "default_currency"),
    "items": [{"item_code": bo, "qty": 1, "rate": 10}],
    "operations": [{"operation": MILLING, "workstation": MILL, "time_in_mins": 6}, {"operation": DRILLING, "workstation": DRILL, "time_in_mins": 3}],
}).insert()
bom.submit()

# A Sales Order with LD, ordered 30 days ago and due 10 days ago; its drafted Job Order (C3a-X5) is submitted.
groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
customer = frappe.get_doc({"doctype": "Customer", "customer_name": "CHK35 Customer " + RUN, "customer_type": "Company",
                           "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert().name
due = frappe.utils.add_days(today, -10)
so = frappe.get_doc({
    "doctype": "Sales Order", "customer": customer, "company": company, "custom_sector": "Private",
    "transaction_date": frappe.utils.add_days(today, -30), "delivery_date": due,
    "custom_ld_applicable": 1, "custom_ld_rate_percent": 0.5, "custom_ld_max_percent": 10, "custom_ld_period": "Week",
    "items": [{"item_code": fg, "qty": 10, "rate": 100, "warehouse": wh("FG Stores"), "delivery_date": due}],
}).insert()
so.submit()
drafts = frappe.get_all("Work Order", filters={"sales_order": so.name, "docstatus": 0}, pluck="name")
check(len(drafts) == 1, "2. the Sales Order drafted its Job Order " + ", ".join(drafts))
wo = frappe.get_doc("Work Order", drafts[0])
wo.submit()
cards = {c.operation: c.name for c in frappe.get_all("Job Card", filters={"work_order": wo.name}, fields=["name", "operation"])}
print("INFO  Job Order " + wo.name + ": 10 pieces; Job Cards " + ", ".join(k + " " + v for k, v in cards.items()))

# ---------------- 3. quantity and routing ----------------
rows = panel(wo.name)
check(any("Made 0 of 10" in r["text"] for r in rows), "3. nothing made yet: 'Made 0 of 10 (0%)'")
first = [r for r in rows if "Step 1" in r["text"]]
check(bool(first) and first[0]["text"].startswith("▶") and MILLING in first[0]["text"], "3. step 1 (milling) is marked as the next step")

entry = frappe.get_doc({"doctype": SPR, "posting_date": yesterday, "shift": DAY, "workstation": MILL, "operator": OP, "company": company})
entry.append("production", {"job_card": cards.get(MILLING), "from_time": "08:00", "to_time": "12:00", "good_qty": 8, "rejected_qty": 2, "rejection_reason": "Undersize"})
entry.append("downtime", {"downtime_category": NO_LOAD, "from_time": "12:00", "to_time": "16:00"})
entry.insert()
entry.submit()
rows = panel(wo.name)
check(any("8 good, 2 rejected" in r["text"] for r in rows), "3. after yesterday's shift entry: the shop floor reported 8 good, 2 rejected")
first = [r for r in rows if "Step 1" in r["text"]]
check(bool(first) and "8 of 10" in first[0]["text"], "3. step 1 (milling): 8 of 10 done")
second = [r for r in rows if "Step 2" in r["text"]]
check(bool(second) and DRILLING in second[0]["text"] and "0 of 10" in second[0]["text"], "3. step 2 (drilling): 0 of 10")

# ---------------- 4. delivery and LD ----------------
check(any("10 days late" in r["text"] and r["colour"] == "red" for r in rows), "4. due 10 days ago: '10 days late' in red")
check(any("LD so far" in r["text"] for r in rows), "4. the Sales Order carries LD: the panel shows the LD so far on this line (1000 x 0.5 % x 2 weeks = 10)")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
