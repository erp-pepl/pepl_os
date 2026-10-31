# PEPL OS v0.47.0 - Check 47: C3a-B6 shift-entry rejections go to the Scrap Register by themselves - a submitted
# entry's rejected pieces become a Scrap Weighment (source Rejection, kg = pieces x weight per unit, at the scrap
# rate, into Scrap Yard); missing weight / scrap item / rate gives Stores a ToDo; cancelling the entry takes it back.
# Runs on 0.47.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the
# end. Then look at the screens in the browser: see the steps in the chat.
VERSION = "0.47.0"
PARAMS = "PEPL System Parameters"
SPR = "PEPL Shift Production Entry"
WEIGHMENT = "PEPL Scrap Weighment"
RULE = "PRD-REJECT-SCRAP"
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


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
pmeta = frappe.get_meta(PARAMS)
check(bool(pmeta.get_field("custom_rejections_to_scrap")) and bool(pmeta.get_field("custom_rejection_scrap_item")),
      "1. System Parameters > Production > Rejections to Scrap: on/off (" + str(frappe.db.get_single_value(PARAMS, "custom_rejections_to_scrap")) + ") and Rejection Scrap Item ("
      + str(frappe.db.get_single_value(PARAMS, "custom_rejection_scrap_item") or "empty") + ")")
check(bool(frappe.get_meta("Item").get_field("custom_rejection_scrap_item")) and bool(frappe.get_meta(WEIGHMENT).get_field("shift_production_entry")),
      "1. Item has 'Scrap Item when Rejected'; Scrap Weighment has 'Shift Production Entry' and 'Rejected Pieces'")
params = frappe.get_doc(PARAMS)
params.custom_rejections_to_scrap = 1
params.custom_rejection_scrap_item = None
params.enable_operational_todos = 1
if not params.get("custom_stores_notification_owner"):
    params.custom_stores_notification_owner = "Administrator"
params.skill_check_mode = "Advisory"
params.custom_spr_tool_photo_required = 0
params.custom_spr_max_unaccounted_minutes = 15
params.save()
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.overproduction_percentage_for_work_order = 0
settings.save()

# ---------------- 2. a scrap item with a rate, a part that weighs 0.25 kg, a Job Card ----------------
BRASS = frappe.get_doc({"doctype": "Item", "item_code": "CHK47-SCRAP-" + RUN, "item_name": "CHK47 Brass Turnings " + RUN, "item_group": "Brass Scrap", "stock_uom": "Kg",
                        "is_stock_item": 1, "is_sales_item": 0, "is_purchase_item": 0}).insert().name
frappe.get_doc({"doctype": "PEPL Scrap Rate", "scrap_item": BRASS, "rate": 40, "effective_from": frappe.utils.add_days(today, -30)}).insert()
MILL = "CHK47 MILL-01 " + RUN
DAY = "CHK47 Day " + RUN
OP = "CHK47-OP-" + RUN
NO_LOAD = "CHK47 No Load " + RUN
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Ramesh " + RUN, "pin": pin}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
FG = frappe.get_doc({"doctype": "Item", "item_code": "CHK47-FG-" + RUN, "item_name": "CHK47 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1,
                     "is_sales_item": 0, "weight_per_unit": 0.25, "weight_uom": "Kg", "custom_rejection_scrap_item": BRASS}).insert().name
