# PEPL OS v0.27.0 - Check 27: C3a-X6 a Production Plan may not double-book a machine -
# rows laid out on their machines, clashes with the plan's own rows, open Job Orders and other open plans,
# machine capacity, Advisory / Soft Block (reason) / Hard Block on submit.
# Runs on 0.27.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters and Manufacturing Settings changes this check makes, is undone at the end.
VERSION = "0.27.0"
PARAMS = "PEPL System Parameters"
MODE = "custom_double_booking_mode"
CLASHES = "custom_machine_clashes"
GATE = "pepl_os.pepl_production.machine_booking.booking_gate_check"
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
DAY = frappe.utils.add_days(frappe.utils.today(), 40)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
print("INFO  company " + company + "; plans are for " + str(DAY))


def at(hhmm):
    return str(DAY) + " " + hhmm + ":00"


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.get_meta(PARAMS).get_field(MODE)), "1. System Parameters has Production > Machine Double-Booking Mode")
check(bool(frappe.get_meta("Production Plan").get_field(CLASHES)), "1. the Production Plan has 'Machine Double-Bookings'")
site_mode = frappe.db.get_single_value(PARAMS, MODE)
print("INFO  this site: Machine Double-Booking Mode = " + str(site_mode))
check(site_mode in ("Advisory", "Soft Block", "Hard Block"), "1. the mode on this site is Advisory, Soft Block or Hard Block")


def set_mode(mode, reasons=1):
    params = frappe.get_doc(PARAMS)
    params.set(MODE, mode)
    params.custom_enforce_override_reason = reasons
    params.save()


set_mode("Advisory")
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.mins_between_operations = 0
settings.save()

