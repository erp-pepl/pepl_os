# PEPL OS v0.36.0 - Check 36: C3a-P2 the Production Plan machine load - each machine's booked hours (this plan +
# already booked) against its available hours (working hours x jobs at once x working days), with colours.
# Runs on 0.36.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters change it makes, is undone at the end. After the check, open any Production Plan to see the panel.
VERSION = "0.36.0"
PARAMS = "PEPL System Parameters"
WARNING = "custom_load_warning_percent"
PANEL = "pepl_os.pepl_production.load_view.get_production_plan_load"
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
DAY = frappe.utils.add_days(frappe.utils.today(), 40)
NEXT = frappe.utils.add_days(DAY, 1)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
print("INFO  company " + company + "; plans are for " + str(DAY))


def at(hhmm, day=None):
    return str(day or DAY) + " " + hhmm + ":00"


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def set_warning(value):
    params = frappe.get_doc(PARAMS)
    params.set(WARNING, value)
    params.custom_double_booking_mode = "Advisory"
    params.save()


def panel(name):
    rows = frappe.call(PANEL, production_plan=name)["rows"]
    print("INFO  machine load of " + name + ": " + " | ".join(r["text"] + " [" + r["colour"] + "]" for r in rows))
    return rows


def line(rows, machine):
    found = [r for r in rows if r["text"].startswith(machine + ",")]
    return found[0] if found else {"text": "", "colour": ""}


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.get_meta(PARAMS).get_field(WARNING)), "1. System Parameters has Production > 'Load View: Warning at % of Machine Hours'")
site_warning = frappe.db.get_single_value(PARAMS, WARNING)
print("INFO  this site: warning at " + str(site_warning) + " %")
check(site_warning not in (None, "") and 0 < frappe.utils.flt(site_warning) <= 100, "1. the warning share on this site is set (default 85)")

set_warning(85)
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.mins_between_operations = 0
settings.save()

# ---------------- 2. machines, items and BOMs for this run ----------------
# Each machine gets an empty Holiday List of its own, so this site's company holidays (weekly offs) never change
# the day count. Test items are not sales items (no HSN needed).
none = frappe.get_doc({"doctype": "Holiday List", "holiday_list_name": "CHK36 No Holidays " + RUN, "from_date": frappe.utils.add_days(DAY, -30), "to_date": frappe.utils.add_days(DAY, 30)}).insert().name
EIGHT = [{"start_time": "08:00:00", "end_time": "16:00:00"}]
M1 = "CHK36 LATHE-01 " + RUN
M2 = "CHK36 VMC-02 " + RUN
M3 = "CHK36 DRILL-03 " + RUN
frappe.get_doc({"doctype": "Workstation", "workstation_name": M1, "production_capacity": 1, "working_hours": EIGHT, "holiday_list": none}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": M2, "production_capacity": 2, "working_hours": EIGHT, "holiday_list": none}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": M3, "production_capacity": 1, "holiday_list": none}).insert()
check(frappe.utils.flt(frappe.db.get_value("Workstation", M1, "total_working_hours")) == 8, "2. " + M1 + " works 08:00-16:00 = 8 h a day (ERPNext Working Hours)")
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": "CHK36 Day " + RUN, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()


