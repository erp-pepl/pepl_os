# PEPL OS v0.33.0 - Check 33: C3a-X11 the contractual LD clause on the Sales Order (sector defaults, checks, fixed
# once submitted) and LD for late delivery (weeks or part, delivered late + pending, grace, cap).
# Runs on 0.33.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes this check makes, is undone at the end.
VERSION = "0.33.0"
PARAMS = "PEPL System Parameters"
EXPOSURE = "pepl_os.pepl_production.ld.get_ld_exposure"
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
        check(words.lower() in text.lower(), label + " -> " + text[:200])
        return text


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


def near(value, expected):
    return abs(float(value or 0) - expected) < 0.01


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
print("INFO  company " + company)


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def day(offset):
    return frappe.utils.add_days(today, offset)


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
meta = frappe.get_meta("Sales Order")
check(all(meta.get_field(f) for f in ("custom_ld_applicable", "custom_ld_rate_percent", "custom_ld_period", "custom_ld_max_percent", "custom_ld_grace_days", "custom_ld_basis", "custom_ld_clause")), "1. the Sales Order has its Liquidated Damages (LD) section")
check(bool(frappe.get_meta(PARAMS).get_field("custom_ld_default_sectors")), "1. System Parameters has Production > LD defaults")
site_sectors = frappe.db.get_single_value(PARAMS, "custom_ld_default_sectors")
print("INFO  this site: LD sectors by default = " + str(site_sectors).replace("\n", ", "))

params = frappe.get_doc(PARAMS)
params.custom_ld_default_sectors = "Railways\nDefence"
params.custom_ld_default_rate_percent = 0.5
params.custom_ld_default_period = "Week"
params.custom_ld_default_max_percent = 10
params.save()

# ---------------- 2. a customer and a part to sell ----------------
# The part is a bought-out sales item with an 8-digit HSN code (India Compliance checks Sales Orders and Delivery
# Notes). Its stock is received 40 days ago, inside this bench's Fiscal Year.
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    hsn = codes[0] if codes else ""
values = {"doctype": "Item", "item_code": "CHK33-PART-" + RUN, "item_name": "CHK33 Part " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 1 if hsn else 0, "valuation_rate": 50}
if hsn:
    values["gst_hsn_code"] = hsn
PART = frappe.get_doc(values).insert().name
receipt = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
                          "set_posting_time": 1, "posting_date": day(-40),
                          "items": [{"item_code": PART, "qty": 100, "t_warehouse": wh("Bought-Out Stores"), "basic_rate": 50}]}).insert()
receipt.submit()
groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
customer = frappe.get_doc({"doctype": "Customer", "customer_name": "CHK33 Customer " + RUN, "customer_type": "Company",
                           "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert().name


def order(sector, ordered_days_ago, due_in, terms=None):
    doc = frappe.get_doc({
        "doctype": "Sales Order", "customer": customer, "company": company, "custom_sector": sector,
        "transaction_date": day(-ordered_days_ago), "delivery_date": day(due_in),
        "items": [{"item_code": PART, "qty": 10, "rate": 100, "warehouse": wh("Bought-Out Stores"), "delivery_date": day(due_in)}],
    })
    for key in (terms or {}):
        doc.set(key, terms[key])
    return doc.insert()


# ---------------- 3. the clause ----------------
rail = order("Railways", 0, 10)
check(rail.custom_ld_applicable == 1 and near(rail.custom_ld_rate_percent, 0.5) and rail.custom_ld_period == "Week" and near(rail.custom_ld_max_percent, 10), "3. a Railways order starts with LD 0.5 % per week, cap 10 %")
private = order("Private", 0, 10)
check(not private.custom_ld_applicable, "3. a Private order starts without LD")
refused("3. LD ticked with a 0 % rate is refused", lambda: order("Private", 0, 10, {"custom_ld_applicable": 1, "custom_ld_rate_percent": 0, "custom_ld_max_percent": 10}), "LD Rate")
rail.submit()
refused("3. the clause is fixed once the order is submitted", lambda: frappe.get_doc("Sales Order", rail.name).update({"custom_ld_rate_percent": 2}).save(), "after submission")

# ---------------- 4. LD for late delivery ----------------
late = order("Railways", 30, -20)
late.submit()
x = frappe.call(EXPOSURE, sales_order=late.name)
print("INFO  " + late.name + ": 10 parts at 100, due 20 days ago -> LD today " + str(x.get("total")))
check(near(x.get("total"), 15), "4. due 20 days ago (= 3 weeks, part of a week counts): 1000 x 0.5 % x 3 = 15")
dn = frappe.get_doc({"doctype": "Delivery Note", "customer": customer, "company": company, "posting_date": today,
                     "items": [{"item_code": PART, "qty": 4, "rate": 100, "warehouse": wh("Bought-Out Stores"), "against_sales_order": late.name, "so_detail": late.items[0].name}]}).insert()
dn.submit()
x = frappe.call(EXPOSURE, sales_order=late.name)
line = x.get("lines")[0]
check(line.get("delivered") == 4 and line.get("pending") == 6 and near(x.get("total"), 15), "4. 4 delivered today (3 weeks late) + 6 still pending: (400 + 600) x 0.5 % x 3 = 15")
x = frappe.call(EXPOSURE, sales_order=late.name, as_on=day(14))
check(near(x.get("total"), 21), "4. as on 14 days from now: 400 x 0.5 % x 3 + 600 x 0.5 % x 5 = 6 + 15 = 21")

# ---------------- 5. grace days and the cap ----------------
grace = order("Private", 30, -10, {"custom_ld_applicable": 1, "custom_ld_rate_percent": 0.5, "custom_ld_max_percent": 10, "custom_ld_period": "Week", "custom_ld_grace_days": 7})
grace.submit()
check(near(frappe.call(EXPOSURE, sales_order=grace.name).get("total"), 5), "5. due 10 days ago with 7 grace days: 3 days late = 1 week: 1000 x 0.5 % = 5")
x = frappe.call(EXPOSURE, sales_order=rail.name, as_on=day(165))
check(near(x.get("total"), 100) and near(x.get("cap_amount"), 100), "5. 155 days late = 23 weeks x 0.5 % = 11.5 %, capped at 10 % of 1000 = 100")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (LD sectors by default are back to " + str(site_sectors).replace("\n", ", ") + ").")
