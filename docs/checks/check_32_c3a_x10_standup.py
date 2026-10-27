# PEPL OS v0.32.0 - Check 32 rev 2: C3a-X10 the Daily Stand-up - yesterday's shop floor, top stops, machines without a
# shift entry, Job Orders at delivery risk, job work overdue; built for a day and e-mailed to the Standup Email Group.
# Runs on 0.32.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes this check makes, is undone at the end.
VERSION = "0.32.0"
PARAMS = "PEPL System Parameters"
STANDUP = "PEPL Daily Standup"
SPR = "PEPL Shift Production Entry"
BUILD = "pepl_os.pepl_production.standup.build_standup_now"
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
yesterday = frappe.utils.add_days(today, -1)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
print("INFO  company " + company + "; stand-up for " + str(yesterday))


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.db.exists("DocType", STANDUP)), "1. the Daily Stand-up record (PEPL Daily Standup) exists")
check(bool(frappe.get_meta(PARAMS).get_field("custom_standup_risk_days")) and bool(frappe.get_meta(PARAMS).get_field("standup_email_group")), "1. System Parameters has 'Stand-up: Days Ahead for Delivery Risk' and 'Standup Email Group'")
site_group = frappe.db.get_single_value(PARAMS, "standup_email_group")
outgoing = frappe.get_all("Email Account", filters={"enable_outgoing": 1}, pluck="name")
print("INFO  this site: Standup Email Group = " + str(site_group) + "; outgoing Email Account: " + (", ".join(outgoing) if outgoing else "none (Frappe may still queue mail when the site's e-mails are muted or set in site_config)"))

# ---------------- 2. a shop floor for yesterday ----------------
# Machines without a machine group: the skill check says "Not checked" and never blocks, whatever this site's mode.
# Test items are not sales items, so India Compliance does not ask them for an HSN/SAC code.
GROUP = "CHK32 Stand-up " + RUN
frappe.get_doc({"doctype": "Email Group", "title": GROUP}).insert()
frappe.get_doc({"doctype": "Email Group Member", "email_group": GROUP, "email": "chk32-foreman-" + RUN + "@example.com"}).insert()
params = frappe.get_doc(PARAMS)
params.standup_email_group = GROUP
params.custom_standup_risk_days = 3
params.custom_spr_tool_photo_required = 0
params.save()
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.overproduction_percentage_for_work_order = 0
settings.save()

