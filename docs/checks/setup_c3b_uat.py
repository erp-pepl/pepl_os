# PEPL OS v0.78.0 - UAT setup for Cycle 3b (demo site only): the records docs/cycle3b_quality_manager_uat.md starts from.
# System Console, Type = Python. Tick "Commit": this script SAVES the UAT records. Run it on the DEMO site only.
# Safe to run again: a record that already exists is kept as it is (shown as "kept"), nothing is made twice.
#
# 1. The real name and e-mail of the Quality Manager who will test (a named login, never Administrator), and of the
#    person who signs Critical NCRs as PEPL CEO. Leave an e-mail as it is to create a test login with that address.
QM_EMAIL = "uat.quality@pepl.example"
QM_NAME = "UAT Quality Manager"
CEO_EMAIL = "uat.ceo@pepl.example"
CEO_NAME = "UAT CEO"
# 2. The password given to the logins this script creates (only to new ones).
PASSWORD = "Pepl#Uat-2026"

PARAMS = "PEPL System Parameters"
made = []
kept = []
problems = []


def note(created, text):
    if created:
        made.append(text)
        print("MADE  " + text)
    else:
        kept.append(text)
        print("KEPT  " + text)


company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
today = frappe.utils.today()


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


print("INFO  company " + company + ", pepl_os " + str(frappe.db.get_value("Installed Application", {"app_name": "pepl_os"}, "app_version")))
for store in ["Bought-Out Stores", "FG Stores"]:
    if not wh(store):
        problems.append("Warehouse '" + store + "' is missing for " + company + ".")
if not frappe.db.exists("Role Profile", "PEPL Quality Manager"):
    problems.append("Role Profile 'PEPL Quality Manager' is missing (bench migrate makes it).")

if problems:
    for p in problems:
        print("STOP  " + p)
    print("Nothing was made. Fix the line(s) above and run again.")
