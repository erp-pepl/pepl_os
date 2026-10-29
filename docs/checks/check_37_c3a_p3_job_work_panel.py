# PEPL OS v0.37.0 - Check 37: C3a-P3 the Job-Work outstanding panel - on the job worker (Supplier): what is still
# outside, since when, due back / overdue / GST one-year limit; on the Stock Entry: what is outside for its items, and
# a red line when an entry brings back more than is outside.
# Runs on 0.37.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes it makes, is undone at the end. After the check, open a job worker's Supplier to see it.
VERSION = "0.37.0"
PARAMS = "PEPL System Parameters"
SUPPLIER_PANEL = "pepl_os.pepl_production.job_work_panel.get_supplier_job_work_panel"
ENTRY_PANEL = "pepl_os.pepl_production.job_work_panel.get_stock_entry_job_work_panel"
RECEIVED = "Received after Processing"
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
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
print("INFO  company " + company)


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def ago(days):
    return frappe.utils.add_days(today, -days)


def shown(day):
    return frappe.utils.formatdate(day)


def texts(rows):
    return " | ".join(r["text"] for r in rows)


def supplier_panel(supplier):
    data = frappe.call(SUPPLIER_PANEL, supplier=supplier)
    print("INFO  panel of " + supplier + ": " + texts(data["rows"]) + " [" + ", ".join(r["colour"] for r in data["rows"]) + "]")
    return data


def entry_panel(name):
    rows = frappe.call(ENTRY_PANEL, stock_entry=name)["rows"]
    print("INFO  panel of " + name + ": " + texts(rows))
    return rows


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
# Every date this check posts is within the last 60 days, so it needs an active Fiscal Year covering them.
fy = frappe.get_all("Fiscal Year", filters={"disabled": 0, "year_start_date": ["<=", ago(60)], "year_end_date": [">=", today]}, pluck="name")
check(bool(fy), "1. an active Fiscal Year covers the last 60 days (" + (", ".join(fy) if fy else "none - add one in Accounting > Fiscal Year") + ")")


def set_days(return_days, gst_warning_days):
    params = frappe.get_doc(PARAMS)
    params.custom_job_work_return_days = return_days
    params.custom_job_work_gst_warning_days = gst_warning_days
    params.save()


set_days(30, 30)

