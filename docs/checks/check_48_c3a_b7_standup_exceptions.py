# PEPL OS v0.48.0 - Check 48: C3a-B7 the Daily Stand-up, exception-only - only what needs attention (machines below
# the OEE target, unplanned stops of at least the minimum, machines without an entry, delivery risk, LD running,
# work waiting, job work overdue, rejections to weigh), numbered as shown; untick the setting for the full page.
# Runs on 0.48.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the
# end. The test day is 150 days ago, so this bench's own shift entries do not mix in.
VERSION = "0.48.0"
PARAMS = "PEPL System Parameters"
SPR = "PEPL Shift Production Entry"
STANDUP = "PEPL Daily Standup"
BUILD = "pepl_os.pepl_production.standup.build_standup_now"
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


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
D = frappe.utils.add_days(today, -150)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def settings(exception_only, min_stop, target):
    p = frappe.get_doc(PARAMS)
    p.custom_standup_exception_only = exception_only
    p.custom_standup_min_stop_minutes = min_stop
    p.custom_oee_target_percent = target
    p.save()


def page():
    name = frappe.call(BUILD, day=D).get("name")
    return frappe.get_doc(STANDUP, name)


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
pmeta = frappe.get_meta(PARAMS)
check(bool(pmeta.get_field("custom_standup_exception_only")) and bool(pmeta.get_field("custom_standup_min_stop_minutes")),
      "1. System Parameters > Production: Stand-up: Exception-Only (" + str(frappe.db.get_single_value(PARAMS, "custom_standup_exception_only")) + "), Minimum Stop Minutes ("
      + str(frappe.db.get_single_value(PARAMS, "custom_standup_min_stop_minutes")) + ")")
smeta = frappe.get_meta(STANDUP)
check(bool(smeta.get_field("exceptions")) and bool(smeta.get_field("all_clear")), "1. the Daily Stand-up record has 'Things Needing Attention' and 'All Clear'")
p = frappe.get_doc(PARAMS)
p.skill_check_mode = "Advisory"
p.custom_spr_tool_photo_required = 0
p.custom_spr_max_unaccounted_minutes = 15
p.save()
settings(1, 30, 85)
s = frappe.get_doc("Manufacturing Settings")
s.disable_capacity_planning = 1
s.save()

# ---------------- 2. a day on the shop floor, 150 days ago ----------------
MILL = "CHK48 MILL-01 " + RUN
LATHE = "CHK48 LATHE-01 " + RUN
DAY = "CHK48 Day " + RUN
OP = "CHK48-OP-" + RUN
NO_LOAD = "CHK48 No Load " + RUN
SPINDLE = "CHK48 Spindle " + RUN
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": LATHE}).insert()
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Ramesh " + RUN, "pin": pin}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": SPINDLE, "stop_type": "Unplanned", "is_breakdown": 1}).insert()
FG = frappe.get_doc({"doctype": "Item", "item_code": "CHK48-FG-" + RUN, "item_name": "CHK48 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert().name
BO = frappe.get_doc({"doctype": "Item", "item_code": "CHK48-BO-" + RUN, "item_name": "CHK48 Bought-out " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1,
                     "is_sales_item": 0, "valuation_rate": 10}).insert().name
TURNING = "CHK48 Turning " + RUN
frappe.get_doc({"doctype": "Operation", "name": TURNING, "workstation": MILL}).insert()
bom = frappe.get_doc({"doctype": "BOM", "item": FG, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
                      "currency": frappe.db.get_value("Company", company, "default_currency"), "items": [{"item_code": BO, "qty": 1, "rate": 10}],
                      "operations": [{"operation": TURNING, "workstation": MILL, "time_in_mins": 6}]}).insert()
bom.submit()
wo = frappe.get_doc({"doctype": "Work Order", "production_item": FG, "bom_no": bom.name, "qty": 10, "stock_uom": "Nos", "company": company, "skip_transfer": 1,
                     "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order"})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
CARD = frappe.get_all("Job Card", filters={"work_order": wo.name}, pluck="name")[0]
mill = frappe.get_doc({"doctype": SPR, "posting_date": D, "shift": DAY, "workstation": MILL, "operator": OP, "company": company})
mill.append("production", {"job_card": CARD, "from_time": "08:00", "to_time": "12:00", "good_qty": 10})
mill.append("downtime", {"downtime_category": SPINDLE, "from_time": "12:00", "to_time": "13:00"})
mill.append("downtime", {"downtime_category": NO_LOAD, "from_time": "13:00", "to_time": "16:30"})
mill.insert()
mill.submit()
lathe = frappe.get_doc({"doctype": SPR, "posting_date": frappe.utils.add_days(D, -5), "shift": DAY, "workstation": LATHE, "operator": OP, "company": company})
lathe.append("downtime", {"downtime_category": NO_LOAD, "from_time": "08:00", "to_time": "16:30"})
lathe.insert()
lathe.submit()
print("INFO  " + D + ": " + MILL + " 4 h run, 60 min spindle breakdown (unplanned), 210 min no load (planned); " + LATHE + " worked 5 days earlier, nothing on " + D)

# ---------------- 3. exception-only ----------------
doc = page()
html = doc.summary
print("INFO  stand-up " + doc.name + ": " + str(doc.exceptions) + " thing(s) need attention, all clear = " + str(doc.all_clear))
check("thing(s) need attention" in html and doc.all_clear == 0 and doc.exceptions >= 3, "3. the heading says how many things need attention (" + str(doc.exceptions) + ")")
check("Machines below the OEE target" in html and MILL in html, "3. " + MILL + " is listed below the 85 % OEE target")
check("Unplanned stops of 30 minutes or more" in html and SPINDLE in html and "breakdown" in html, "3. the 60-minute spindle stop is listed, marked breakdown")
check(NO_LOAD not in html, "3. the planned 'no load' stop is not an exception, so it is not listed")
check("Machines without a shift entry" in html and LATHE in html, "3. " + LATHE + " (worked 5 days earlier, no entry on the day) is listed")
check("1. Shop floor yesterday" not in html, "3. the full machine-by-machine table is not on the exception page")

# ---------------- 4. thresholds ----------------
settings(1, 90, 1)
html = page().summary
check(SPINDLE not in html, "4. with Minimum Stop Minutes = 90 the 60-minute stop is left out")
check("Machines below the OEE target" not in html and "machines at or above the OEE target." in html, "4. with an OEE target of 1 % no machine is below it: one line says so")

# ---------------- 5. the full page, and the setting ----------------
settings(0, 30, 85)
doc = page()
check("1. Shop floor yesterday" in doc.summary and NO_LOAD in doc.summary and "need attention" not in doc.summary, "5. Exception-Only unticked: the full page as before (every machine, every stop)")
settings(1, 30, 85)
refused("5. a negative Minimum Stop Minutes is refused", lambda: settings(1, -1, 85), "Minimum Stop Minutes")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
