# PEPL OS v0.43.0 - Check 43: C3a-B2 Estimate vs Actual Cost - the CST estimate a piece against what a Job Order
# really cost a piece (material, machining with consumables, job work & other, overhead), red above the Variance
# Warning %, by Job Order and by item.
# Runs on 0.43.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the
# end. Then open the report in the browser: see the steps in the chat.
VERSION = "0.43.0"
PARAMS = "PEPL System Parameters"
SPR = "PEPL Shift Production Entry"
REPORT = "PEPL Estimate vs Actual Cost"
WARNING = "custom_cost_variance_warning_percent"
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
    return a is not None and abs(flt(a) - flt(b)) <= 0.011


def flt(value):
    return frappe.utils.flt(value)


def run_report(filters):
    out = frappe.call("frappe.desk.query_report.run", report_name=REPORT, filters=filters)
    return out


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(frappe.db.get_value("Report", REPORT, "report_type") == "Script Report", "1. report '" + REPORT + "' exists")
meta = frappe.get_meta(PARAMS)
check(bool(meta.get_field(WARNING)), "1. System Parameters > Production has 'Costing: Variance Warning %' (this site: " + str(frappe.db.get_single_value(PARAMS, WARNING)) + ")")
links = frappe.get_all("Workspace Link", filters={"parent": "Production Command Centre", "link_to": REPORT}, pluck="label")
check(bool(links), "1. the Production Command Centre lists the report under Reports")

# ---------------- 2. a machine, its rate, a Job Order and its CST ----------------
GROUP = "CHK43 MILL " + RUN
MILL = "CHK43 MILL-01 " + RUN
DAY = "CHK43 Day " + RUN
OP = "CHK43-OP-" + RUN
NO_LOAD = "CHK43 No Load " + RUN
OIL = "CHK43-COOLANT-" + RUN
frappe.get_doc({"doctype": "Workstation Type", "workstation_type": GROUP}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL, "workstation_type": GROUP}).insert()
params = frappe.get_doc(PARAMS)
params.append("custom_machine_hour_rates", {"machine_group": GROUP, "rate_per_hour": 600})
params.custom_overhead_percent = 10
params.set(WARNING, 10)
params.custom_spr_tool_photo_required = 0
params.custom_spr_max_unaccounted_minutes = 15
params.skill_check_mode = "Advisory"
params.save()
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.overproduction_percentage_for_work_order = 0
settings.save()
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Ramesh " + RUN, "pin": pin}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
frappe.get_doc({"doctype": "Item", "item_code": OIL, "item_name": "CHK43 Coolant " + RUN, "item_group": "Consumables", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert()
receipt = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
                          "items": [{"item_code": OIL, "qty": 100, "t_warehouse": wh("Consumables Stores"), "basic_rate": 10}]}).insert()