# ---------------- 2. machines, items and BOMs for this run ----------------
# Test items are not sales items, so India Compliance does not ask them for an HSN/SAC code.
M1 = "CHK27 LATHE-01 " + RUN
M2 = "CHK27 VMC-02 " + RUN
frappe.get_doc({"doctype": "Workstation", "workstation_name": M1, "production_capacity": 1}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": M2, "production_capacity": 2}).insert()


def item(code, group, rate=0):
    values = {"doctype": "Item", "item_code": code + "-" + RUN, "item_name": code + " " + RUN, "item_group": group, "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}
    if rate:
        values["valuation_rate"] = rate
    return frappe.get_doc(values).insert().name


ROD = item("CHK27-RM-ROD", "Raw Material", 10)
currency = frappe.db.get_value("Company", company, "default_currency")


def product(code, machine, minutes):
    name = item(code, "Finished Goods")
    operation = code + " Op " + RUN
    frappe.get_doc({"doctype": "Operation", "name": operation, "workstation": machine}).insert()
    bom = frappe.get_doc({
        "doctype": "BOM", "item": name, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
        "currency": currency, "items": [{"item_code": ROD, "qty": 1, "rate": 10}],
        "operations": [{"operation": operation, "workstation": machine, "time_in_mins": minutes}],
    }).insert()
    bom.submit()
    return name


SHAFT = product("CHK27-SHAFT", M1, 60)
PIN = product("CHK27-PIN", M1, 30)
BUSH = product("CHK27-BUSH", M2, 60)
print("INFO  " + SHAFT + " 60 min and " + PIN + " 30 min on " + M1 + " (1 job at a time); " + BUSH + " 60 min on " + M2 + " (2 at a time)")


def plan(rows):
    return frappe.get_doc({
        "doctype": "Production Plan", "company": company, "posting_date": frappe.utils.today(),
        "po_items": [{
            "item_code": code, "bom_no": frappe.db.get_value("BOM", {"item": code, "is_default": 1, "docstatus": 1}),
            "planned_qty": qty, "planned_start_date": at(start), "stock_uom": "Nos", "warehouse": wh("FG Stores"),
        } for code, qty, start in rows],
    }).insert()


def clashes(doc):
    return doc.get(CLASHES) or ""


# ---------------- 3. rows of the same plan ----------------
p = plan([(SHAFT, 1, "09:00"), (PIN, 1, "09:30")])
print("INFO  " + p.name + ": " + clashes(p).replace("\n", " | "))
check(M1 in clashes(p) and PIN in clashes(p), "3. shaft 09:00-10:00 and pin 09:30-10:00 on " + M1 + ": the clash is listed on the plan")
check(frappe.db.exists("Production Plan", p.name), "3. the draft plan is saved all the same")
check(clashes(plan([(SHAFT, 2, "09:00"), (PIN, 1, "11:00")])) == "", "3. shaft x 2 09:00-11:00 then pin at 11:00 (back to back): no clash")
check(clashes(plan([(BUSH, 1, "09:00"), (BUSH, 1, "09:15")])) == "", "3. two bushes at once on " + M2 + " (runs 2 jobs): no clash")
check(M2 in clashes(plan([(BUSH, 1, "09:00"), (BUSH, 1, "09:15"), (BUSH, 1, "09:30")])), "3. a third bush at the same time on " + M2 + ": clash")

# ---------------- 4. open Job Orders hold their machine ----------------
wo = frappe.get_doc({
    "doctype": "Work Order", "production_item": SHAFT, "bom_no": frappe.db.get_value("BOM", {"item": SHAFT, "is_default": 1, "docstatus": 1}),
    "qty": 1, "stock_uom": "Nos", "company": company, "skip_transfer": 1, "fg_warehouse": wh("FG Stores"),
    "planned_start_date": at("14:00"), "transfer_material_against": "Work Order",
})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
print("INFO  Job Order " + wo.name + ": shaft on " + M1 + " 14:00-15:00")
check(clashes(plan([(PIN, 1, "13:30")])) == "", "4. pin 13:30-14:00, ending as the Job Order starts: no clash")
held = clashes(plan([(PIN, 1, "14:15")]))
check(wo.name in held, "4. pin at 14:15 clashes with Job Order " + wo.name)
frappe.get_doc("Work Order", wo.name).update_status("Stopped")  # what the Stop button does
check(frappe.db.get_value("Work Order", wo.name, "status") == "Stopped", "4. the Job Order is stopped")
check(clashes(plan([(PIN, 1, "14:15")])) == "", "4. a stopped Job Order no longer holds the machine")

# ---------------- 5. other open Production Plans hold the machine ----------------
first = plan([(SHAFT, 1, "16:00")])
first.submit()
check(first.docstatus == 1, "5. plan " + first.name + " (shaft 16:00-17:00) is submitted")
check(first.name in clashes(plan([(PIN, 1, "16:30")])), "5. another plan with a pin at 16:30 clashes with " + first.name)

# ---------------- 6. what submit does in each mode ----------------
set_mode("Advisory")
a = plan([(SHAFT, 1, "18:00"), (PIN, 1, "18:30")])
check(frappe.call(GATE, name=a.name) is None, "6. Advisory: no reason asked")
a.submit()
check(a.docstatus == 1, "6. Advisory: the plan with a clash is submitted (warning only)")

set_mode("Soft Block")
s = plan([(SHAFT, 1, "20:00"), (PIN, 1, "20:30")])
gate = frappe.call(GATE, name=s.name)
check(bool(gate) and gate.get("rule_code") == "PRD-DOUBLE-BOOK", "6. Soft Block: the form asks for a reason (PRD-DOUBLE-BOOK)")
refused("6. Soft Block: submit without a reason is refused", lambda: frappe.get_doc("Production Plan", s.name).submit(), "PRD-DOUBLE-BOOK")
frappe.call("pepl_os.common.overrides.record_override", rule_code="PRD-DOUBLE-BOOK", reference_doctype="Production Plan", reference_name=s.name, message=gate.get("message") if gate else "", reason="Pin moves to the second lathe on the day (check " + RUN + ")")
log = frappe.get_all("PEPL Override Log", filters={"rule_code": "PRD-DOUBLE-BOOK", "reference_name": s.name}, fields=["user", "reason"])
check(len(log) == 1 and log[0].user == frappe.session.user, "6. the reason is in the Override Log with the user's name")
s = frappe.get_doc("Production Plan", s.name)
s.submit()
check(s.docstatus == 1, "6. Soft Block: with the reason logged, the plan is submitted")
set_mode("Soft Block", reasons=0)
s2 = plan([(SHAFT, 1, "22:00"), (PIN, 1, "22:30")])
s2.submit()
check(s2.docstatus == 1, "6. Soft Block with 'Require a Reason for Every Override' off: warning only, submitted")

set_mode("Hard Block")
h = plan([(SHAFT, 1, "10:00"), (PIN, 1, "10:30")])
check(frappe.call(GATE, name=h.name) is None, "6. Hard Block: no reason dialog (a reason cannot unlock it)")
refused("6. Hard Block: the plan with a clash cannot be submitted", lambda: frappe.get_doc("Production Plan", h.name).submit(), "Hard Block")
ok = plan([(SHAFT, 1, "10:00"), (PIN, 1, "11:00")])
ok.submit()
check(ok.docstatus == 1, "6. Hard Block: a plan without clashes is submitted")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (Machine Double-Booking Mode is back to " + str(site_mode) + ").")
