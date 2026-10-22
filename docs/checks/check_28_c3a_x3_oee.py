# PEPL OS v0.28.0 - Check 28: C3a-X3 daily OEE per machine from the submitted Shift Production Entries -
# availability, performance, quality, OEE, PM rule, target, rebuild, cancel.
# Runs on 0.28.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters and Manufacturing Settings changes this check makes, is undone at the end.
VERSION = "0.28.0"
PARAMS = "PEPL System Parameters"
OEE = "PEPL OEE Daily"
SPR = "PEPL Shift Production Entry"
REBUILD = "pepl_os.pepl_production.oee.rebuild_oee"
passed = []
failed = []


def check(ok, label):
    if ok:
        passed.append(label)
        print("PASS  " + label)
    else:
        failed.append(label)
        print("FAIL  " + label)


def near(value, expected):
    return abs(float(value or 0) - expected) < 0.01


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
yesterday = frappe.utils.add_days(frappe.utils.today(), -1)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
print("INFO  company " + company + "; shift date " + str(yesterday))


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.db.exists("DocType", OEE)), "1. the Daily OEE record (PEPL OEE Daily) exists")
check(bool(frappe.get_meta(PARAMS).get_field("custom_oee_target_percent")), "1. System Parameters has Production > OEE Target %")
site_target = frappe.db.get_single_value(PARAMS, "custom_oee_target_percent")
site_pm = frappe.db.get_single_value(PARAMS, "oee_planned_time_excludes_pm")
print("INFO  this site: OEE Target % = " + str(site_target) + ", Exclude PM/Calibration from Planned Time = " + str(site_pm))


def set_params(target=65, exclude_pm=1):
    params = frappe.get_doc(PARAMS)
    params.custom_oee_target_percent = target
    params.oee_planned_time_excludes_pm = exclude_pm
    params.custom_spr_tool_photo_required = 0
    params.save()


set_params()
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.overproduction_percentage_for_work_order = 0
settings.save()

# ---------------- 2. masters for this run ----------------
# Machines without a machine group: the skill check says "Not checked" and never blocks, whatever this site's mode.
# Test items are not sales items, so India Compliance does not ask them for an HSN/SAC code.
DAY = "CHK28 Day " + RUN
MILL = "CHK28 MILL-01 " + RUN
DRILL = "CHK28 DRILL-02 " + RUN
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": DRILL}).insert()
OP = "CHK28-OP-" + RUN
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Check " + OP, "pin": pin}).insert()
NO_LOAD = "CHK28 No Load " + RUN
SPINDLE = "CHK28 Spindle " + RUN
WAIT = "CHK28 Waiting " + RUN
PM = "CHK28 PM " + RUN
for name, stop, breakdown in ((NO_LOAD, "Planned", 0), (SPINDLE, "Unplanned", 1), (WAIT, "Unplanned", 0), (PM, "PM / Calibration", 0)):
    frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": name, "stop_type": stop, "is_breakdown": breakdown}).insert()