# ---------------- 2. a job worker, its store, material ----------------
# Bought-out items (no heat number needed, C2-15) that are not sales items (no HSN needed).
WORKER = frappe.get_doc({"doctype": "Supplier", "supplier_name": "CHK37 Heat Treaters " + RUN}).insert().name
PLAIN = frappe.get_doc({"doctype": "Supplier", "supplier_name": "CHK37 Ordinary Supplier " + RUN}).insert().name
root = frappe.db.get_value("Warehouse", wh("Bought-Out Stores"), "parent_warehouse")
STORE = frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "CHK37 Heat Treaters Store " + RUN, "company": company, "parent_warehouse": root, "custom_job_worker": WORKER}).insert().name
BO = wh("Bought-Out Stores")
GEAR = frappe.get_doc({"doctype": "Item", "item_code": "CHK37-GEAR-" + RUN, "item_name": "CHK37 Gear " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
PIN = frappe.get_doc({"doctype": "Item", "item_code": "CHK37-PIN-" + RUN, "item_name": "CHK37 Pin " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
print("INFO  job worker " + WORKER + ", store " + STORE)


def entry(rows, days_ago, purpose="Material Transfer", movement=None, submit=True):
    doc = frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": purpose, "purpose": purpose, "company": company,
        "set_posting_time": 1, "posting_date": ago(days_ago),
        "items": [{"item_code": r[0], "qty": r[1], "s_warehouse": r[2], "t_warehouse": r[3], "basic_rate": 10} for r in rows],
    })
    if movement:
        doc.custom_job_work_movement = movement
    doc.insert()
    if submit:
        doc.submit()
    return doc


entry([(GEAR, 200, None, BO), (PIN, 200, None, BO)], 60, purpose="Material Receipt")

# ---------------- 3. the Supplier panel ----------------
check(not frappe.call(SUPPLIER_PANEL, supplier=PLAIN)["job_worker"], "3. an ordinary supplier (no job-worker store) gets no panel")
data = supplier_panel(WORKER)
check(data["job_worker"] and "Nothing outside" in texts(data["rows"]) and data["rows"][0]["colour"] == "green", "3. the job worker with nothing outside: 'Nothing outside with this job worker', green")

entry([(GEAR, 40, BO, STORE)], 10)
entry([(GEAR, 15, STORE, BO)], 2, movement=RECEIVED)
rows = supplier_panel(WORKER)["rows"]
check("1 item(s) outside" in rows[0]["text"] and rows[0]["colour"] == "green", "3. 40 gears sent 10 days ago, 15 back: headline '1 item(s) outside', green")
check(GEAR + ": 25 Nos outside since " + shown(ago(10)) + " (10 days)" in texts(rows), "3. the gear line: 25 Nos outside since " + shown(ago(10)) + " (10 days)")
check("due back by " + shown(frappe.utils.add_days(ago(10), 30)) in texts(rows), "3. due back by " + shown(frappe.utils.add_days(ago(10), 30)) + " (sent + 30 return days)")
check("250" in rows[0]["text"], "3. the headline gives the value outside: 25 x 10 = 250")

entry([(PIN, 10, BO, STORE)], 40)
rows = supplier_panel(WORKER)["rows"]
check(rows[0]["colour"] == "orange" and "1 overdue or near the GST limit" in rows[0]["text"], "3. pins sent 40 days ago: the headline turns orange, '1 overdue or near the GST limit'")
check(rows[1]["text"].startswith(PIN) and "10 days overdue" in rows[1]["text"] and rows[1]["colour"] == "orange", "3. the overdue pins come first: '10 days overdue', orange")

set_days(30, 330)  # the GST one-year limit is near once 365 - 330 = 35 days have passed
rows = supplier_panel(WORKER)["rows"]
check(rows[0]["colour"] == "red" and "GST one-year limit on " + shown(frappe.utils.add_days(ago(40), 365)) in rows[1]["text"] and rows[1]["colour"] == "red", "3. with GST Warning Days 330 the pins are near the GST limit (" + shown(frappe.utils.add_days(ago(40), 365)) + "): red")
set_days(30, 30)

# ---------------- 4. the Stock Entry panel ----------------
other = entry([(PIN, 5, BO, wh("FG Stores"))], 1)
check(entry_panel(other.name) == [], "4. an entry that does not touch a job worker's store gets no panel")
draft = entry([(GEAR, 10, STORE, BO)], 0, movement=RECEIVED, submit=False)
rows = entry_panel(draft.name)
check("At job worker " + WORKER + " now (before this entry): 1 of these item(s) outside" in texts(rows) and PIN not in texts(rows), "4. a draft bringing gears back shows what is outside for its own items only (25 gears)")
check("but only" not in texts(rows), "4. bringing back 10 of the 25 outside: no warning")
too_many = entry([(GEAR, 20, STORE, BO)], 0, movement=RECEIVED, submit=False)
# the draft is then changed to 30 (a typing slip the panel should catch before submit)
frappe.db.set_value("Stock Entry Detail", too_many.items[0].name, {"qty": 30, "transfer_qty": 30})
rows = entry_panel(too_many.name)
check(any("brings back 30 Nos" in r["text"] and "only 25 is outside" in r["text"] and r["colour"] == "red" for r in rows), "4. a draft bringing back 30 when 25 are outside: red line 'brings back 30 Nos ... but only 25 is outside'")
draft = frappe.get_doc("Stock Entry", draft.name)
draft.submit()
check("(after this entry)" in texts(entry_panel(draft.name)) and "15 Nos outside" in texts(entry_panel(draft.name)), "4. once submitted: 'after this entry', 15 gears outside")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