receipt.submit()
FG = frappe.get_doc({"doctype": "Item", "item_code": "CHK43-FG-" + RUN, "item_name": "CHK43 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert().name
BO = frappe.get_doc({"doctype": "Item", "item_code": "CHK43-BO-" + RUN, "item_name": "CHK43 Bought-out " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
TURNING = "CHK43 Turning " + RUN
frappe.get_doc({"doctype": "Operation", "name": TURNING, "workstation": MILL}).insert()
bom = frappe.get_doc({"doctype": "BOM", "item": FG, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
                      "currency": frappe.db.get_value("Company", company, "default_currency"), "items": [{"item_code": BO, "qty": 1, "rate": 10}],
                      "operations": [{"operation": TURNING, "workstation": MILL, "time_in_mins": 6}]}).insert()
bom.submit()
wo = frappe.get_doc({"doctype": "Work Order", "production_item": FG, "bom_no": bom.name, "qty": 10, "stock_uom": "Nos", "company": company,
                     "skip_transfer": 1, "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order"})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
CARD = frappe.get_all("Job Card", filters={"work_order": wo.name}, pluck="name")[0]
rm_group = (frappe.get_all("PEPL RM Group", pluck="name", limit=1) or [None])[0]
if not rm_group:
    rm_group = frappe.get_doc({"doctype": "PEPL RM Group", "group_name": "CHK43 Rod " + RUN, "material_base": "Brass", "default_uom": "Kg", "is_active": 1, "auto_sync_to_item_group": 0}).insert().name
product = frappe.get_doc({"doctype": "PEPL Product Master", "product_name": "CHK43 Product " + RUN, "product_type": "Single Component", "status": "Active", "linked_item": FG}).insert().name
draft = frappe.get_doc({"doctype": "PEPL CST Cost Sheet", "cst_title": "CHK43 draft " + RUN, "linked_product": product, "linked_item": FG, "status": "Draft",
                        "costing_date": today, "overhead_percent": 10,
                        "components": [{"manufactured_or_bought_out": "Manufactured", "rm_group": rm_group, "quantity_per_assembly": 1, "raw_material_cost": 1}]}).insert().name
cst = frappe.get_doc({"doctype": "PEPL CST Cost Sheet", "cst_title": "CHK43 " + RUN, "linked_product": product, "linked_item": FG, "status": "Approved",
                      "costing_date": frappe.utils.add_days(today, -1), "overhead_percent": 10,
                      "components": [{"manufactured_or_bought_out": "Manufactured", "rm_group": rm_group, "quantity_per_assembly": 1, "raw_material_cost": 12,
                                      "machining_cost": 250, "surface_treatment_cost": 20, "component_other_charges": 5}]}).insert()
print("INFO  Job Order " + wo.name + " for 10 x " + FG + "; Job Card " + CARD + "; CST " + cst.name + " (Approved) and " + draft + " (Draft, must be ignored)")
check(near(cst.total_components_cost + cst.overhead_amount, 315.7), "2. the CST costs 287 + 10% overhead = 315.70 a piece (CST says " + str(cst.total_components_cost + cst.overhead_amount) + ")")

# ---------------- 3. before anything is made ----------------
out = run_report({"job_order": wo.name})
rows = out.get("result") or []
check(len(rows) == 1 and rows[0].get("cst") == cst.name and near(rows[0].get("est_total"), 315.7), "3. the estimate is the Approved CST " + cst.name + ", not the Draft: 315.70 a piece")
check(rows[0].get("act_total") is None and "Nothing made yet" in (rows[0].get("notes") or ""), "3. nothing made yet: no actual a piece, and the note says so -> " + str(rows[0].get("notes")))

# ---------------- 4. one shift on the Job Card ----------------
entry = frappe.get_doc({"doctype": SPR, "posting_date": today, "shift": DAY, "workstation": MILL, "operator": OP, "company": company})
entry.append("production", {"job_card": CARD, "from_time": "08:00", "to_time": "12:00", "good_qty": 8, "rejected_qty": 2, "rejection_reason": "Undersize"})
entry.append("downtime", {"downtime_category": NO_LOAD, "from_time": "12:00", "to_time": "16:30"})
entry.append("consumables", {"item_code": OIL, "qty": 3})
entry.insert()
entry.submit()
print("INFO  shift entry " + entry.name + ": 4 h on " + CARD + ", 8 good + 2 rejected, 3 coolant (30)")
out = run_report({"job_order": wo.name})
row = (out.get("result") or [{}])[0]
print("INFO  a piece - estimate " + str(row.get("est_total")) + ", actual " + str(row.get("act_total")) + " (material " + str(row.get("act_material")) + ", machining " + str(row.get("act_machining")) + ", overhead " + str(row.get("act_overhead")) + "), variance " + str(row.get("variance")) + " = " + str(row.get("variance_percent")) + "%")
check(row.get("pieces") == 8 and near(row.get("actual_total"), 2783), "4. actual cost 2,783: BOM material 10 x 10 pieces worked + 4 h x 600 + coolant 30 + 10% overhead, over 8 good pieces")
check(near(row.get("act_material"), 12.5) and near(row.get("act_machining"), 303.75) and abs(flt(row.get("act_overhead")) - 31.625) < 0.01, "4. a piece: material 12.50, machining 303.75 (machine + coolant), overhead 31.62")
check(abs(flt(row.get("act_total")) - 347.875) < 0.01 and row.get("variance_percent") == 10.2, "4. actual 347.88 a piece against 315.70: +10.2%")
check(row.get("colour") == "red", "4. above the 10% warning: shown red")
check("material from the BOM" in (row.get("notes") or "") and "none booked yet" in (row.get("notes") or ""), "4. the notes say the material is from the BOM and nothing is booked yet -> " + str(row.get("notes")))
check("1 of 1 row(s) over" in str(out.get("message")), "4. the line above the report counts it -> " + str(out.get("message"))[:160])

# ---------------- 5. by item, and the warning setting ----------------
out = run_report({"item_code": FG, "group_by": "Item"})
items = out.get("result") or []
check(len(items) == 1 and items[0].get("job_orders") == 1 and items[0].get("item_code") == FG and "job_order" not in [c.get("fieldname") for c in out.get("columns") or []],
      "5. 'Show: Item' gives one row for " + FG + " (1 Job Order), without the Job Order column")
params = frappe.get_doc(PARAMS)
params.set(WARNING, 15)
params.save()
out = run_report({"job_order": wo.name})
check((out.get("result") or [{}])[0].get("colour") == "green", "5. with Variance Warning % = 15 the same Job Order is green")


def bad_warning():
    p = frappe.get_doc(PARAMS)
    p.set(WARNING, 150)
    p.save()


refused("5. a Variance Warning % above 100 is refused", bad_warning, "Costing: Variance Warning")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
