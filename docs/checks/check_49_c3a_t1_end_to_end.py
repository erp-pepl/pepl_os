# PEPL OS v0.49.0 - Check 49 rev 2: C3a-T1 end to end - one order through the whole Production chain:
# Sales Order (Railways, LD) -> draft Job Order -> submitted Job Order and Job Card -> the operator's shift entered
# and submitted on the kiosk -> Job Card time log, Daily OEE, Machine Week, rejected pieces in the Scrap Register ->
# Job Order panel, Estimate vs Actual Cost, LD Exposure, Skill Matrix, foreman board, Command Centre, exception-only
# stand-up -> Cycle 3a health check.
# Rev 2: the Job Card's time logs are read from the Job Card itself (a child table read on its own returned
# nothing in the System Console).
# Runs on 0.49.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the
# end (except the kiosk's short-lived session entry in the cache, which expires by itself).
VERSION = "0.49.0"
PARAMS = "PEPL System Parameters"
SPR = "PEPL Shift Production Entry"
K = "pepl_os.pepl_production.kiosk."
P = "pepl_os.pepl_production."
LEVEL3 = "3 - Runs independently"
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


def near(a, b, tolerance=0.011):
    return a is not None and abs(frappe.utils.flt(a) - frappe.utils.flt(b)) <= tolerance


def report(name, filters):
    return frappe.call("frappe.desk.query_report.run", report_name=name, filters=filters)


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
yesterday = frappe.utils.add_days(today, -1)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def day(offset):
    return frappe.utils.add_days(today, offset)


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")

# ---------------- 2. rules and masters for this run ----------------
GROUP = "CHK49 MILL " + RUN
MILL = "CHK49 MILL-01 " + RUN
DAY = "CHK49 Day " + RUN
OP = "CHK49-OP-" + RUN
NO_LOAD = "CHK49 No Load " + RUN
frappe.get_doc({"doctype": "Workstation Type", "workstation_type": GROUP}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL, "workstation_type": GROUP}).insert()
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
p = frappe.get_doc(PARAMS)
p.append("custom_machine_hour_rates", {"machine_group": GROUP, "rate_per_hour": 600})
p.custom_overhead_percent = 10
p.custom_cost_variance_warning_percent = 10
p.custom_job_order_from_sales_order = 1
p.enable_operational_todos = 1
p.custom_production_notification_owner = frappe.session.user
if not p.get("custom_stores_notification_owner"):
    p.custom_stores_notification_owner = frappe.session.user
p.custom_ld_default_sectors = "Railways\nDefence"
p.custom_ld_default_rate_percent = 0.5
p.custom_ld_default_period = "Week"
p.custom_ld_default_max_percent = 10
p.custom_ld_look_ahead_days = 7
p.custom_rejections_to_scrap = 1
p.custom_standup_exception_only = 1
p.custom_oee_target_percent = 85
p.skill_check_mode = "Advisory"
p.custom_skill_min_level = LEVEL3
p.custom_spr_tool_photo_required = 0
p.custom_spr_max_unaccounted_minutes = 15
p.custom_shift_eligibility_mode = "Warn"
p.save()
s = frappe.get_doc("Manufacturing Settings")
s.disable_capacity_planning = 1
s.overproduction_percentage_for_work_order = 0
s.save()
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Ramesh " + RUN, "pin": pin, "default_shift": DAY,
                "eligible_shifts": [{"shift": DAY}], "skills": [{"workstation_type": GROUP, "level": LEVEL3}]}).insert()
# India Compliance (bench and demo) checks HSN codes on sales items
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    hsn = codes[0] if codes else ""
SCRAP = frappe.get_doc({"doctype": "Item", "item_code": "CHK49-SCRAP-" + RUN, "item_name": "CHK49 Brass Turnings " + RUN, "item_group": "Brass Scrap", "stock_uom": "Kg",
                        "is_stock_item": 1, "is_sales_item": 0, "is_purchase_item": 0}).insert().name
frappe.get_doc({"doctype": "PEPL Scrap Rate", "scrap_item": SCRAP, "rate": 40, "effective_from": day(-60)}).insert()
fg_values = {"doctype": "Item", "item_code": "CHK49-SHAFT-" + RUN, "item_name": "CHK49 Shaft " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1,
             "is_sales_item": 1 if hsn else 0, "weight_per_unit": 0.25, "weight_uom": "Kg", "custom_rejection_scrap_item": SCRAP}
if hsn:
    fg_values["gst_hsn_code"] = hsn
