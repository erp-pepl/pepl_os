# PEPL OS v0.40.0 - Check 39 rev 2: C3a-P5 entry aids on the Shift Production Entry - the gaps no row covers (other
# operators' entries counted, "Add rows for the gaps"), what is left on each Job Card, speed against the standard,
# open Job Cards on the machine; and the Shift panel's quantities without ".0". Rev 2 (v0.40.0, C3a-C1): slow / fast
# is judged by the pepl_sales "Cycle Deviation Threshold Low / High" (0.8 / 1.2), the one measure for it.
# Runs on 0.40.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters change it makes, is undone at the end. After the check, open any Shift Production Entry.
VERSION = "0.40.0"
PARAMS = "PEPL System Parameters"
SPR = "PEPL Shift Production Entry"
HIGH = "cycle_deviation_threshold_high"
LOW = "cycle_deviation_threshold_low"
AIDS = "pepl_os.pepl_production.spr_aids.get_spr_aids"
SHIFT_PANEL = "pepl_os.pepl_production.spr.get_spr_panel"
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


def texts(rows):
    return " | ".join(r["text"] for r in rows)


def aids(name):
    data = frappe.call(AIDS, name=name)
    print("INFO  entry aids of " + name + ": " + texts(data["rows"]) + " [" + ", ".join(r["colour"] for r in data["rows"]) + "]")
    return data


def find(rows, start):
    found = [r for r in rows if r["text"].startswith(start)]
    return found[0] if found else {"text": "", "colour": ""}


def set_band(low, high):
    params = frappe.get_doc(PARAMS)
    params.set(LOW, low)
    params.set(HIGH, high)
    params.custom_spr_tool_photo_required = 0
    params.custom_spr_max_unaccounted_minutes = 15
    params.save()


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(not frappe.get_meta(PARAMS).get_field("custom_spr_slow_speed_percent"), "1. the v0.39.0 field 'Shift Entry: Slow Below % of Standard Speed' is gone (one measure: the cycle deviation band)")
site_band = str(frappe.db.get_single_value(PARAMS, LOW)) + " / " + str(frappe.db.get_single_value(PARAMS, HIGH))
print("INFO  this site: Cycle Deviation Threshold Low / High = " + site_band)
set_band(0.8, 1.2)
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.overproduction_percentage_for_work_order = 0
settings.save()

