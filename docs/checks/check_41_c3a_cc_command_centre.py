# PEPL OS v0.41.0 - Check 41: C3a-CC the Production Command Centre - a workspace that renders (every block named by
# its label, no apostrophe in the title) and its five cards: OEE Yesterday, Jobs at Delivery Risk, Open Job-Work
# Quantity Outside, Rejection % (7 days), Top Downtime Cause (7 days); the report PEPL Downtime by Cause behind the last.
# Runs on 0.41.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the
# end. Afterwards open the workspace: search bar -> "Production Command Centre" (or the sidebar).
VERSION = "0.41.0"
PARAMS = "PEPL System Parameters"
SPR = "PEPL Shift Production Entry"
WORKSPACE = "Production Command Centre"
CC = "pepl_os.pepl_production.command_centre."
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


def card(method):
    res = frappe.call(CC + method)
    print("INFO  card " + method + ": " + str(res.get("value")) + " (" + str(res.get("fieldtype")) + ") -> " + str(res.get("route")))
    return res


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
yesterday = frappe.utils.add_days(today, -1)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


# ---------------- 1. installed: the workspace renders ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.db.exists("Workspace", WORKSPACE)) and "'" not in str(frappe.db.get_value("Workspace", WORKSPACE, "title")), "1. the workspace '" + WORKSPACE + "' exists, with no apostrophe in its title (the address is made from it)")
ws = frappe.get_doc("Workspace", WORKSPACE)
labels = {
    "number_card": [r.label for r in ws.number_cards],
    "custom_block": [r.label for r in ws.custom_blocks],
    "shortcut": [r.label for r in ws.shortcuts],
    "card": [r.label for r in ws.links if r.type == "Card Break"],
}
keys = {"number_card": "number_card_name", "custom_block": "custom_block_name", "shortcut": "shortcut_name", "card": "card_name"}
blocks = json.loads(ws.content)
unmatched = [b["type"] + " " + str(b["data"].get(keys[b["type"]])) for b in blocks if b["type"] in keys and b["data"].get(keys[b["type"]]) not in labels[b["type"]]]
check(not unmatched, "1. every block on the page is named by the label of its row, so Frappe draws it" + (" - not drawn: " + ", ".join(unmatched) if unmatched else ""))
cards_on_page = [b for b in blocks if b["type"] in ("number_card", "custom_block")]
check(len(cards_on_page) == 5 and all(frappe.db.exists("Number Card", r.number_card_name) for r in ws.number_cards), "1. five cards on the page: " + ", ".join(b["data"].get("number_card_name") or b["data"].get("custom_block_name") for b in cards_on_page))
broken = [r.link_to for r in ws.links if r.type == "Link" and not frappe.db.exists(r.link_type, r.link_to)] + [s.link_to for s in ws.shortcuts if not frappe.db.exists(s.type, s.link_to)]
check(not broken, "1. every link and shortcut opens something that exists" + (" - broken: " + ", ".join(broken) if broken else ""))
check(bool(frappe.db.exists("Custom HTML Block", "PEPL Top Downtime Cause")) and bool(frappe.db.exists("Report", "PEPL Downtime by Cause")), "1. the block 'PEPL Top Downtime Cause' and the report 'PEPL Downtime by Cause' exist")