SHAFT = frappe.get_doc(fg_values).insert().name
BAR = frappe.get_doc({"doctype": "Item", "item_code": "CHK49-BAR-" + RUN, "item_name": "CHK49 Bar " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos",
                      "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
TURNING = "CHK49 Turning " + RUN
frappe.get_doc({"doctype": "Operation", "name": TURNING, "workstation": MILL}).insert()
bom = frappe.get_doc({"doctype": "BOM", "item": SHAFT, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
                      "currency": frappe.db.get_value("Company", company, "default_currency"), "items": [{"item_code": BAR, "qty": 1, "rate": 10}],
                      "operations": [{"operation": TURNING, "workstation": MILL, "time_in_mins": 3}]}).insert()
bom.submit()
rm_group = (frappe.get_all("PEPL RM Group", pluck="name", limit=1) or [None])[0]
if not rm_group:
    rm_group = frappe.get_doc({"doctype": "PEPL RM Group", "group_name": "CHK49 Rod " + RUN, "material_base": "Brass", "default_uom": "Kg", "is_active": 1, "auto_sync_to_item_group": 0}).insert().name
product = frappe.get_doc({"doctype": "PEPL Product Master", "product_name": "CHK49 Product " + RUN, "product_type": "Single Component", "status": "Active", "linked_item": SHAFT}).insert().name
cst = frappe.get_doc({"doctype": "PEPL CST Cost Sheet", "cst_title": "CHK49 " + RUN, "linked_product": product, "linked_item": SHAFT, "status": "Approved", "costing_date": day(-40),
                      "overhead_percent": 10, "components": [{"manufactured_or_bought_out": "Manufactured", "rm_group": rm_group, "quantity_per_assembly": 1,
                                                              "raw_material_cost": 12, "machining_cost": 50, "surface_treatment_cost": 5}]}).insert()
groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
customer = frappe.get_doc({"doctype": "Customer", "customer_name": "CHK49 Railway " + RUN, "customer_type": "Company",
                           "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert().name
print("INFO  " + MILL + " (" + GROUP + ", 600 / h); operator " + OP + " level 3; " + SHAFT + " 0.25 kg, BOM 1 bar x 10, 3 min on " + MILL + "; CST " + cst.name + " = "
      + str(cst.total_components_cost + cst.overhead_amount) + " a piece")

# ---------------- 3. the order and its Job Order ----------------
so = frappe.get_doc({"doctype": "Sales Order", "customer": customer, "company": company, "custom_sector": "Railways", "transaction_date": day(-30), "delivery_date": day(-2),
                     "items": [{"item_code": SHAFT, "qty": 40, "rate": 100, "warehouse": wh("FG Stores"), "delivery_date": day(-2)}]}).insert()
so.submit()
check(so.custom_ld_applicable == 1, "3. the Railways order " + so.name + " carries the standard LD clause (0.5 % a week, cap 10 %)")
drafts = frappe.get_all("Work Order", filters={"sales_order": so.name, "docstatus": 0}, pluck="name")
check(len(drafts) == 1, "3. submitting it drafted Job Order " + (drafts[0] if drafts else "none") + " for the shaft")
wo = frappe.get_doc("Work Order", drafts[0])
wo.submit()
cards = frappe.get_all("Job Card", filters={"work_order": wo.name}, fields=["name", "workstation", "for_quantity"])
CARD = cards[0].name if cards else None
check(len(cards) == 1 and cards[0].workstation == MILL and cards[0].for_quantity == 40, "3. Production submits it: Job Card " + str(CARD) + " for 40 on " + MILL)

# ---------------- 4. the operator's shift, on the kiosk ----------------
out = frappe.call(K + "sign_in", machine=MILL, shift=DAY, posting_date=yesterday, employee_code=OP, pin=pin)
TOKEN = out.get("token")
check(bool(TOKEN) and CARD in [c.get("name") for c in out.get("job_cards")], "4. " + OP + " signs in on the kiosk at " + MILL + " (yesterday's " + DAY + ") and sees " + str(CARD))
out = frappe.call(K + "save_entry", token=TOKEN, production=[{"job_card": CARD, "from_time": "08:00", "to_time": "12:00", "good_qty": 36, "rejected_qty": 4, "rejection_reason": "Undersize"}],
                  downtime=[{"downtime_category": NO_LOAD, "from_time": "12:00", "to_time": "16:30"}])
ENTRY = out.get("entry")
check(bool(ENTRY) and out.get("production")[0].get("from_time") == "08:00", "4. saved as " + str(ENTRY) + ": 08:00-12:00, 36 good, 4 rejected; stop 12:00-16:30")
out = frappe.call(K + "submit_entry", token=TOKEN)
frappe.call(K + "sign_out", token=TOKEN)
check(frappe.db.get_value(SPR, ENTRY, "docstatus") == 1, "4. submitted from the kiosk")

# ---------------- 5. what the submission set going ----------------
logs = frappe.get_doc("Job Card", CARD).time_logs
print("INFO  Job Card " + str(CARD) + " time logs: " + ", ".join(str(l.from_time) + " - " + str(l.to_time) + " done " + str(l.completed_qty) for l in logs))
check(len(logs) == 1 and logs[0].completed_qty == 36 and logs[0].get("custom_pepl_spr") == ENTRY, "5. Job Card " + str(CARD) + " has the time log from " + str(ENTRY) + ": 36 done")
daily = frappe.get_all("PEPL OEE Daily", filters={"workstation": MILL, "oee_date": yesterday}, fields=["name", "oee", "good_qty", "rejected_qty"])
check(len(daily) == 1 and daily[0].good_qty == 36 and daily[0].rejected_qty == 4, "5. Daily OEE " + (daily[0].name if daily else "missing") + " built: OEE " + str(daily[0].oee if daily else "-") + " %")
week = frappe.get_all("PEPL Machine Week", filters={"workstation": MILL}, fields=["name", "run_minutes", "machine_cost"])
check(len(week) == 1 and week[0].run_minutes == 240 and near(week[0].machine_cost, 2400), "5. Machine Week " + (week[0].name if week else "missing") + ": 240 run minutes, machine cost 2,400")
ws = frappe.get_all("PEPL Scrap Weighment", filters={"shift_production_entry": ENTRY, "docstatus": 1}, fields=["name", "net_kg", "amount"])
check(len(ws) == 1 and near(ws[0].net_kg, 1) and near(ws[0].amount, 40), "5. the 4 rejected shafts went to the Scrap Register: " + (ws[0].name if ws else "nothing") + ", 1 kg = 40")
panel = frappe.call(P + "job_order_panel.get_job_order_panel", work_order=wo.name).get("rows") or []
check(any("shop floor reported 36 good, 4 rejected" in r.get("text") for r in panel), "5. the Job Order panel: " + (panel[0].get("text") if panel else "-"))

# ---------------- 6. the reports ----------------
out = report("PEPL Estimate vs Actual Cost", {"job_order": wo.name})
row = (out.get("result") or [{}])[0]
print("INFO  cost a piece: estimate " + str(row.get("est_total")) + ", actual " + str(row.get("act_total")) + " (" + str(row.get("variance_percent")) + " %)")
check(row.get("cst") == cst.name and near(row.get("actual_total"), 3080) and near(row.get("act_total"), 85.56),
      "6. Estimate vs Actual: actual 3,080 (BOM 400 + machine 2,400 + 10 % overhead) over 36 good = 85.56 a piece against CST " + str(row.get("est_total")))
check(row.get("colour") == "red", "6. ... 85.56 is above 73.70 (+16 %): red")
out = report("PEPL LD Exposure", {"sales_order": so.name, "as_on": today})
row = (out.get("result") or [{}])[0]
check(near(row.get("ld_now"), 20) and row.get("colour") == "red", "6. LD Exposure: 2 days late = 1 week: 4,000 x 0.5 % = " + str(row.get("ld_now")) + " so far, red")
out = report("PEPL Skill Matrix", {"status": "Active", "workstation_type": GROUP})
mine = [r for r in out.get("result") or [] if r.get("operator") == OP]
key = [c.get("fieldname") for c in out.get("columns") or [] if c.get("label") == GROUP]
check(bool(mine) and bool(key) and mine[0].get(key[0]) == "3", "6. Skill Matrix: " + OP + " level 3 on " + GROUP)
board = frappe.call(K + "foreman_board", posting_date=yesterday, shift=DAY)
rows = [r for r in board.get("rows") or [] if r.get("machine") == MILL]
check(bool(rows) and rows[0].get("state") == "Submitted" and rows[0].get("good") == "36", "6. foreman board: " + MILL + " Submitted, 36 good")
card = frappe.call(P + "command_centre.rejection_percent")
check(card is not None and "value" in card, "6. Command Centre card 'Rejection % (7 days)' answers: " + str(card.get("value") if card else "-"))
name = frappe.call(P + "standup.build_standup_now", day=yesterday).get("name")
html = frappe.db.get_value("PEPL Daily Standup", name, "summary") or ""
check("need attention" in html and MILL in html and so.name in html and wo.name in html,
      "6. stand-up " + name + ": " + MILL + " below target, " + wo.name + " overdue, " + so.name + " running LD")

# ---------------- 7. the Cycle 3a health check ----------------
health = frappe.call(P + "health_check.run_health_check", since=day(-60))
counts = health.get("findings") or {}
print("INFO  health check findings: " + ", ".join(k + " " + str(counts[k]) for k in sorted(counts)))
check(len(counts) == 8, "7. the Cycle 3a health check runs: 8 sheets")
check(not [r for r in (health.get("rows") or {}).get("5 Costing and scrap", []) if r.get("record") == SHAFT], "7. the shaft has its CST, weight and scrap item: no costing finding for it")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
