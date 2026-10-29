# PEPL OS v0.38.0 - Check 38: C3a-P4 the customer-supplied material (CSM) panel on the Job Order - what this Job
# Order still needs of the customer's material, what the whole Sales Order still needs, against what the order holds
# in the CSM stores; green / orange / red, short by, enough for n pieces.
# Runs on 0.38.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters change it makes, is undone at the end. After the check, open a Job Order made from customer
# material to see the panel (draft or submitted).
VERSION = "0.38.0"
PARAMS = "PEPL System Parameters"
PANEL = "pepl_os.pepl_production.csm_panel.get_job_order_csm_panel"
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
due = frappe.utils.add_days(today, 15)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
print("INFO  company " + company)


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def texts(rows):
    return " | ".join(r["text"] for r in rows)


def panel(work_order):
    rows = frappe.call(PANEL, work_order=work_order)["rows"]
    print("INFO  CSM panel of " + work_order + ": " + texts(rows) + " [" + ", ".join(r["colour"] for r in rows) + "]")
    return rows


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
site_tol = frappe.db.get_single_value(PARAMS, "csm_reconciliation_tolerance_kg")
print("INFO  this site: CSM Reconciliation Tolerance = " + str(site_tol) + " kg")
params = frappe.get_doc(PARAMS)
params.csm_reconciliation_tolerance_kg = 0.5
params.custom_job_order_from_sales_order = 1
params.save()

# ---------------- 2. a shaft made from the customer's steel ----------------
# The finished shaft is a sales item with an 8-digit HSN code (India Compliance checks the Sales Order); the
# customer's steel is weighed in Kg and heat-tracked, so each receipt names a heat number.
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    hsn = codes[0] if codes else ""
fg_values = {"doctype": "Item", "item_code": "CHK38-SHAFT-" + RUN, "item_name": "CHK38 Shaft " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 1 if hsn else 0}
if hsn:
    fg_values["gst_hsn_code"] = hsn
SHAFT = frappe.get_doc(fg_values).insert().name
STEEL = frappe.get_doc({"doctype": "Item", "item_code": "CHK38-CSM-STEEL-" + RUN, "item_name": "CHK38 Customer Steel " + RUN, "item_group": "Customer-Supplied Material", "stock_uom": "Kg", "is_stock_item": 1, "is_sales_item": 0}).insert().name
BOUGHT = frappe.get_doc({"doctype": "Item", "item_code": "CHK38-BO-" + RUN, "item_name": "CHK38 Bought-out " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
PLAIN = frappe.get_doc({"doctype": "Item", "item_code": "CHK38-PLAIN-" + RUN, "item_name": "CHK38 Plain " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert().name
currency = frappe.db.get_value("Company", company, "default_currency")
for fg, material, qty in ((SHAFT, STEEL, 2), (PLAIN, BOUGHT, 1)):
    bom = frappe.get_doc({"doctype": "BOM", "item": fg, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "currency": currency,
                          "items": [{"item_code": material, "qty": qty, "rate": 0 if material == STEEL else 10}]}).insert()
    bom.submit()
groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
customer = frappe.get_doc({"doctype": "Customer", "customer_name": "CHK38 Customer " + RUN, "customer_type": "Company",
                           "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert().name


def order(quantities):
    so = frappe.get_doc({
        "doctype": "Sales Order", "customer": customer, "company": company, "transaction_date": today, "delivery_date": due, "custom_sector": "Private",
        "items": [{"item_code": SHAFT, "qty": q, "rate": 100, "warehouse": wh("FG Stores"), "delivery_date": due} for q in quantities],
    }).insert()
    so.submit()
    drafts = frappe.get_all("Work Order", filters={"sales_order": so.name, "docstatus": 0}, fields=["name", "qty"], order_by="creation")
    return {"so": so.name, "drafts": drafts}


heats = [0]


def receive(sales_order, kg):
    heats[0] = heats[0] + 1
    heat = "CHK38-H" + str(heats[0]) + "-" + RUN
    doc = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company, "custom_sales_order": sales_order,
                          "items": [{"item_code": STEEL, "qty": kg, "t_warehouse": wh("CSM Stores"), "custom_heat_number": heat}]}).insert()
    doc.submit()
    print("INFO  received " + str(kg) + " kg of the customer's steel against " + sales_order + " (heat " + heat + ")")


placed = order([10])
SO1 = placed["so"]
drafts = placed["drafts"]
check(len(drafts) == 1 and drafts[0].qty == 10, "2. Sales Order " + SO1 + " for 10 shafts (2 kg of the customer's steel each) drafted its Job Order " + (drafts[0].name if drafts else "-"))
WO1 = drafts[0].name if drafts else ""

# ---------------- 3. short, then enough ----------------
rows = panel(WO1)
check(rows[0]["colour"] == "red" and "does not hold enough" in rows[0]["text"], "3. nothing received yet: red, 'does not hold enough customer material to finish this Job Order'")
check("2 Kg a piece x 10 still to make = 20 Kg; the order holds 0 Kg (enough for 0 pieces) - short by 20 Kg" in texts(rows), "3. the steel line: 2 Kg a piece x 10 = 20 Kg, holds 0 Kg, short by 20 Kg")
receive(SO1, 15)
rows = panel(WO1)
check("holds 15 Kg (enough for 7 pieces) - short by 5 Kg" in texts(rows) and rows[1]["colour"] == "red", "3. 15 kg received: enough for 7 pieces, short by 5 Kg, red")
receive(SO1, 4.7)
rows = panel(WO1)
check(rows[0]["colour"] == "green", "3. 19.7 kg received: within the 0.5 kg CSM tolerance of the 20 kg needed - green")
receive(SO1, 5.3)
rows = panel(WO1)
check(rows[0]["colour"] == "green" and "holds enough" in rows[0]["text"] and "holds 25 Kg (enough for 12 pieces)" in texts(rows), "3. 25 kg received: green, 'holds 25 Kg (enough for 12 pieces)'")

# ---------------- 4. enough for this Job Order, not for the whole order ----------------
placed = order([10, 5])
SO2 = placed["so"]
drafts2 = placed["drafts"]
receive(SO2, 25)
first = [d.name for d in drafts2 if d.qty == 10]
rows = panel(first[0]) if first else []
check(bool(first) and rows[0]["colour"] == "orange" and "the whole order still needs 30 Kg" in texts(rows), "4. order of 10 + 5 shafts with 25 kg: the 10-shaft Job Order is covered (20 kg), the whole order is not (30 kg) - orange")

# ---------------- 5. Job Orders that need no panel, or have no Sales Order ----------------


def job_order(item):
    wo = frappe.get_doc({"doctype": "Work Order", "production_item": item, "bom_no": frappe.db.get_value("BOM", {"item": item, "is_default": 1, "docstatus": 1}),
                         "qty": 5, "stock_uom": "Nos", "company": company, "skip_transfer": 1, "fg_warehouse": wh("FG Stores"),
                         "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order"})
    wo.get_items_and_operations_from_bom()
    wo.insert()
    return wo.name


check(panel(job_order(PLAIN)) == [], "5. a Job Order made from PEPL's own material: no customer-material panel")
rows = panel(job_order(SHAFT))
check(len(rows) == 1 and rows[0]["colour"] == "red" and "has no Sales Order" in rows[0]["text"], "5. a Job Order using the customer's steel without a Sales Order: red, 'has no Sales Order'")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (the CSM tolerance is back to " + str(site_tol) + " kg).")