fg = frappe.get_doc({"doctype": "Item", "item_code": "CHK28-FG-" + RUN, "item_name": "CHK28 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert()
rm = frappe.get_doc({"doctype": "Item", "item_code": "CHK28-RM-" + RUN, "item_name": "CHK28 RM " + RUN, "item_group": "Raw Material", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert()
MILLING = "CHK28 Milling " + RUN
frappe.get_doc({"doctype": "Operation", "name": MILLING, "workstation": MILL}).insert()
bom = frappe.get_doc({
    "doctype": "BOM", "item": fg.name, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
    "currency": frappe.db.get_value("Company", company, "default_currency"),
    "items": [{"item_code": rm.name, "qty": 1, "rate": 10}],
    "operations": [{"operation": MILLING, "workstation": MILL, "time_in_mins": 6}],
}).insert()
bom.submit()
wo = frappe.get_doc({
    "doctype": "Work Order", "production_item": fg.name, "bom_no": bom.name, "qty": 10, "stock_uom": "Nos", "company": company,
    "skip_transfer": 1, "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order",
})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
card = frappe.get_all("Job Card", filters={"work_order": wo.name}, pluck="name")[0]
print("INFO  Job Order " + wo.name + " -> Job Card " + card + ": 10 pieces at 6 standard minutes on " + MILL)


def entry(machine, production=None, downtime=None):
    doc = frappe.get_doc({"doctype": SPR, "posting_date": yesterday, "shift": DAY, "workstation": machine, "operator": OP, "company": company})
    for row in production or []:
        doc.append("production", row)
    for row in downtime or []:
        doc.append("downtime", row)
    doc.insert()
    doc.submit()
    return doc


def down(category, start, end):
    return {"downtime_category": category, "from_time": start, "to_time": end}


def record(machine):
    name = frappe.db.get_value(OEE, {"workstation": machine, "oee_date": yesterday}, "name")
    return frappe.get_doc(OEE, name) if name else None


# ---------------- 3. a shift entry builds the machine's day ----------------
# 08:00-12:00 run, 8 good + 2 rejected; 12-13 planned stop; 13-14 spindle breakdown; 14-16 waiting = the 480 planned minutes
e1 = entry(MILL,
           production=[{"job_card": card, "from_time": "08:00", "to_time": "12:00", "good_qty": 8, "rejected_qty": 2, "rejection_reason": "Undersize bore"}],
           downtime=[down(NO_LOAD, "12:00", "13:00"), down(SPINDLE, "13:00", "14:00"), down(WAIT, "14:00", "16:00")])
r = record(MILL)
check(r is not None, "3. submitting the shift entry built the Daily OEE record " + (r.name if r else ""))
if r:
    print("INFO  A " + str(r.availability) + " % x P " + str(r.performance) + " % x Q " + str(r.quality) + " % = OEE " + str(r.oee) + " %")
    check(r.planned_minutes == 480 and r.planned_stop_minutes == 60, "3. planned 480 minutes, 60 of them a planned stop")
    check(r.planned_production_minutes == 420, "3. planned production time 420 minutes")
    check(r.run_minutes == 240 and r.unplanned_stop_minutes == 180, "3. run 240 minutes, unplanned stops 180")
    check(r.breakdown_count == 1 and r.breakdown_minutes == 60, "3. one breakdown of 60 minutes")
    check(near(r.ideal_minutes, 60), "3. standard minutes of the 10 pieces made: 10 x 6 = 60")
    check(near(r.availability, 57.14), "3. availability 240 / 420 = 57.14 %")
    check(near(r.performance, 25.0), "3. performance 60 / 240 = 25 %")
    check(near(r.quality, 80.0), "3. quality 8 / 10 = 80 %")
    check(near(r.oee, 11.43), "3. OEE 57.14 % x 25 % x 80 % = 11.43 %")
    check(near(r.target, 65) and r.below_target == 1, "3. compared with the 65 % target: Below Target")

# ---------------- 4. PM / Calibration and the rebuild ----------------
e2 = entry(DRILL, downtime=[down(PM, "08:00", "09:00"), down(NO_LOAD, "09:00", "16:00")])
r2 = record(DRILL)
check(r2 is not None and r2.pm_minutes == 60 and r2.planned_production_minutes == 0, "4. PM left out of planned time (parameter on): 480 - 420 planned stop - 60 PM = 0")
set_params(exclude_pm=0)
built = frappe.call(REBUILD, from_date=yesterday)
check(bool(built) and built.get("records", 0) >= 2, "4. Rebuild OEE for the day rebuilt " + str(built.get("records") if built else 0) + " record(s)")
r2 = record(DRILL)
check(r2 is not None and r2.planned_production_minutes == 60 and r2.unplanned_stop_minutes == 60, "4. parameter off: PM is an unplanned stop (planned production 60, unplanned 60)")

# ---------------- 5. target from System Parameters ----------------
set_params(target=10, exclude_pm=1)
frappe.call(REBUILD, from_date=yesterday)
r = record(MILL)
check(r is not None and near(r.target, 10) and r.below_target == 0, "5. with the target at 10 %, the 11.43 % day is no longer Below Target")

# ---------------- 6. cancelling the entry removes the day ----------------
e2 = frappe.get_doc(SPR, e2.name)
e2.cancel()
check(record(DRILL) is None, "6. cancelling the drill's only entry removed its Daily OEE record")
check(record(MILL) is not None, "6. the mill's record is untouched")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (OEE Target % is back to " + str(site_target) + ").")
