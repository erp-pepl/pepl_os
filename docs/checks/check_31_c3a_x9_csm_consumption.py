# PEPL OS v0.31.0 - Check 31: C3a-X9 customer-supplied material (CSM) consumed by the Delivery Note, and the
# Delivery Note material gate (Off / Warn at Validate, Block at Submit / Hard Block).
# Runs on 0.31.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes this check makes, is undone at the end.
VERSION = "0.31.0"
PARAMS = "PEPL System Parameters"
WARN = "Warn at Validate, Block at Submit"
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
        return ""
    except Exception as e:
        text = frappe.utils.strip_html(str(e))
        check(words.lower() in text.lower(), label + " -> " + text[:240])
        return text


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


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.get_meta("Delivery Note").get_field("custom_csm_consumption")), "1. the Delivery Note shows 'Customer Material Consumed'")
check(bool(frappe.get_meta("Stock Entry").get_field("custom_delivery_note")), "1. the Stock Entry links the Delivery Note that consumed the material")
site_mode = frappe.db.get_single_value(PARAMS, "dn_material_gate_mode")
site_tol = frappe.db.get_single_value(PARAMS, "csm_reconciliation_tolerance_kg")
print("INFO  this site: Delivery Note Material Gate Mode = " + str(site_mode) + ", CSM tolerance = " + str(site_tol) + " kg")


def set_gate(mode):
    params = frappe.get_doc(PARAMS)
    params.dn_material_gate_mode = mode
    params.csm_reconciliation_tolerance_kg = 0.5
    params.save()


set_gate(WARN)

# ---------------- 2. an order made from the customer's steel ----------------
# The finished shaft is a sales item with an 8-digit HSN code (India Compliance checks Sales Orders and Delivery
# Notes); the customer's steel is weighed in Kg and heat-tracked, so its receipt names the heat number.
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    hsn = codes[0] if codes else ""
fg_values = {"doctype": "Item", "item_code": "CHK31-SHAFT-" + RUN, "item_name": "CHK31 Shaft " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 1 if hsn else 0}
if hsn:
    fg_values["gst_hsn_code"] = hsn
SHAFT = frappe.get_doc(fg_values).insert().name
STEEL = frappe.get_doc({"doctype": "Item", "item_code": "CHK31-CSM-STEEL-" + RUN, "item_name": "CHK31 Customer Steel " + RUN, "item_group": "Customer-Supplied Material", "stock_uom": "Kg", "is_stock_item": 1, "is_sales_item": 0}).insert().name
bom = frappe.get_doc({
    "doctype": "BOM", "item": SHAFT, "company": company, "quantity": 1, "is_active": 1, "is_default": 1,
    "currency": frappe.db.get_value("Company", company, "default_currency"),
    "items": [{"item_code": STEEL, "qty": 2, "rate": 0}],
}).insert()
bom.submit()
groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
customer = frappe.get_doc({"doctype": "Customer", "customer_name": "CHK31 Customer " + RUN, "customer_type": "Company",
                           "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert().name
so = frappe.get_doc({
    "doctype": "Sales Order", "customer": customer, "company": company, "transaction_date": today, "delivery_date": due, "custom_sector": "Private",
    "items": [{"item_code": SHAFT, "qty": 20, "rate": 100, "warehouse": wh("FG Stores"), "delivery_date": due}],
}).insert()
so.submit()
line = so.items[0].name


def stock_entry(entry_type, rows, sales_order=None):
    purpose = frappe.db.get_value("Stock Entry Type", entry_type, "purpose")
    doc = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": entry_type, "purpose": purpose, "company": company,
                          "custom_sales_order": sales_order, "items": rows}).insert()
    doc.submit()
    return doc