# ---------------- 2. a machine, a shift, two operators, two Job Cards ----------------
# The machine has no machine group, so the skill check says "Not checked" and never blocks.
DAY = "CHK39 Day " + RUN
MILL = "CHK39 MILL-01 " + RUN
OP1 = "CHK39-OP1-" + RUN
OP2 = "CHK39-OP2-" + RUN
NO_LOAD = "CHK39 No Load " + RUN
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
for code in (OP1, OP2):
    frappe.get_doc({"doctype": "PEPL Operator", "employee_code": code, "operator_name": "Check " + code, "pin": pin}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
FG = frappe.get_doc({"doctype": "Item", "item_code": "CHK39-FG-" + RUN, "item_name": "CHK39 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert().name
BO = frappe.get_doc({"doctype": "Item", "item_code": "CHK39-BO-" + RUN, "item_name": "CHK39 Bought-out " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
MILLING = "CHK39 Milling " + RUN
frappe.get_doc({"doctype": "Operation", "name": MILLING, "workstation": MILL}).insert()
bom = frappe.get_doc({"doctype": "BOM", "item": FG, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
                      "currency": frappe.db.get_value("Company", company, "default_currency"), "items": [{"item_code": BO, "qty": 1, "rate": 10}],
                      "operations": [{"operation": MILLING, "workstation": MILL, "time_in_mins": 6}]}).insert()
bom.submit()


def job_card(qty):
    wo = frappe.get_doc({"doctype": "Work Order", "production_item": FG, "bom_no": bom.name, "qty": qty, "stock_uom": "Nos", "company": company,
                         "skip_transfer": 1, "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order"})
    wo.get_items_and_operations_from_bom()
    wo.insert()
    wo.submit()
    return frappe.get_all("Job Card", filters={"work_order": wo.name}, pluck="name")[0]


CARD = job_card(10)
OTHER_CARD = job_card(5)
check(bool(CARD) and bool(OTHER_CARD), "2. Job Cards " + CARD + " (10 pieces, 6 min a piece) and " + OTHER_CARD + " (5 pieces) are open on " + MILL)


def entry(operator, production, downtime):
    doc = frappe.get_doc({"doctype": SPR, "posting_date": yesterday, "shift": DAY, "workstation": MILL, "operator": operator, "company": company})
    for row in production:
        doc.append("production", row)
    for row in downtime:
        doc.append("downtime", row)
    return doc.insert()


# ---------------- 3. gaps no row covers ----------------
a = entry(OP1, [{"job_card": CARD, "from_time": "08:00", "to_time": "09:00", "good_qty": 6, "rejected_qty": 1, "rejection_reason": "Undersize"}],
          [{"downtime_category": NO_LOAD, "from_time": "10:30", "to_time": "12:00"}])
data = aids(a.name)
rows = data["rows"]
check("2 gap(s) in the shift not covered by any row, 360 min" in rows[0]["text"] and "30-minute break is one of them" in rows[0]["text"], "3. production 08:00-09:00 and a stop 10:30-12:00: 2 gaps, 360 min (the 30-minute break is one of them)")
check(rows[0]["colour"] == "orange", "3. 360 min is more than the break + 15 minutes allowed: orange")
check("Not covered: 09:00-10:30 (90 min)" in texts(rows) and "Not covered: 12:00-16:30 (270 min)" in texts(rows), "3. the gaps are listed: 09:00-10:30 and 12:00-16:30")
check(len(data["gaps"]) == 2 and data["gaps"][0]["from_time"] == "09:00:00" and data["gaps"][1]["to_time"] == "16:30:00", "3. 'Add rows for the gaps' would add 2 downtime rows: 09:00-10:30 and 12:00-16:30")
b = entry(OP2, [], [{"downtime_category": NO_LOAD, "from_time": "12:00", "to_time": "16:30"}])
rows = aids(a.name)["rows"]
check("1 gap(s)" in rows[0]["text"] and "Not covered: 09:00-10:30 (90 min)" in texts(rows) and "12:00-16:30" not in texts(rows), "3. " + OP2 + "'s entry " + b.name + " covers 12:00-16:30: only 09:00-10:30 is left")

# ---------------- 4. Job Card left, speed ----------------
check("Job Card " + CARD + ": target 10, done before 0, this entry 6 - 4 left" in texts(rows), "4. Job Card line: target 10, done before 0, this entry 6 - 4 left")
speed = find(rows, "Row 1:")
check("7 piece(s) x 6 min standard = 42 min; took 60 min - 70% of standard speed" in speed["text"] and speed["colour"] == "orange", "4. row 1: 7 pieces x 6 min = 42 min in 60 min (cycle x 1.43, over x 1.2): orange")
check("slower than standard x 1.2: check the time and the quantity" in speed["text"], "4. the slow row says 'slower than standard x 1.2: check the time and the quantity'")
set_band(0.8, 1.5)
check(find(aids(a.name)["rows"], "Row 1:")["colour"] == "green", "4. with Cycle Deviation Threshold High at 1.5: the same row (x 1.43) is green")
set_band(0.8, 1.2)

# ---------------- 5. open Job Cards, Shift panel ----------------
rows = aids(a.name)["rows"]
check("Open on this machine: Job Card " + OTHER_CARD in texts(rows) and "Open on this machine: Job Card " + CARD not in texts(rows), "5. the other open Job Card on the machine is offered; the one already on the entry is not")
shift_rows = frappe.call(SHIFT_PANEL, name=a.name)["rows"]
print("INFO  Shift panel: " + texts(shift_rows))
check("Good 6 · Rejected 1 (14.29%)" in texts(shift_rows), "5. the Shift panel says 'Good 6 · Rejected 1 (14.29%)' (no '6.0')")

# ---------------- 6. every minute covered ----------------
a = frappe.get_doc(SPR, a.name)
a.append("downtime", {"downtime_category": NO_LOAD, "from_time": "09:00", "to_time": "10:30"})
a.save()
data = aids(a.name)
check(data["rows"][0]["text"] == "Every minute of the shift is covered by a row" and data["rows"][0]["colour"] == "green" and data["gaps"] == [], "6. with a stop 09:00-10:30 added: 'Every minute of the shift is covered by a row', green, no gap rows to add")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (the cycle deviation band is back to " + site_band + ").")