DAY = "CHK32 Day " + RUN
MILL = "CHK32 MILL-01 " + RUN
LATHE = "CHK32 LATHE-02 " + RUN
OP = "CHK32-OP-" + RUN
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": LATHE}).insert()
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Check " + OP, "pin": pin}).insert()
NO_LOAD = "CHK32 No Load " + RUN
SPINDLE = "CHK32 Spindle " + RUN
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": SPINDLE, "stop_type": "Unplanned", "is_breakdown": 1}).insert()
fg = frappe.get_doc({"doctype": "Item", "item_code": "CHK32-FG-" + RUN, "item_name": "CHK32 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert().name
rm = frappe.get_doc({"doctype": "Item", "item_code": "CHK32-BO-" + RUN, "item_name": "CHK32 Bought-out " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
MILLING = "CHK32 Milling " + RUN
frappe.get_doc({"doctype": "Operation", "name": MILLING, "workstation": MILL}).insert()
bom = frappe.get_doc({
    "doctype": "BOM", "item": fg, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
    "currency": frappe.db.get_value("Company", company, "default_currency"),
    "items": [{"item_code": rm, "qty": 1, "rate": 10}],
    "operations": [{"operation": MILLING, "workstation": MILL, "time_in_mins": 6}],
}).insert()
bom.submit()


def job_order(qty, start_days_ago, due):
    wo = frappe.get_doc({
        "doctype": "Work Order", "production_item": fg, "bom_no": bom.name, "qty": qty, "stock_uom": "Nos", "company": company,
        "skip_transfer": 1, "fg_warehouse": wh("FG Stores"), "planned_start_date": str(frappe.utils.add_days(today, -start_days_ago)) + " 08:00:00",
        "expected_delivery_date": due, "transfer_material_against": "Work Order",
    })
    wo.get_items_and_operations_from_bom()
    wo.insert()
    wo.submit()
    return wo


soon = job_order(10, 2, frappe.utils.add_days(today, 2))
late = job_order(5, 3, yesterday)
far = job_order(5, 1, frappe.utils.add_days(today, 20))
card = frappe.get_all("Job Card", filters={"work_order": soon.name}, pluck="name")[0]
print("INFO  Job Orders " + soon.name + " (due in 2 days), " + late.name + " (due yesterday), " + far.name + " (due in 20 days)")


def entry(machine, day, production=None, downtime=None):
    doc = frappe.get_doc({"doctype": SPR, "posting_date": day, "shift": DAY, "workstation": machine, "operator": OP, "company": company})
    for row in production or []:
        doc.append("production", row)
    for row in downtime or []:
        doc.append("downtime", row)
    doc.insert()
    doc.submit()
    return doc


def down(category, start, end):
    return {"downtime_category": category, "from_time": start, "to_time": end}


entry(MILL, yesterday,
      production=[{"job_card": card, "from_time": "08:00", "to_time": "12:00", "good_qty": 8, "rejected_qty": 2, "rejection_reason": "Undersize"}],
      downtime=[down(SPINDLE, "12:00", "13:00"), down(NO_LOAD, "13:00", "16:00")])
entry(LATHE, frappe.utils.add_days(today, -5), downtime=[down(NO_LOAD, "08:00", "16:00")])
print("INFO  yesterday on " + MILL + ": 4 h run (8 good, 2 rejected), 1 h spindle breakdown, 3 h no load; " + LATHE + " worked 5 days ago only")

# ---------------- 3. the stand-up for yesterday ----------------
result = frappe.call(BUILD, day=yesterday)
doc = frappe.get_doc(STANDUP, result.get("name"))
page = doc.summary or ""
check(str(doc.standup_date) == str(yesterday), "3. stand-up " + doc.name + " built for " + str(yesterday))
check(MILL in page and doc.machines_reported >= 1, "3. section 1 shows the mill's Daily OEE (" + str(doc.machines_reported) + " machine(s) reported)")
check(doc.good_qty >= 8 and doc.rejected_qty >= 2 and doc.breakdowns >= 1, "3. headline: good " + str(doc.good_qty) + ", rejected " + str(doc.rejected_qty) + ", breakdowns " + str(doc.breakdowns))
check(NO_LOAD in page and SPINDLE in page, "3. section 2 lists the stops (no load 180 min, spindle 60 min)")
check(LATHE in page and MILL not in (page.split("3. Machines without a shift entry")[1].split("4. ")[0] if "3. Machines without a shift entry" in page else ""), "3. section 3: the lathe has no shift entry yesterday, the mill has")
risk = page.split("4. Job Orders at delivery risk")[1].split("5. ")[0] if "4. Job Orders at delivery risk" in page else ""
check(soon.name in risk and late.name in risk and far.name not in risk, "3. section 4: due in 2 days and due yesterday are at risk; due in 20 days is not")
check("overdue" in risk.split(late.name)[1][:80] if late.name in risk else False, "3. section 4: " + late.name + " is marked overdue")
check(doc.job_orders_overdue >= 1 and doc.job_orders_at_risk >= 2, "3. headline: " + str(doc.job_orders_at_risk) + " Job Orders at risk, " + str(doc.job_orders_overdue) + " overdue")

# ---------------- 4. e-mailed to the Standup Email Group ----------------
# Whether the mail is queued depends on the site's e-mail set-up, not on PEPL OS: with an outgoing account (or muted
# e-mails / a mail server in site_config) Frappe queues it; with none at all PEPL OS records "Not e-mailed".
result = frappe.call(BUILD, day=yesterday, email=1)
emailed = frappe.db.get_value(STANDUP, result.get("name"), "emailed_to") or ""
queued = frappe.get_all("Email Queue", filters={"reference_doctype": STANDUP, "reference_name": result.get("name")}, fields=["name", "status"])
if queued:
    to = frappe.get_all("Email Queue Recipient", filters={"parent": queued[0].name}, pluck="recipient")
    print("INFO  Email Queue " + queued[0].name + " (" + str(queued[0].status) + ") to " + ", ".join(to))
    check(("chk32-foreman-" + RUN + "@example.com") in to and ("chk32-foreman-" + RUN) in emailed, "4. queued for the group's member and recorded on the stand-up (" + emailed + ")")
else:
    check("Not e-mailed" in emailed, "4. nothing could be queued on this site: the record says '" + emailed + "' and nothing breaks")

# ---------------- 5. building again updates the same day ----------------
check(result.get("name") == doc.name and frappe.db.count(STANDUP, {"standup_date": yesterday}) == 1, "5. building again updated " + doc.name + " (one stand-up per day)")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (Standup Email Group is back to " + str(site_group) + ").")