BO = frappe.get_doc({"doctype": "Item", "item_code": "CHK47-BO-" + RUN, "item_name": "CHK47 Bought-out " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos",
                     "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
TURNING = "CHK47 Turning " + RUN
frappe.get_doc({"doctype": "Operation", "name": TURNING, "workstation": MILL}).insert()
bom = frappe.get_doc({"doctype": "BOM", "item": FG, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
                      "currency": frappe.db.get_value("Company", company, "default_currency"), "items": [{"item_code": BO, "qty": 1, "rate": 10}],
                      "operations": [{"operation": TURNING, "workstation": MILL, "time_in_mins": 6}]}).insert()
bom.submit()
wo = frappe.get_doc({"doctype": "Work Order", "production_item": FG, "bom_no": bom.name, "qty": 40, "stock_uom": "Nos", "company": company, "skip_transfer": 1,
                     "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order"})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
CARD = frappe.get_all("Job Card", filters={"work_order": wo.name}, pluck="name")[0]
print("INFO  " + FG + " weighs 0.25 kg; when rejected it becomes " + BRASS + " at 40 a kg; Job Card " + CARD)


def entry(rejected, on):
    doc = frappe.get_doc({"doctype": SPR, "posting_date": on, "shift": DAY, "workstation": MILL, "operator": OP, "company": company})
    doc.append("production", {"job_card": CARD, "from_time": "08:00", "to_time": "10:00", "good_qty": 8, "rejected_qty": rejected, "rejection_reason": "Undersize"})
    doc.append("downtime", {"downtime_category": NO_LOAD, "from_time": "10:00", "to_time": "16:30"})
    doc.insert()
    doc.submit()
    return doc.name


def todos(name, status):
    return frappe.get_all("ToDo", filters={"reference_type": SPR, "reference_name": name, "status": status, "description": ["like", "%" + RULE + "%"]}, pluck="description")


# ---------------- 3. submitted entry -> Scrap Weighment ----------------
first = entry(4, yesterday)
ws = frappe.get_all(WEIGHMENT, filters={"shift_production_entry": first, "docstatus": 1}, fields=["name", "source", "scrap_item", "net_kg", "rate_applied", "amount", "rejected_pieces", "stock_entry", "warehouse"])
w = ws[0] if ws else {}
print("INFO  " + first + ": 8 good, 4 rejected -> " + str(w.get("name")) + " " + str(w.get("net_kg")) + " kg " + str(w.get("scrap_item")) + " at " + str(w.get("rate_applied")) + " = " + str(w.get("amount")))
check(len(ws) == 1 and w.get("source") == "Rejection" and w.get("scrap_item") == BRASS and w.get("rejected_pieces") == 4, "3. the 4 rejected pieces became Scrap Weighment " + str(w.get("name")) + " (source Rejection, " + BRASS + ")")
check(abs(frappe.utils.flt(w.get("net_kg")) - 1) < 0.001 and frappe.utils.flt(w.get("amount")) == 40, "3. weight 4 x 0.25 = 1 kg, at 40 a kg = 40")
check(bool(w.get("stock_entry")) and frappe.db.get_value("Stock Entry", w.get("stock_entry"), "docstatus") == 1 and w.get("warehouse") == wh("Scrap Yard"),
      "3. it posted Material Receipt " + str(w.get("stock_entry")) + " into " + str(w.get("warehouse")))
panel = frappe.call("pepl_os.pepl_production.spr.get_spr_panel", name=first).get("rows") or []
line = [r.get("text") for r in panel if "Scrap Weighment" in r.get("text")]
check(bool(line), "3. the entry's Shift panel says -> " + (line[0] if line else "nothing"))

# ---------------- 4. missing weight -> a ToDo for Stores ----------------
frappe.db.set_value("Item", FG, "weight_per_unit", 0)
second = entry(3, frappe.utils.add_days(today, -2))  # another day: one machine, one shift, no overlap
check(not frappe.get_all(WEIGHMENT, filters={"shift_production_entry": second}), "4. without a weight per unit nothing is posted")
open_todos = todos(second, "Open")
check(bool(open_todos) and "3 rejected piece(s)" in open_todos[0] and "weight per unit" in open_todos[0], "4. Stores gets a ToDo -> " + (open_todos[0].split("\n")[-1][:220] if open_todos else "none"))

# ---------------- 5. cancelling takes it back ----------------
frappe.get_doc(SPR, first).cancel()
check(frappe.db.get_value(WEIGHMENT, w.get("name"), "docstatus") == 2 and frappe.db.get_value("Stock Entry", w.get("stock_entry"), "docstatus") == 2,
      "5. cancelling " + first + " cancels its weighment and the scrap receipt")
frappe.get_doc(SPR, second).cancel()
check(not todos(second, "Open") and bool(todos(second, "Cancelled")), "5. cancelling " + second + " closes the Stores ToDo")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
