# PEPL OS v0.46.0 - Check 46: C3a-B5 LD Exposure report - late days x contractual LD rate on every open Sales Order:
# LD so far, LD in the look-ahead days if nothing more is delivered, red / orange / green, by order and by line.
# Runs on 0.46.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the
# end. Then open the report in the browser: see the steps in the chat.
VERSION = "0.46.0"
PARAMS = "PEPL System Parameters"
REPORT = "PEPL LD Exposure"
AHEAD = "custom_ld_look_ahead_days"
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
    except Exception as e:
        text = frappe.utils.strip_html(str(e))
        check(words.lower() in text.lower(), label + " -> " + text[:200])


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


def near(a, b):
    return a is not None and abs(frappe.utils.flt(a) - frappe.utils.flt(b)) <= 0.011


def run_report(filters):
    return frappe.call("frappe.desk.query_report.run", report_name=REPORT, filters=filters)


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def day(offset):
    return frappe.utils.add_days(today, offset)


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(frappe.db.get_value("Report", REPORT, "report_type") == "Script Report" and bool(frappe.get_all("Workspace Link", filters={"parent": "Production Command Centre", "link_to": REPORT})),
      "1. report '" + REPORT + "' exists and is listed on the Production Command Centre")
check(bool(frappe.get_meta(PARAMS).get_field(AHEAD)), "1. System Parameters > Production > LD: Look-Ahead Days (this site: " + str(frappe.db.get_single_value(PARAMS, AHEAD)) + ")")
params = frappe.get_doc(PARAMS)
params.custom_ld_default_sectors = "Railways\nDefence"
params.custom_ld_default_rate_percent = 0.5
params.custom_ld_default_period = "Week"
params.custom_ld_default_max_percent = 10
params.set(AHEAD, 7)
params.save()

# ---------------- 2. a customer, a part, four orders ----------------
# The part is a bought-out sales item with an 8-digit HSN code (India Compliance checks Sales Orders and Delivery Notes).
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    hsn = codes[0] if codes else ""
values = {"doctype": "Item", "item_code": "CHK46-PART-" + RUN, "item_name": "CHK46 Part " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 1 if hsn else 0, "valuation_rate": 50}
if hsn:
    values["gst_hsn_code"] = hsn
PART = frappe.get_doc(values).insert().name
receipt = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company, "set_posting_time": 1, "posting_date": day(-40),
                          "items": [{"item_code": PART, "qty": 100, "t_warehouse": wh("Bought-Out Stores"), "basic_rate": 50}]}).insert()
receipt.submit()
groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
customer = frappe.get_doc({"doctype": "Customer", "customer_name": "CHK46 Customer " + RUN, "customer_type": "Company",
                           "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert().name


def order(sector, ordered_days_ago, due_in):
    doc = frappe.get_doc({"doctype": "Sales Order", "customer": customer, "company": company, "custom_sector": sector,
                          "transaction_date": day(-ordered_days_ago), "delivery_date": day(due_in),
                          "items": [{"item_code": PART, "qty": 10, "rate": 100, "warehouse": wh("Bought-Out Stores"), "delivery_date": day(due_in)}]}).insert()
    doc.submit()
    return doc.name


late = order("Railways", 30, -10)  # 10 days late
soon = order("Railways", 5, 3)  # due in 3 days
fine = order("Railways", 5, 30)  # due in 30 days
private = order("Private", 30, -10)  # late, but no LD clause
print("INFO  orders of " + customer + ": late " + late + " (due 10 days ago), soon " + soon + " (due in 3 days), on time " + fine + " (due in 30 days), no LD " + private)

# ---------------- 3. the report, by order ----------------
out = run_report({"customer": customer, "as_on": today})
rows = out.get("result") or []
by = {}
for r in rows:
    by[r.get("sales_order")] = r
for r in rows:
    print("INFO  " + str(r.get("sales_order")) + ": " + str(r.get("terms")) + ", days late " + str(r.get("days_late")) + ", LD so far " + str(r.get("ld_now")) + ", in 7 days "
          + str(r.get("ld_ahead")) + " (" + str(r.get("colour")) + ")")
check(late in by and near(by[late].get("ld_now"), 10) and by[late].get("days_late") == 10, "3. " + late + ": 10 days late = 2 weeks: 1000 x 0.5 % x 2 = 10 so far")
check(late in by and near(by[late].get("ld_ahead"), 15) and near(by[late].get("ld_added"), 5) and by[late].get("colour") == "red", "3. ... in 7 days (17 days = 3 weeks) 15, 5 more - red")
check(late in by and near(by[late].get("cap_amount"), 100) and near(by[late].get("cap_used"), 10), "3. ... cap 10 % of 1000 = 100, 10 % of it used")
check(soon in by and near(by[soon].get("ld_now"), 0) and near(by[soon].get("ld_ahead"), 5) and by[soon].get("colour") == "orange", "3. " + soon + ": no LD yet, 5 if not delivered in 7 days - orange")
check(fine in by and near(by[fine].get("ld_ahead"), 0) and by[fine].get("colour") == "green", "3. " + fine + ": due in 30 days - green")
check(private not in by, "3. " + private + " (no LD clause) is left out while 'Only orders with LD terms' is ticked")
check(rows and rows[0].get("sales_order") == late, "3. the order with the most LD comes first")
check("on 1 order(s)" in str(out.get("message")) and "1 more order(s) start LD" in str(out.get("message")), "3. the line above the report -> " + str(out.get("message")))
out = run_report({"customer": customer, "as_on": today, "only_ld": 0})
grey = [r for r in out.get("result") or [] if r.get("sales_order") == private]
check(bool(grey) and grey[0].get("terms") == "no LD clause" and grey[0].get("colour") == "gray", "3. unticked: " + private + " shows grey, 'no LD clause'")

# ---------------- 4. by line, a late part delivery, and the setting ----------------
dn = frappe.get_doc({"doctype": "Delivery Note", "customer": customer, "company": company, "posting_date": today,
                     "items": [{"item_code": PART, "qty": 4, "rate": 100, "warehouse": wh("Bought-Out Stores"), "against_sales_order": late,
                                "so_detail": frappe.get_doc("Sales Order", late).items[0].name}]}).insert()
dn.submit()
out = run_report({"sales_order": late, "as_on": today, "show": "Lines"})
line = (out.get("result") or [{}])[0]
check(line.get("delivered") == 4 and line.get("pending") == 6 and near(line.get("ld_now"), 10) and near(line.get("ld_ahead"), 13),
      "4. 4 delivered today (late), 6 pending: 10 so far; in 7 days 4 + 600 x 0.5 % x 3 = 13 (by line)")
params = frappe.get_doc(PARAMS)
params.set(AHEAD, 2)
params.save()
out = run_report({"sales_order": soon, "as_on": today})
row = (out.get("result") or [{}])[0]
check(near(row.get("ld_ahead"), 0) and row.get("colour") == "green", "4. with LD: Look-Ahead Days = 2, " + soon + " (due in 3 days) is green")


def bad_ahead():
    p = frappe.get_doc(PARAMS)
    p.set(AHEAD, 400)
    p.save()


refused("4. LD: Look-Ahead Days of 400 is refused", bad_ahead, "LD: Look-Ahead Days")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
