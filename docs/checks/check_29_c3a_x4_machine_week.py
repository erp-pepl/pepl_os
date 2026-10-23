# PEPL OS v0.29.0 - Check 29: C3a-X4 weekly MTBF, MTTR and CPC (cost per component) per machine -
# from the submitted Shift Production Entries of last week: breakdowns, machine-hour rate, consumables, overhead,
# cost per piece, rebuild, cancel.
# Runs on 0.29.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters and Manufacturing Settings changes this check makes, is undone at the end.
VERSION = "0.29.0"
PARAMS = "PEPL System Parameters"
WEEK = "PEPL Machine Week"
SPR = "PEPL Shift Production Entry"
REBUILD = "pepl_os.pepl_production.machine_week.rebuild_machine_weeks"
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
    return abs(float(value or 0) - expected) < 0.05


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.getdate(frappe.utils.today())
MONDAY = frappe.utils.add_days(today, -today.weekday() - 7)
TUESDAY = frappe.utils.add_days(MONDAY, 1)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
print("INFO  company " + company + "; last week starts on " + str(MONDAY))


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.db.exists("DocType", WEEK)), "1. the Machine Week record (PEPL Machine Week) exists")
check(bool(frappe.db.exists("DocType", "PEPL Machine Week Item")), "1. with its Items Made table")
site_overhead = frappe.db.get_single_value(PARAMS, "custom_overhead_percent")
print("INFO  this site: Overhead (%) = " + str(site_overhead))

# ---------------- 2. masters for this run ----------------
# The operator is level 4 on the machine group, so the skill check passes in any mode.
# Test items are not sales items, so India Compliance does not ask them for an HSN/SAC code.
DAY = "CHK29 Day " + RUN
GROUP = "CHK29 MILL " + RUN
MILL = "CHK29 MILL-01 " + RUN
OP = "CHK29-OP-" + RUN
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "Workstation Type", "workstation_type": GROUP}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL, "workstation_type": GROUP}).insert()
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Check " + OP, "pin": pin,
                "skills": [{"workstation_type": GROUP, "level": "4 - Sets up and trains others"}]}).insert()
NO_LOAD = "CHK29 No Load " + RUN
SPINDLE = "CHK29 Spindle " + RUN
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": SPINDLE, "stop_type": "Unplanned", "is_breakdown": 1}).insert()


def set_params(rate):
    params = frappe.get_doc(PARAMS)
    rows = [r for r in params.get("custom_machine_hour_rates") or [] if r.machine_group != GROUP]
    params.set("custom_machine_hour_rates", [])
    for r in rows:
        params.append("custom_machine_hour_rates", {"machine_group": r.machine_group, "rate_per_hour": r.rate_per_hour})
    params.append("custom_machine_hour_rates", {"machine_group": GROUP, "rate_per_hour": rate})
    params.custom_overhead_percent = 10
    params.custom_spr_tool_photo_required = 0
    params.save()


set_params(600)
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.overproduction_percentage_for_work_order = 0
settings.save()