def item(code, group, rate=0):
    values = {"doctype": "Item", "item_code": code + "-" + RUN, "item_name": code + " " + RUN, "item_group": group, "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}
    if rate:
        values["valuation_rate"] = rate
    return frappe.get_doc(values).insert().name


ROD = item("CHK36-RM-ROD", "Raw Material", 10)
currency = frappe.db.get_value("Company", company, "default_currency")


def product(code, machine, minutes):
    name = item(code, "Finished Goods")
    values = {"doctype": "BOM", "item": name, "company": company, "quantity": 1, "is_active": 1, "is_default": 1,
              "currency": currency, "items": [{"item_code": ROD, "qty": 1, "rate": 10}]}
    if machine:
        operation = code + " Op " + RUN
        frappe.get_doc({"doctype": "Operation", "name": operation, "workstation": machine}).insert()
        values["with_operations"] = 1
        values["operations"] = [{"operation": operation, "workstation": machine, "time_in_mins": minutes}]
    bom = frappe.get_doc(values).insert()
    bom.submit()
    return name


SHAFT = product("CHK36-SHAFT", M1, 60)
BUSH = product("CHK36-BUSH", M2, 60)
COLLAR = product("CHK36-COLLAR", M3, 60)
PLAIN = product("CHK36-PLAIN", None, 0)
print("INFO  60 min a piece: " + SHAFT + " on " + M1 + ", " + BUSH + " on " + M2 + " (2 jobs at once), " + COLLAR + " on " + M3 + " (no working hours)")


def plan(rows, submit=False):
    doc = frappe.get_doc({
        "doctype": "Production Plan", "company": company, "posting_date": frappe.utils.today(),
        "po_items": [{
            "item_code": code, "bom_no": frappe.db.get_value("BOM", {"item": code, "is_default": 1, "docstatus": 1}),
            "planned_qty": qty, "planned_start_date": start, "stock_uom": "Nos", "warehouse": wh("FG Stores"),
        } for code, qty, start in rows],
    }).insert()
    if submit:
        doc.submit()
    return doc


def job_order(code, qty, start):
    wo = frappe.get_doc({
        "doctype": "Work Order", "production_item": code, "bom_no": frappe.db.get_value("BOM", {"item": code, "is_default": 1, "docstatus": 1}),
        "qty": qty, "stock_uom": "Nos", "company": company, "skip_transfer": 1, "fg_warehouse": wh("FG Stores"),
        "planned_start_date": start, "transfer_material_against": "Work Order",
    })
    wo.get_items_and_operations_from_bom()
    wo.insert()
    wo.submit()
    return wo.name


# ---------------- 3. this plan against the machine's hours ----------------
rows = panel(plan([(SHAFT, 2, at("09:00"))]).name)
check("this plan 2 h of 8 h" in line(rows, M1)["text"] and "25%" in line(rows, M1)["text"], "3. shaft x 2 on " + M1 + ": 'this plan 2 h of 8 h' - 25%")
check(line(rows, M1)["colour"] == "green" and rows[0]["colour"] == "green", "3. below 85 %: green")

# ---------------- 4. what is already booked on those days ----------------
held = job_order(SHAFT, 4, at("11:00"))
later = job_order(SHAFT, 3, at("09:00", frappe.utils.add_days(DAY, 5)))
print("INFO  open Job Orders on " + M1 + ": " + held + " 4 h on " + str(DAY) + ", " + later + " 3 h five days later")
b = plan([(SHAFT, 2, at("09:00"))])
rows = panel(b.name)
check("this plan 2 h + already booked 4 h = 6 h of 8 h" in line(rows, M1)["text"] and "75%" in line(rows, M1)["text"], "4. the Job Order on the same day counts, the one five days later does not: 6 h of 8 h - 75%")
check(line(rows, M1)["colour"] == "green", "4. 75 % is below the 85 % warning: still green")
other = plan([(SHAFT, 1, at("15:00"))], submit=True)
rows = panel(b.name)
check("already booked 5 h = 7 h of 8 h" in line(rows, M1)["text"] and "88%" in line(rows, M1)["text"], "4. submitted plan " + other.name + " (1 h on the same day) counts as already booked too: 7 h of 8 h - 88%")
check(line(rows, M1)["colour"] == "orange" and rows[0]["colour"] == "orange", "4. 88 % is at or above the 85 % warning: orange")
set_warning(90)
check(line(panel(b.name), M1)["colour"] == "green", "4. with the warning raised to 90 % in System Parameters: the same 88 % shows green")
set_warning(85)

# ---------------- 5. overloaded ----------------
rows = panel(plan([(SHAFT, 10, at("06:00"))]).name)
check(rows[0]["colour"] == "red" and "overloaded" in rows[0]["text"], "5. shaft x 10 on top: the headline says overloaded, in red")
check(line(rows, M1)["colour"] == "red" and "188%" in line(rows, M1)["text"], "5. " + M1 + ": 10 h + 5 h = 15 h of 8 h - 188% in red")

# ---------------- 6. days, holidays and machines that run two jobs ----------------
long_plan = plan([(SHAFT, 20, at("09:00"))]).name  # 09:00 today to 05:00 the next day
check("2 working day(s)" in line(panel(long_plan), M1)["text"], "6. a plan running past midnight gets both days: 16 h available")
holidays = frappe.get_doc({"doctype": "Holiday List", "holiday_list_name": "CHK36 Holidays " + RUN, "from_date": frappe.utils.add_days(DAY, -30), "to_date": frappe.utils.add_days(DAY, 30),
                           "holidays": [{"holiday_date": NEXT, "description": "CHK36 holiday"}]}).insert().name
frappe.db.set_value("Workstation", M1, "holiday_list", holidays)
check("1 working day(s)" in line(panel(long_plan), M1)["text"], "6. with the next day a holiday on the machine's Holiday List: 1 working day, 8 h available")
frappe.db.set_value("Workstation", M1, "holiday_list", none)
rows = panel(plan([(BUSH, 4, at("09:00"))]).name)
check("4 h of 16 h" in line(rows, M2)["text"] and "2 jobs at once" in line(rows, M2)["text"], "6. bush x 4 on " + M2 + " (2 jobs at once): 4 h of 16 h - 25%")

# ---------------- 7. no working hours of its own: the active shifts ----------------
minutes = sum(frappe.utils.cint(m) for m in frappe.get_all("PEPL Shift", filters={"is_active": 1}, pluck="planned_minutes"))
print("INFO  active shifts on this site: " + str(minutes) + " planned minutes a day")
rows = panel(plan([(COLLAR, 3, at("09:00"))]).name)
check("from the active shifts" in line(rows, M3)["text"], "7. " + M3 + " has no Working Hours: its hours a day come from the active shifts")

# ---------------- 8. no machine time, double-bookings ----------------
rows = panel(plan([(PLAIN, 5, at("09:00"))]).name)
check(len(rows) == 1 and "No machine time" in rows[0]["text"], "8. a plan whose BOM has no operations: 'No machine time in this plan yet'")
rows = panel(plan([(SHAFT, 1, at("06:00", NEXT)), (SHAFT, 1, at("06:30", NEXT))]).name)
check(any("double-booked" in r["text"] and r["colour"] == "red" for r in rows), "8. two rows on " + M1 + " at the same time: the load points to Machine Double-Bookings")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (the warning is back to " + str(site_warning) + " %).")
