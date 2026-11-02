# PEPL OS v0.51.0 - UAT setup for Cycle 3a (demo site only): the records the two UAT guides start from.
# docs/cycle3a_kiosk_uat.md and docs/cycle3a_production_manager_uat.md.
# System Console, Type = Python. Tick "Commit": this script SAVES the UAT records. Run it on the DEMO site only.
# Safe to run again: a record that already exists is kept as it is (shown as "kept"), nothing is made twice.
#
# 1. Put the real names and e-mail addresses of the people who will test (named logins, never Administrator).
#    Leave an e-mail as it is to create a test login with that address.
FOREMAN_EMAIL = "uat.foreman@pepl.example"
FOREMAN_NAME = "UAT Foreman"
MANAGER_EMAIL = "uat.prodmgr@pepl.example"
MANAGER_NAME = "UAT Production Manager"
TABLET_EMAIL = "tablet-mill01@pepl.example"
# 2. The password given to the three new logins (only to logins this script creates). Change it if you like.
PASSWORD = "Pepl#Uat-2026"

PARAMS = "PEPL System Parameters"
SPR = "PEPL Shift Production Entry"
LEVEL1 = "1 - Trainee"
LEVEL3 = "3 - Runs independently"
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


def day(offset):
    return frappe.utils.add_days(today, offset)


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


print("INFO  company " + company + ", pepl_os " + str(frappe.db.get_value("Installed Application", {"app_name": "pepl_os"}, "app_version")))
digits = int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
if digits != 4:
    problems.append("Operator PIN Digits is " + str(digits) + " on this site; the guides use 4-digit PINs (1357, 2468). Set it to 4 or tell the consultant.")
if not frappe.db.exists("PEPL Downtime Category", "No Plan / No Load"):
    problems.append("Downtime category 'No Plan / No Load' is missing.")
if not wh("FG Stores"):
    problems.append("Warehouse 'FG Stores' is missing for " + company + ".")

if problems:
    for p in problems:
        print("STOP  " + p)
    print("Nothing was made. Fix the line(s) above and run again.")
