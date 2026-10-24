# PEPL OS v0.30.0 - Check 30: C3a-X8 job-work reconciliation - sent to a job worker, received back processed,
# returned unprocessed, balance, age (first in, first out), Overdue / GST limit near, the morning ToDo.
# Runs on 0.30.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes this check makes, is undone at the end.
VERSION = "0.30.0"
PARAMS = "PEPL System Parameters"
SUMMARY = "pepl_os.pepl_production.job_work.job_work_summary"
RUN_NOW = "pepl_os.pepl_production.job_work.run_job_work_alerts_now"
SENT = "Sent to Job Worker"
RECEIVED = "Received after Processing"
RETURNED = "Returned Unprocessed"
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
        check(words.lower() in text.lower(), label + " -> " + text[:220])
        return text


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


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.get_meta("Warehouse").get_field("custom_job_worker")), "1. Warehouse has 'Job Worker'")
check(bool(frappe.get_meta("Stock Entry").get_field("custom_job_work_movement")), "1. Stock Entry has 'Job-Work Movement'")
check(bool(frappe.get_meta(PARAMS).get_field("custom_job_work_return_days")) and bool(frappe.get_meta(PARAMS).get_field("custom_job_work_gst_warning_days")), "1. System Parameters has Production > Job-Work Return Days and GST Warning Days")
check(bool(frappe.db.exists("Report", "PEPL Job-Work Reconciliation")), "1. the report PEPL Job-Work Reconciliation exists")
site_days = frappe.db.get_single_value(PARAMS, "custom_job_work_return_days")
print("INFO  this site: Job-Work Return Days = " + str(site_days))

params = frappe.get_doc(PARAMS)
params.custom_job_work_return_days = 30
params.custom_job_work_gst_warning_days = 30
params.enable_operational_todos = 1
params.custom_production_notification_owner = frappe.session.user
params.save()

# ---------------- 2. a job worker, its store, material ----------------
# Test items are not sales items, so India Compliance does not ask them for an HSN/SAC code.
PLATER = frappe.get_doc({"doctype": "Supplier", "supplier_name": "CHK30 Platers " + RUN}).insert().name
root = frappe.db.get_value("Warehouse", wh("RM Stores"), "parent_warehouse")
STORE = frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "CHK30 Platers Store " + RUN, "company": company, "parent_warehouse": root, "custom_job_worker": PLATER}).insert().name
ROD = frappe.get_doc({"doctype": "Item", "item_code": "CHK30-ROD-" + RUN, "item_name": "CHK30 Rod " + RUN, "item_group": "Raw Material", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
PIN = frappe.get_doc({"doctype": "Item", "item_code": "CHK30-PIN-" + RUN, "item_name": "CHK30 Pin " + RUN, "item_group": "Raw Material", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
print("INFO  job worker " + PLATER + ", store " + STORE)


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


entry([(ROD, 200, None, wh("RM Stores")), (PIN, 200, None, wh("RM Stores"))], 400, purpose="Material Receipt")


def line(item):
    rows = frappe.call(SUMMARY, supplier=PLATER)["rows"]
    found = [r for r in rows if r.get("item_code") == item]
    return found[0] if found else None


# ---------------- 3. movements say what they are ----------------
out = entry([(ROD, 100, wh("RM Stores"), STORE)], 45)
check(out.custom_job_work_movement == SENT, "3. 100 rods moved to the job worker's store 45 days ago: marked 'Sent to Job Worker'")
refused("3. material coming back without saying what it is is refused", lambda: entry([(ROD, 10, STORE, wh("RM Stores"))], 10, submit=False), "Job-Work Movement")
entry([(ROD, 60, STORE, wh("RM Stores"))], 10, movement=RECEIVED)
entry([(ROD, 15, STORE, wh("RM Stores"))], 8, movement=RETURNED)
print("INFO  60 received back processed 10 days ago, 15 returned unprocessed 8 days ago")

# ---------------- 4. reconciliation ----------------
r = line(ROD)
check(r is not None, "4. the rod is outside with " + PLATER)
if r:
    print("INFO  sent " + str(r.get("sent")) + ", received " + str(r.get("received")) + ", returned " + str(r.get("returned")) + ", balance " + str(r.get("balance")) + ", " + str(r.get("days_outside")) + " days, " + str(r.get("status")))
    check(r.get("sent") == 100 and r.get("received") == 60 and r.get("returned") == 15, "4. sent 100, received 60, returned 15")
    check(r.get("balance") == 25, "4. balance at the job worker 100 - 60 - 15 = 25")
    check(abs(float(r.get("value") or 0) - 250) < 0.01, "4. value outside 25 x 10 = 250")
    check(r.get("days_outside") == 45 and r.get("status") == "Overdue", "4. outside for 45 days, over the 30 return days: Overdue")
report = frappe.call("frappe.desk.query_report.run", report_name="PEPL Job-Work Reconciliation", filters={"company": company, "supplier": PLATER, "as_on": today, "outstanding_only": 1})
rows = [x for x in (report.get("result") or []) if isinstance(x, dict) and x.get("item_code") == ROD]
check(len(rows) == 1 and rows[0].get("balance") == 25, "4. the report PEPL Job-Work Reconciliation shows the same line")

# ---------------- 5. age: first in, first out, and the GST limit ----------------
entry([(PIN, 10, wh("RM Stores"), STORE)], 340)
entry([(PIN, 10, wh("RM Stores"), STORE)], 5)
entry([(PIN, 10, STORE, wh("RM Stores"))], 2, movement=RECEIVED)
p = line(PIN)
check(p is not None and p.get("balance") == 10 and p.get("days_outside") == 5, "5. pins: the 340-day lot is back first (FIFO), the 10 still outside were sent 5 days ago")
entry([(PIN, 5, wh("RM Stores"), STORE)], 340)
p = line(PIN)
check(p is not None and p.get("status") == "GST limit near", "5. a lot outside for 340 days is within 30 days of the one-year GST limit: GST limit near")

# ---------------- 6. the morning ToDo ----------------
late = frappe.call(RUN_NOW)
check(PLATER in (late or []), "6. this morning's check finds overdue material at " + PLATER)
todos = frappe.get_all("ToDo", filters={"reference_type": "Supplier", "reference_name": PLATER, "status": "Open"}, fields=["description", "allocated_to", "priority"])
check(len(todos) == 1 and ROD in todos[0].description and PIN in todos[0].description, "6. one ToDo for the job worker naming both items (PRD-JW-OVERDUE)")
check(len(todos) == 1 and todos[0].allocated_to == frappe.session.user and todos[0].priority == "High", "6. for the Production notification owner, High (a GST limit is near)")

# ---------------- 7. everything back: clear ----------------
entry([(ROD, 25, STORE, wh("RM Stores"))], 0, movement=RECEIVED)
entry([(PIN, 15, STORE, wh("RM Stores"))], 0, movement=RETURNED)
check(line(ROD) is None and line(PIN) is None, "7. all back: nothing outside with " + PLATER)
frappe.call(RUN_NOW)
check(not frappe.get_all("ToDo", filters={"reference_type": "Supplier", "reference_name": PLATER, "status": "Open"}), "7. the next check closes the ToDo by itself")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (Job-Work Return Days is back to " + str(site_days) + ").")