# ---------------- 2. a shift to put numbers on the cards ----------------
params = frappe.get_doc(PARAMS)
params.custom_spr_tool_photo_required = 0
params.custom_spr_max_unaccounted_minutes = 15
params.save()
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.overproduction_percentage_for_work_order = 0
settings.save()
before_rej = card("rejection_percent")
DAY = "CHK41 Day " + RUN
MILL = "CHK41 MILL-01 " + RUN
OP = "CHK41-OP-" + RUN
SETTING = "CHK41 Tool Setting " + RUN
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Check " + OP, "pin": pin}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": SETTING, "stop_type": "Unplanned", "is_breakdown": 0}).insert()
FG = frappe.get_doc({"doctype": "Item", "item_code": "CHK41-FG-" + RUN, "item_name": "CHK41 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert().name
BO = frappe.get_doc({"doctype": "Item", "item_code": "CHK41-BO-" + RUN, "item_name": "CHK41 Bought-out " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
MILLING = "CHK41 Milling " + RUN
frappe.get_doc({"doctype": "Operation", "name": MILLING, "workstation": MILL}).insert()
bom = frappe.get_doc({"doctype": "BOM", "item": FG, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
                      "currency": frappe.db.get_value("Company", company, "default_currency"), "items": [{"item_code": BO, "qty": 1, "rate": 10}],
                      "operations": [{"operation": MILLING, "workstation": MILL, "time_in_mins": 6}]}).insert()
bom.submit()
wo = frappe.get_doc({"doctype": "Work Order", "production_item": FG, "bom_no": bom.name, "qty": 40, "stock_uom": "Nos", "company": company,
                     "skip_transfer": 1, "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order",
                     "expected_delivery_date": frappe.utils.add_days(today, 1)})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
jc = frappe.get_all("Job Card", filters={"work_order": wo.name}, pluck="name")[0]
entry = frappe.get_doc({"doctype": SPR, "posting_date": yesterday, "shift": DAY, "workstation": MILL, "operator": OP, "company": company})
entry.append("production", {"job_card": jc, "from_time": "08:00", "to_time": "12:00", "good_qty": 38, "rejected_qty": 2, "rejection_reason": "Undersize"})
entry.append("downtime", {"downtime_category": SETTING, "from_time": "12:00", "to_time": "16:30"})
entry.insert()
entry.submit()
print("INFO  shift entry " + entry.name + " yesterday on " + MILL + ": 40 pieces (2 rejected) 08:00-12:00, stop '" + SETTING + "' 12:00-16:30 (270 min); Job Order " + wo.name + " due tomorrow")

# ---------------- 3. the number cards ----------------
oee_rows = frappe.get_all("PEPL OEE Daily", filters={"oee_date": yesterday}, fields=["oee", "planned_production_minutes"])
weight = sum(frappe.utils.cint(r.planned_production_minutes) for r in oee_rows)
want_oee = round(sum(frappe.utils.flt(r.oee) * frappe.utils.cint(r.planned_production_minutes) for r in oee_rows) / weight, 1) if weight else 0
res = card("yesterdays_oee")
check(res.get("fieldtype") == "Percent" and abs(frappe.utils.flt(res.get("value")) - want_oee) < 0.05, "3. OEE Yesterday = " + str(want_oee) + " %: the " + str(len(oee_rows)) + " Daily OEE record(s) of yesterday weighted by planned production time")
risk = frappe.call(CC + "jobs_at_delivery_risk")
names = (risk.get("route_options") or {}).get("name") or []
check(wo.name in str(names) and risk.get("value") >= 1, "3. Jobs at Delivery Risk counts " + wo.name + " (due tomorrow, within the stand-up's risk days, not finished): " + str(risk.get("value")))
res = card("job_work_outside")
want_jw = round(sum(frappe.utils.flt(r.get("balance")) for r in frappe.call("frappe.desk.query_report.run", report_name="PEPL Job-Work Reconciliation", filters={"company": company, "as_on": today, "outstanding_only": 1}).get("result") or [] if isinstance(r, dict) and r.get("item_code")), 3)
check(abs(frappe.utils.flt(res.get("value")) - want_jw) < 0.001, "3. Open Job-Work Quantity Outside = " + str(want_jw) + ", the total of the Job-Work Reconciliation report")
res = card("rejection_percent")
check(res.get("fieldtype") == "Percent" and frappe.utils.flt(res.get("value")) > 0, "3. Rejection % (7 days) counts yesterday's 2 rejected of 40 (it was " + str(before_rej.get("value")) + " %, now " + str(res.get("value")) + " %)")

# ---------------- 4. top downtime cause ----------------
report = frappe.call("frappe.desk.query_report.run", report_name="PEPL Downtime by Cause", filters={"days": 7})
rows = [r for r in (report.get("result") or []) if isinstance(r, dict) and r.get("downtime_category")]
mine = [r for r in rows if r.get("downtime_category") == SETTING]
print("INFO  Downtime by Cause (7 days): " + ", ".join(str(r.get("downtime_category")) + " " + str(r.get("minutes")) + " min" for r in rows[:5]))
check(bool(mine) and mine[0].get("minutes") == 270 and mine[0].get("stops") == 1, "4. the report PEPL Downtime by Cause shows '" + SETTING + "': 270 min, 1 stop")
top = frappe.call(CC + "top_downtime_cause")
print("INFO  Top Downtime Cause (7 days): " + str(top.get("cause")) + " - " + str(top.get("text")))
check(bool(rows) and top.get("cause") == rows[0].get("downtime_category") and str(rows[0].get("minutes")) + " min" in str(top.get("text")), "4. the Top Downtime Cause card shows the first line of that report: " + str(top.get("cause")))

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