else:
    # ---------------- logins (named; the tablet login is a Website User that opens the kiosk) ----------------
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

    FOREMAN = login(FOREMAN_EMAIL, FOREMAN_NAME, profile="PEPL Foreman")
    MANAGER = login(MANAGER_EMAIL, MANAGER_NAME, profile="PEPL Production Manager")
    TABLET = login(TABLET_EMAIL, "Tablet MILL-01", roles=["PEPL Kiosk"])

    # ---------------- machines and machine groups ----------------
    def ensure(doctype, name, values):
        if frappe.db.exists(doctype, name):
            note(False, doctype + " " + name)
            return name
        values["doctype"] = doctype
        doc = frappe.get_doc(values).insert()
        note(True, doctype + " " + doc.name)
        return doc.name

    ensure("Workstation Type", "MILL", {"workstation_type": "MILL"})
    ensure("Workstation Type", "LATHE", {"workstation_type": "LATHE"})
    ensure("Workstation", "MILL-01", {"workstation_name": "MILL-01", "workstation_type": "MILL", "production_capacity": 1})
    ensure("Workstation", "LATHE-01", {"workstation_name": "LATHE-01", "workstation_type": "LATHE", "production_capacity": 1})

    # ---------------- shifts ----------------
    ensure("PEPL Shift", "General Shift", {"shift_name": "General Shift", "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30, "is_active": 1})
    ensure("PEPL Shift", "Evening Shift", {"shift_name": "Evening Shift", "start_time": "16:30:00", "end_time": "01:00:00", "break_minutes": 30, "is_active": 1})

    # ---------------- settings the UAT relies on (each change is printed) ----------------
    p = frappe.get_doc(PARAMS)
    changes = []

    def setp(field, value):
        if p.get(field) != value:
            changes.append(field + ": " + str(p.get(field)) + " -> " + str(value))
            p.set(field, value)

    have = [r.machine_group for r in (p.get("custom_machine_hour_rates") or [])]
    for group, rate in (("MILL", 600), ("LATHE", 500)):
        if group not in have:
            p.append("custom_machine_hour_rates", {"machine_group": group, "rate_per_hour": rate})
            changes.append("Machine-Hour Rate " + group + " = " + str(rate) + " a hour")
    setp("custom_job_order_from_sales_order", 1)
    setp("enable_operational_todos", 1)
    setp("custom_rejections_to_scrap", 1)
    setp("custom_standup_exception_only", 1)
    setp("custom_production_notification_owner", MANAGER)
    if not p.get("custom_stores_notification_owner"):
        setp("custom_stores_notification_owner", MANAGER)
    if not p.get("custom_ld_default_sectors"):
        setp("custom_ld_default_sectors", "Railways\nDefence")
    if changes:
        p.save()
        for c in changes:
            note(True, "System Parameters " + c)
    else:
        note(False, "System Parameters (already as the UAT needs)")
    ms = frappe.get_doc("Manufacturing Settings")
    if not ms.disable_capacity_planning:
        ms.disable_capacity_planning = 1
        ms.save()
        note(True, "Manufacturing Settings: capacity planning off (the machines have no working hours yet; PEPL input 9)")

    # ---------------- operators ----------------
    def operator(code, name, pin, skills, eligible):
        if frappe.db.exists("PEPL Operator", code):
            note(False, "operator " + code)
            return code
        frappe.get_doc({"doctype": "PEPL Operator", "employee_code": code, "operator_name": name, "status": "Active", "pin": pin,
                        "default_shift": "General Shift", "eligible_shifts": [{"shift": s} for s in eligible],
                        "skills": [{"workstation_type": g, "level": lv} for g, lv in skills]}).insert()
        note(True, "operator " + code + " " + name + ", PIN " + pin + ", skills " + ", ".join(g + " " + lv for g, lv in skills))
        return code

    operator("OP-101", "Ramesh Kumar", "1357", [("MILL", LEVEL3), ("LATHE", LEVEL3)], ["General Shift"])
    operator("OP-102", "Suresh Patil", "2468", [("MILL", LEVEL1)], ["General Shift"])

    # an Employee for OP-102, not linked yet (Production Manager UAT D1 links it, D2 sets it to Left)
    if frappe.db.exists("Employee", {"first_name": "Suresh", "last_name": "Patil", "company": company}):
        note(False, "Employee Suresh Patil")
    else:
        genders = frappe.get_all("Gender", pluck="name")
        emp = frappe.get_doc({"doctype": "Employee", "first_name": "Suresh", "last_name": "Patil", "company": company, "status": "Active",
                              "gender": "Male" if "Male" in genders else (genders[0] if genders else None),
                              "date_of_birth": "1990-05-15", "date_of_joining": "2022-04-01"}).insert()
        note(True, "Employee " + emp.name + " Suresh Patil (joined 2022-04-01), to link to OP-102 in the UAT")

    # ---------------- the shaft, its scrap item, BOM, CST ----------------
    hsn = ""
    if frappe.db.exists("DocType", "GST HSN Code"):
        codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
        hsn = codes[0] if codes else ""
    scrap_groups = [g for g in frappe.get_all("Item Group", filters={"is_group": 0, "name": ["like", "%Scrap%"]}, pluck="name")]
    scrap_group = "Brass Scrap" if "Brass Scrap" in scrap_groups else (scrap_groups[0] if scrap_groups else "All Item Groups")
    ensure("Item", "UAT-SCRAP-BRASS", {"item_code": "UAT-SCRAP-BRASS", "item_name": "UAT Brass Turnings", "item_group": scrap_group, "stock_uom": "Kg",
                                       "is_stock_item": 1, "is_sales_item": 0, "is_purchase_item": 0})
    if frappe.get_all("PEPL Scrap Rate", filters={"scrap_item": "UAT-SCRAP-BRASS"}, limit=1):
        note(False, "PEPL Scrap Rate for UAT-SCRAP-BRASS")
    else:
        frappe.get_doc({"doctype": "PEPL Scrap Rate", "scrap_item": "UAT-SCRAP-BRASS", "rate": 40, "effective_from": day(-60)}).insert()
        note(True, "PEPL Scrap Rate UAT-SCRAP-BRASS 40 a kg")

    def sold_item(code, name, extra):
        values = {"item_code": code, "item_name": name, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 1 if hsn else 0}
        if hsn:
            values["gst_hsn_code"] = hsn
        values.update(extra)
        return ensure("Item", code, values)

    SHAFT = sold_item("UAT-SHAFT", "UAT Shaft", {"weight_per_unit": 0.25, "weight_uom": "Kg", "custom_rejection_scrap_item": "UAT-SCRAP-BRASS"})
    PLATE = sold_item("UAT-PLATE", "UAT Plate (no BOM)", {})
    ensure("Item", "UAT-BAR", {"item_code": "UAT-BAR", "item_name": "UAT Brass Bar", "item_group": "Bought-Out Components", "stock_uom": "Nos",
                               "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10})
    ensure("Operation", "UAT Turning", {"name": "UAT Turning", "workstation": "MILL-01"})
    bom = frappe.db.get_value("BOM", {"item": SHAFT, "is_default": 1, "docstatus": 1}, "name")
    if bom:
        note(False, "BOM " + bom)
    else:
        b = frappe.get_doc({"doctype": "BOM", "item": SHAFT, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
                            "currency": frappe.db.get_value("Company", company, "default_currency"), "items": [{"item_code": "UAT-BAR", "qty": 1, "rate": 10}],
                            "operations": [{"operation": "UAT Turning", "workstation": "MILL-01", "time_in_mins": 6}]}).insert()
        b.submit()
        note(True, "BOM " + b.name + ": 1 bar, UAT Turning 6 minutes a piece on MILL-01")
    cst_name = frappe.db.get_value("PEPL CST Cost Sheet", {"linked_item": SHAFT, "status": "Approved"}, "name")
    if cst_name:
        note(False, "CST " + cst_name)
    else:
        product = frappe.db.get_value("PEPL Product Master", {"linked_item": SHAFT}, "name")
        if not product:
            product = frappe.get_doc({"doctype": "PEPL Product Master", "product_name": "UAT Shaft", "product_type": "Single Component", "status": "Active", "linked_item": SHAFT}).insert().name
        rm_group = (frappe.get_all("PEPL RM Group", pluck="name", limit=1) or [None])[0]
        if not rm_group:
            rm_group = frappe.get_doc({"doctype": "PEPL RM Group", "group_name": "UAT Brass Rod", "material_base": "Brass", "default_uom": "Kg", "is_active": 1, "auto_sync_to_item_group": 0}).insert().name
        cst = frappe.get_doc({"doctype": "PEPL CST Cost Sheet", "cst_title": "UAT Shaft", "linked_product": product, "linked_item": SHAFT, "status": "Approved",
                              "costing_date": day(-40), "overhead_percent": 10,
                              "components": [{"manufactured_or_bought_out": "Manufactured", "rm_group": rm_group, "quantity_per_assembly": 1,
                                              "raw_material_cost": 12, "machining_cost": 50, "surface_treatment_cost": 5}]}).insert()
        note(True, "CST " + cst.name + " Approved: " + str(cst.total_components_cost + cst.overhead_amount) + " a piece")

    # ---------------- the Railways customer and the Sales Order (submitted: it drafts the Job Order the UAT starts from) ----------------
    customer = frappe.db.get_value("Customer", "UAT-RLY-CUSTOMER-A", "name")
    if customer:
        note(False, "Customer " + customer)
    else:
        groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
        territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
        customer = frappe.db.get_value("Customer", {"customer_name": "UAT Railway Customer"}, "name")
        if customer:
            note(False, "Customer " + customer)
        else:
            customer = frappe.get_doc({"doctype": "Customer", "customer_name": "UAT Railway Customer", "customer_type": "Company",
                                       "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert().name
            note(True, "Customer " + customer + " (UAT Railway Customer)")
    # found again by its customer PO no. (a child table read on its own returns nothing in the System Console)
    open_so = frappe.get_all("Sales Order", filters={"po_no": "UAT-C3A", "docstatus": ["<", 2]}, pluck="name", limit=1)
    if open_so:
        note(False, "Sales Order " + open_so[0] + " (PO no. UAT-C3A)")
        SO = open_so[0]
    else:
        so = frappe.get_doc({"doctype": "Sales Order", "customer": customer, "company": company, "custom_sector": "Railways", "po_no": "UAT-C3A",
                             "transaction_date": day(-30), "delivery_date": day(-2),
                             "items": [{"item_code": SHAFT, "qty": 40, "rate": 100, "warehouse": wh("FG Stores"), "delivery_date": day(-2)},
                                       {"item_code": PLATE, "qty": 5, "rate": 200, "warehouse": wh("FG Stores"), "delivery_date": day(-2)}]}).insert()
        SO = so.name
        note(True, "Sales Order " + SO + ": Railways, 40 x UAT-SHAFT + 5 x UAT-PLATE, due " + str(day(-2)) + " (2 days late on purpose)")
    so = frappe.get_doc("Sales Order", SO)
    if so.docstatus == 0:
        so.submit()
        note(True, "Sales Order " + SO + " submitted: LD clause filled; Job Order drafted for the shaft; ToDo PRD-NO-BOM for the plate")
    jo = frappe.get_all("Work Order", filters={"sales_order": SO, "production_item": SHAFT, "docstatus": ["<", 2]}, fields=["name", "docstatus"], limit=1)
    print("INFO  Job Order for the shaft: " + (jo[0].name + (" (draft - the Production Manager submits it in UAT A4)" if jo[0].docstatus == 0 else " (submitted)") if jo else "NONE - tell the consultant"))

    # ---------------- an earlier shift on LATHE-01 (so the foreman board shows LATHE-01 'Missing' today, kiosk UAT D2) ----------------
    if frappe.get_all(SPR, filters={"workstation": "LATHE-01", "docstatus": 1}, limit=1):
        note(False, "a submitted shift entry on LATHE-01")
    else:
        e = frappe.get_doc({"doctype": SPR, "posting_date": day(-1), "shift": "General Shift", "workstation": "LATHE-01", "operator": "OP-101", "company": company})
        e.append("downtime", {"downtime_category": "No Plan / No Load", "from_time": "08:00", "to_time": "16:30"})
        e.insert()
        e.submit()
        note(True, "shift entry " + e.name + " on LATHE-01, " + str(day(-1)) + ": no load all shift (submitted)")

    # ---------------- the stand-up e-mail goes to the Production Manager ----------------
    if frappe.db.exists("Email Group", "Standup Email Group"):
        if frappe.db.exists("Email Group Member", {"email_group": "Standup Email Group", "email": MANAGER}):
            note(False, MANAGER + " in the Standup Email Group")
        else:
            frappe.get_doc({"doctype": "Email Group Member", "email_group": "Standup Email Group", "email": MANAGER}).insert()
            note(True, MANAGER + " added to the Standup Email Group")
    else:
        print("WARN  there is no 'Standup Email Group' on this site; Production Manager UAT F2 (the e-mail) cannot be tested")

    print("")
    print("RESULT: " + str(len(made)) + " made, " + str(len(kept)) + " kept (already there).")
    print("")
    print("UAT DAY, IN THIS ORDER:")
    print("  1. Production Manager (" + MANAGER + "): Production Manager guide, section A - open Sales Order " + SO + ", then submit its Job Order.")
    print("  2. Foreman and operators: the kiosk guide. Tablet login " + TABLET + ", page /kiosk?machine=MILL-01,")
    print("     operators OP-101 (PIN 1357) and OP-102 (PIN 2468), shift General Shift. Foreman login " + FOREMAN + ", page /foreman.")
    print("  3. Production Manager: the rest of the Production Manager guide (sections B to F).")
    print("Commit must be TICKED for this script: if it was unticked, nothing above was saved - tick it and run again.")