else:
    # ---------------- logins ----------------
    def login(email, first_name, profile=None, roles=None):
        if frappe.db.exists("User", email):
            note(False, "login " + email)
            return email
        values = {"doctype": "User", "email": email, "first_name": first_name, "send_welcome_email": 0, "new_password": PASSWORD, "enabled": 1}
        if profile:
            values["role_profile_name"] = profile
        if roles:
            values["roles"] = [{"role": r} for r in roles]
        frappe.get_doc(values).insert()
        note(True, "login " + email + (" (Role Profile " + profile + ")" if profile else " (" + ", ".join(roles) + ")") + ", password " + PASSWORD)
        return email

    QM = login(QM_EMAIL, QM_NAME, profile="PEPL Quality Manager")
    CEO = login(CEO_EMAIL, CEO_NAME, roles=["PEPL CEO"])

    def ensure(doctype, name, values):
        if frappe.db.exists(doctype, name):
            note(False, doctype + " " + name)
            return name
        values["doctype"] = doctype
        doc = frappe.get_doc(values).insert()
        note(True, doctype + " " + doc.name)
        return doc.name

    # ---------------- settings the UAT relies on (each change is printed) ----------------
    p = frappe.get_doc(PARAMS)
    changes = []

    def setp(field, value):
        if p.get(field) != value:
            changes.append(field + ": " + str(p.get(field)) + " -> " + str(value))
            p.set(field, value)

    setp("custom_quality_notification_owner", QM)
    setp("custom_incoming_qc_gate_mode", "Soft Block")
    setp("custom_calibration_gate_mode", "Hard Block")
    setp("custom_dispatch_gate_mode", "Soft Block")
    setp("custom_capa_verification_days", 90)
    setp("enable_operational_todos", 1)
    if changes:
        p.save()
        for c in changes:
            note(True, "setting " + c)
    else:
        note(False, "settings (all as the UAT needs)")

    # ---------------- inspection plans, items, supplier, customer ----------------
    def parameter(name):
        return ensure("Quality Inspection Parameter", name, {"parameter": name})

    def template(name, spec, low, high):
        if frappe.db.exists("Quality Inspection Template", name):
            note(False, "Quality Inspection Template " + name)
            return name
        frappe.get_doc({"doctype": "Quality Inspection Template", "quality_inspection_template_name": name,
                        "item_quality_inspection_parameter": [{"specification": parameter(spec), "numeric": 1, "min_value": low, "max_value": high}]}).insert()
        note(True, "Quality Inspection Template " + name + " (" + spec + " " + str(low) + " - " + str(high) + ")")
        return name

    PIN_PLAN = template("UAT Pin Plan", "UAT Pin Diameter", 9.9, 10.1)
    SHAFT_PLAN = template("UAT Shaft Final Plan", "UAT Shaft Diameter", 19.9, 20.1)
    hsn = ""
    if frappe.db.exists("DocType", "GST HSN Code"):
        codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
        hsn = codes[0] if codes else ""

    def item(code, group, values):
        if frappe.db.exists("Item", code):
            note(False, "Item " + code)
            return code
        v = {"doctype": "Item", "item_code": code, "item_name": code, "item_group": group, "stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": 50}
        if hsn:
            v["gst_hsn_code"] = hsn
        v.update(values)
        frappe.get_doc(v).insert()
        note(True, "Item " + code)
        return code

    PIN = item("UAT-QC-PIN", "Bought-Out Components", {"is_purchase_item": 1, "is_sales_item": 0, "quality_inspection_template": PIN_PLAN})
    frappe.db.set_value("Item", PIN, "inspection_required_before_purchase", 1)
    SHAFT = item("UAT-QC-SHAFT", "Finished Goods", {"is_sales_item": 1 if hsn else 0, "quality_inspection_template": SHAFT_PLAN})
    frappe.db.set_value("Item", SHAFT, "inspection_required_before_delivery", 1)
    SUPPLIER = "UAT QC Supplier"
    if not frappe.db.exists("Supplier", SUPPLIER):
        frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER}).insert()
        note(True, "Supplier " + SUPPLIER)
    else:
        note(False, "Supplier " + SUPPLIER)
    frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")
    CUSTOMER = "UAT QC Railway"
    if not frappe.db.exists("Customer", CUSTOMER):
        groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
        territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
        frappe.get_doc({"doctype": "Customer", "customer_name": CUSTOMER, "customer_type": "Company",
                        "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert()
        note(True, "Customer " + CUSTOMER)
    else:
        note(False, "Customer " + CUSTOMER)

    # ---------------- instruments: one calibrated, one overdue ----------------
    def gauge(code, days_ago):
        if frappe.db.exists("PEPL Instrument", code):
            note(False, "PEPL Instrument " + code)
            return code
        frappe.get_doc({"doctype": "PEPL Instrument", "instrument_id": code, "instrument_name": code, "instrument_type": "Vernier Caliper",
                        "calibration_frequency_days": 365, "measuring_range": "0-150 mm", "least_count": "0.02 mm", "location": "QC room"}).insert()
        rec = frappe.get_doc({"doctype": "PEPL Calibration Record", "instrument": code, "calibration_date": frappe.utils.add_days(today, -days_ago),
                              "result": "Pass", "certificate_no": "UAT-" + code, "agency": "UAT Lab"}).insert()
        rec.submit()
        note(True, "PEPL Instrument " + code + " calibrated " + str(days_ago) + " days ago")
        return code

    gauge("UAT-VC-01", 10)
    gauge("UAT-VC-02", 400)

    # ---------------- stock of shafts and one submitted order for 30 (agency inspection) ----------------
    if not frappe.db.get_value("Bin", {"item_code": SHAFT, "warehouse": wh("FG Stores")}, "actual_qty"):
        se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
                             "items": [{"item_code": SHAFT, "qty": 40, "t_warehouse": wh("FG Stores"), "basic_rate": 50}]}).insert()
        se.submit()
        note(True, "40 UAT-QC-SHAFT received into FG Stores (" + se.name + ")")
    else:
        note(False, "stock of UAT-QC-SHAFT")
    so = frappe.db.get_value("Sales Order", {"customer": CUSTOMER, "docstatus": 1}, "name")
    if so:
        note(False, "Sales Order " + so)
    else:
        due = frappe.utils.add_days(today, 20)
        doc = frappe.get_doc({"doctype": "Sales Order", "customer": CUSTOMER, "company": company, "transaction_date": today, "delivery_date": due,
                              "custom_sector": "Private", "items": [{"item_code": SHAFT, "qty": 30, "rate": 100, "warehouse": wh("FG Stores"), "delivery_date": due}]}).insert()
        doc.submit()
        note(True, "Sales Order " + doc.name + " for 30 UAT-QC-SHAFT")

    print("")
    print("UAT records: " + str(len(made)) + " made, " + str(len(kept)) + " kept. Logins: " + QM + ", " + CEO + " (password " + PASSWORD + " for new ones).")
    print("Commit must be ticked for these to stay. Then follow docs/cycle3b_quality_manager_uat.md.")