stock_entry("Material Receipt", [{"item_code": STEEL, "qty": 25, "t_warehouse": wh("CSM Stores"), "custom_heat_number": "CHK31-H1-" + RUN}], so.name)
stock_entry("Material Receipt", [{"item_code": SHAFT, "qty": 20, "t_warehouse": wh("FG Stores"), "basic_rate": 100}])
print("INFO  Sales Order " + so.name + ": 20 shafts at 2 kg of the customer's steel each; 25 kg received (heat CHK31-H1-" + RUN + ")")


def delivery(qty):
    return frappe.get_doc({
        "doctype": "Delivery Note", "customer": customer, "company": company, "posting_date": today,
        "items": [{"item_code": SHAFT, "qty": qty, "rate": 100, "warehouse": wh("FG Stores"), "against_sales_order": so.name, "so_detail": line}],
    })


def issues(dn_name):
    return frappe.get_all("Stock Entry", filters={"custom_delivery_note": dn_name, "docstatus": 1}, pluck="name")


def balance():
    rows = frappe.call("pepl_os.pepl_stores.csm.get_order_balance", sales_order=so.name)
    found = [r for r in rows if r.get("item_code") == STEEL]
    return found[0] if found else {}


# ---------------- 3. a delivery consumes the steel it used ----------------
dn1 = delivery(5).insert()
check(STEEL in (dn1.custom_csm_consumption or "") and "10" in (dn1.custom_csm_consumption or ""), "3. the draft Delivery Note for 5 shafts shows 10 kg of the customer's steel to consume")
dn1.submit()
got = issues(dn1.name)
check(len(got) == 1, "3. on submit it posted one Material Issue " + ", ".join(got))
if got:
    entry = frappe.get_doc("Stock Entry", got[0])
    row = entry.items[0]
    check(entry.custom_sales_order == so.name and row.item_code == STEEL and abs(row.qty - 10) < 0.001, "3. 10 kg of the customer's steel against " + so.name)
    check(row.s_warehouse == wh("CSM Stores") and (row.custom_heat_number or "") == "CHK31-H1-" + RUN, "3. from CSM Stores, with its heat number")
b = balance()
check(abs(float(b.get("issued") or 0) - 10) < 0.001 and abs(float(b.get("balance") or 0) - 15) < 0.001, "3. CSM Balance by Order: 10 kg consumed, 15 kg left")

# ---------------- 4. the next delivery consumes only its own share ----------------
dn2 = delivery(3).insert()
dn2.submit()
got2 = issues(dn2.name)
check(len(got2) == 1 and abs(frappe.get_doc("Stock Entry", got2[0]).items[0].qty - 6) < 0.001, "4. 3 more shafts consume 6 kg (16 kg in all, 9 kg left)")

# ---------------- 5. the material gate ----------------
dn3 = delivery(5).insert()
check(dn3.docstatus == 0, "5. Warn mode: a Delivery Note for 5 more shafts (needs 10 kg, 9 kg left) is saved, with a warning")
refused("5. Warn mode: it cannot be submitted", lambda: frappe.get_doc("Delivery Note", dn3.name).submit(), "does not cover")
set_gate("Hard Block")
refused("5. Hard Block: such a Delivery Note cannot even be saved", lambda: delivery(5).insert(), "Hard Block")
set_gate("Off")
dn3 = frappe.get_doc("Delivery Note", dn3.name)
dn3.submit()
got3 = issues(dn3.name)
check(dn3.docstatus == 1 and len(got3) == 1 and abs(frappe.get_doc("Stock Entry", got3[0]).items[0].qty - 9) < 0.001, "5. gate Off: it is delivered and consumes the 9 kg there is")

# ---------------- 6. cancelling a delivery gives the steel back ----------------
dn2 = frappe.get_doc("Delivery Note", dn2.name)
dn2.cancel()
check(frappe.db.get_value("Stock Entry", got2[0], "docstatus") == 2 if got2 else False, "6. cancelling the second Delivery Note cancelled its Material Issue")
check(abs(float(balance().get("balance") or 0) - 6) < 0.001, "6. the 6 kg are back on the order")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (Delivery Note Material Gate Mode is back to " + str(site_mode) + ").")