fg = frappe.get_doc({"doctype": "Item", "item_code": "CHK29-FG-" + RUN, "item_name": "CHK29 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert()
rm = frappe.get_doc({"doctype": "Item", "item_code": "CHK29-RM-" + RUN, "item_name": "CHK29 RM " + RUN, "item_group": "Raw Material", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert()
oil = frappe.get_doc({"doctype": "Item", "item_code": "CHK29-COOLANT-" + RUN, "item_name": "CHK29 Coolant " + RUN, "item_group": "Consumables", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert()
receipt = frappe.get_doc({
    "doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
    "set_posting_time": 1, "posting_date": frappe.utils.add_days(MONDAY, -10),
    "items": [{"item_code": oil.name, "qty": 50, "t_warehouse": wh("Consumables Stores"), "basic_rate": 10}],
}).insert()
receipt.submit()
MILLING = "CHK29 Milling " + RUN
frappe.get_doc({"doctype": "Operation", "name": MILLING, "workstation": MILL}).insert()
bom = frappe.get_doc({
    "doctype": "BOM", "item": fg.name, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
    "currency": frappe.db.get_value("Company", company, "default_currency"),
    "items": [{"item_code": rm.name, "qty": 1, "rate": 10}],
    "operations": [{"operation": MILLING, "workstation": MILL, "time_in_mins": 6}],
}).insert()
bom.submit()
material = float(frappe.db.get_value("BOM", bom.name, "raw_material_cost") or 0)
wo = frappe.get_doc({
    "doctype": "Work Order", "production_item": fg.name, "bom_no": bom.name, "qty": 10, "stock_uom": "Nos", "company": company,
    "skip_transfer": 1, "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order",
})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
card = frappe.get_all("Job Card", filters={"work_order": wo.name}, pluck="name")[0]
print("INFO  Job Card " + card + " on " + MILL + " (group " + GROUP + "); BOM raw material " + str(material) + " a piece")


def entry(day, production=None, downtime=None, consumables=None):
    doc = frappe.get_doc({"doctype": SPR, "posting_date": day, "shift": DAY, "workstation": MILL, "operator": OP, "company": company})
    for table, rows in (("production", production), ("downtime", downtime), ("consumables", consumables)):
        for row in rows or []:
            doc.append(table, row)
    doc.insert()
    doc.submit()
    return doc


def down(category, start, end):
    return {"downtime_category": category, "from_time": start, "to_time": end}


def record():
    name = frappe.db.get_value(WEEK, {"workstation": MILL, "week_start": MONDAY}, "name")
    return frappe.get_doc(WEEK, name) if name else None


# ---------------- 3. last week on the mill: MTBF and MTTR ----------------
# Monday: 4 h run (8 good, 2 rejected), 1 h spindle breakdown, 3 h no load, 3 coolant used.
# Tuesday: 30 min spindle breakdown, 2 h run (2 good), the rest no load.
mon = entry(MONDAY,
            production=[{"job_card": card, "from_time": "08:00", "to_time": "12:00", "good_qty": 8, "rejected_qty": 2, "rejection_reason": "Undersize bore"}],
            downtime=[down(SPINDLE, "12:00", "13:00"), down(NO_LOAD, "13:00", "16:00")],
            consumables=[{"item_code": oil.name, "qty": 3}])
tue = entry(TUESDAY,
            production=[{"job_card": card, "from_time": "08:30", "to_time": "10:30", "good_qty": 2}],
            downtime=[down(SPINDLE, "08:00", "08:30"), down(NO_LOAD, "10:30", "16:00")])
r = record()
check(r is not None, "3. the two entries built the Machine Week record " + (r.name if r else ""))
if r:
    print("INFO  MTBF " + str(r.mtbf_hours) + " h, MTTR " + str(r.mttr_minutes) + " min, CPC " + str(r.cpc))
    check(r.entries == 2 and r.run_minutes == 360, "3. 2 shift entries, 360 run minutes (6 hours)")
    check(r.breakdown_count == 2 and r.breakdown_minutes == 90, "3. 2 breakdowns, 90 minutes")
    check(near(r.mtbf_hours, 3.0), "3. MTBF = 6 run hours / 2 breakdowns = 3 hours")
    check(near(r.mttr_minutes, 45.0), "3. MTTR = 90 minutes / 2 breakdowns = 45 minutes")

# ---------------- 4. cost per component ----------------
if r:
    check(near(r.rate_per_hour, 600) and GROUP in (r.rate_source or ""), "4. machine-hour rate 600 taken from Machine-Hour Rates for " + GROUP)
    check(near(r.machine_cost, 3600), "4. machine cost = 6 h x 600 = 3600")
    check(near(r.consumables_cost, 30), "4. consumables = 3 coolant x 10 = 30 (Material Issue of Monday's entry)")
    check(near(r.conversion_cost, 3993), "4. conversion cost = (3600 + 30) x 1.10 overhead = 3993")
    check(near(r.cpc, 399.3), "4. machine CPC = 3993 / 10 good pieces = 399.30")
    row = r.items[0] if r.items else None
    check(row is not None and row.good_qty == 10 and row.rejected_qty == 2, "4. items made: " + fg.name + " - 10 good, 2 rejected")
    expected = (material * 12 + 3630) * 1.1
    check(row is not None and near(row.total_cost, expected), "4. item total = (material " + str(material) + " x 12 pieces + 3630) x 1.10 = " + str(round(expected, 2)))
    check(row is not None and near(row.cost_per_piece, expected / 10), "4. item CPC = total / 10 good pieces = " + str(round(expected / 10, 2)))

# ---------------- 5. rebuild after a rate change ----------------
set_params(900)
built = frappe.call(REBUILD, from_date=MONDAY, to_date=TUESDAY)
check(bool(built) and built.get("records", 0) >= 1, "5. Rebuild Machine Weeks rebuilt " + str(built.get("records") if built else 0) + " record(s)")
r = record()
check(r is not None and near(r.machine_cost, 5400), "5. with the rate at 900, machine cost = 6 h x 900 = 5400")

# ---------------- 6. cancelling an entry rebuilds the week ----------------
tue = frappe.get_doc(SPR, tue.name)
tue.cancel()
r = record()
check(r is not None and r.entries == 1 and r.breakdown_count == 1 and near(r.mttr_minutes, 60), "6. Tuesday cancelled: 1 entry, 1 breakdown, MTTR 60 minutes")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (Overhead (%) is back to " + str(site_overhead) + ").")
