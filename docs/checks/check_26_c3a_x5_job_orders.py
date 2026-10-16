# PEPL OS v0.26.0 - Check 26: C3a-X5 a submitted Sales Order drafts its Job Orders -
# one per manufactured line with a BOM (with the BOM's operations), no-BOM lines flagged, switch, cancel.
# Runs on 0.26.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters and Manufacturing Settings changes this check makes, is undone at the end.
VERSION = "0.26.0"
PARAMS = "PEPL System Parameters"
ENABLE = "custom_job_order_from_sales_order"
AUTO = "custom_auto_from_sales_order"
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
due = frappe.utils.add_days(today, 12)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
print("INFO  company " + company)


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.get_meta(PARAMS).get_field(ENABLE)), "1. System Parameters has Production > Draft Job Orders from Sales Orders")
check(bool(frappe.get_meta("Work Order").get_field(AUTO)), "1. the Job Order (Work Order) shows 'Drafted from the Sales Order'")
site_switch = frappe.db.get_single_value(PARAMS, ENABLE)
print("INFO  this site: Draft Job Orders from Sales Orders = " + str(site_switch))
check(bool(wh("FG Stores")) and bool(wh("WIP Main Workshop")), "1. FG Stores and WIP Main Workshop exist for " + company)


def set_params(switch):
    params = frappe.get_doc(PARAMS)
    params.set(ENABLE, switch)
    params.enable_operational_todos = 1
    params.custom_production_notification_owner = frappe.session.user
    params.save()


set_params(1)
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.save()

# ---------------- 2. masters for this run ----------------
# India Compliance (bench and demo) refuses to submit a Sales Order whose lines have no valid HSN/SAC code, so the
# test items get an 8-digit code from its HSN master (84831010 family = shafts) and are sales items. Without India
# Compliance they get no code and are not sales items.
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    codes = codes or [c for c in frappe.get_all("GST HSN Code", pluck="name", limit=200) if len(c) == 8]
    hsn = codes[0] if codes else ""
print("INFO  HSN code for the test items: " + (hsn or "(none - India Compliance not installed)"))


def item(code, group, rate=0):
    values = {"doctype": "Item", "item_code": code + "-" + RUN, "item_name": code + " " + RUN, "item_group": group, "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 1 if hsn else 0}
    if hsn:
        values["gst_hsn_code"] = hsn
    if rate:
        values["valuation_rate"] = rate
    return frappe.get_doc(values).insert().name


SHAFT = item("CHK26-FG-SHAFT", "Finished Goods")
PLATE = item("CHK26-FG-PLATE", "Finished Goods")
BEARING = item("CHK26-BO-BEARING", "Bought-Out Components", 50)
ROD = item("CHK26-RM-ROD", "Raw Material", 10)
MILL = "CHK26 MILL-01 " + RUN
MILLING = "CHK26 Milling " + RUN
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
frappe.get_doc({"doctype": "Operation", "name": MILLING, "workstation": MILL}).insert()
bom = frappe.get_doc({
    "doctype": "BOM", "item": SHAFT, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
    "currency": frappe.db.get_value("Company", company, "default_currency"),
    "items": [{"item_code": ROD, "qty": 1, "rate": 10}],
    "operations": [{"operation": MILLING, "workstation": MILL, "time_in_mins": 12}],
}).insert()
bom.submit()
groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
customer = frappe.get_doc({
    "doctype": "Customer", "customer_name": "CHK26 Customer " + RUN, "customer_type": "Company",
    "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None,
}).insert().name
print("INFO  items " + SHAFT + " (BOM " + bom.name + ", milling on " + MILL + "), " + PLATE + " (no BOM), " + BEARING + " (bought-out)")


def sales_order(lines):
    return frappe.get_doc({
        "doctype": "Sales Order", "customer": customer, "company": company, "transaction_date": today, "delivery_date": due,
        "custom_sector": "Private",
        "items": [{"item_code": code, "qty": qty, "rate": 100, "warehouse": wh("FG Stores"), "delivery_date": due} for code, qty in lines],
    }).insert()


def job_orders(so_name):
    return frappe.get_all(
        "Work Order", filters={"sales_order": so_name, "docstatus": 0},
        fields=["name", "production_item", "qty", "bom_no", "sales_order_item", "fg_warehouse", "wip_warehouse", "expected_delivery_date", AUTO],
    )


def todos(so_name, rule):
    return frappe.get_all(
        "ToDo", filters={"reference_type": "Sales Order", "reference_name": so_name, "status": "Open", "description": ["like", "%" + rule + "%"]},
        fields=["description", "allocated_to"],
    )


# ---------------- 3. submit: one draft Job Order per manufactured line with a BOM ----------------
so = sales_order([(SHAFT, 8), (PLATE, 3), (BEARING, 4)])
so.submit()
check(so.docstatus == 1, "3. the Sales Order with a shaft (BOM), a plate (no BOM) and a bearing (bought-out) is submitted")
rows = job_orders(so.name)
print("INFO  Job Orders: " + ", ".join(r.name + " " + r.production_item + " x " + str(r.qty) for r in rows))
check(len(rows) == 1 and rows[0].production_item == SHAFT, "3. exactly one draft Job Order, for the shaft (none for the plate or the bearing)")
if rows:
    jo = rows[0]
    line = [r for r in so.items if r.item_code == SHAFT][0]
    check(jo.qty == 8, "3. the Job Order is for the 8 ordered")
    check(jo.bom_no == bom.name, "3. it uses the shaft's default BOM " + bom.name)
    check(jo.sales_order_item == line.name, "3. it is linked to the Sales Order line")
    check(jo.fg_warehouse == wh("FG Stores") and jo.wip_warehouse == wh("WIP Main Workshop"), "3. it finishes into FG Stores through WIP Main Workshop")
    check(str(jo.expected_delivery_date) == str(due), "3. it is due on the line's delivery date " + str(due))
    check(jo.get(AUTO) == 1, "3. it is marked 'Drafted from the Sales Order'")
    ops = frappe.get_all("Work Order Operation", filters={"parent": jo.name}, fields=["operation", "workstation", "time_in_mins"])
    check(len(ops) == 1 and ops[0].operation == MILLING and ops[0].workstation == MILL, "3. it carries the BOM's milling operation on " + MILL)
    check(bool(ops) and ops[0].time_in_mins == 96, "3. operation time is 8 x 12 = 96 minutes (has " + str(ops[0].time_in_mins if ops else None) + ")")
flags = todos(so.name, "PRD-NO-BOM")
check(len(flags) == 1 and PLATE in flags[0].description, "3. Production has a ToDo PRD-NO-BOM naming the plate")
check(bool(flags) and flags[0].allocated_to == frappe.session.user, "3. the ToDo is for the Production notification owner")

# ---------------- 4. Production submits the Job Order: Job Cards are made ----------------
if rows:
    wo = frappe.get_doc("Work Order", rows[0].name)
    wo.submit()
    cards = frappe.get_all("Job Card", filters={"work_order": wo.name}, fields=["name", "workstation", "for_quantity"])
    print("INFO  Job Order " + wo.name + " submitted -> Job Card(s) " + ", ".join(c.name for c in cards))
    check(len(cards) == 1 and cards[0].workstation == MILL and cards[0].for_quantity == 8, "4. submitting it makes the Job Card for 8 on " + MILL)

# ---------------- 5. cancelling a Sales Order deletes its draft Job Orders ----------------
so2 = sales_order([(SHAFT, 2)])
so2.submit()
drafts = [r.name for r in job_orders(so2.name)]
check(len(drafts) == 1, "5. a second order drafts its own Job Order " + ", ".join(drafts))
so2.reload()
so2.cancel()
check(so2.docstatus == 2, "5. the second order is cancelled")
check(not any(frappe.db.exists("Work Order", n) for n in drafts), "5. its draft Job Order is deleted")
check(frappe.db.exists("Work Order", rows[0].name) if rows else False, "5. the first order's Job Order is untouched")

# ---------------- 6. switched off in System Parameters ----------------
set_params(0)
so3 = sales_order([(SHAFT, 5)])
so3.submit()
check(so3.docstatus == 1 and not job_orders(so3.name), "6. with the switch off, a submitted order drafts no Job Order")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (Draft Job Orders from Sales Orders is back to " + str(site_switch) + ").")
