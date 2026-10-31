# PEPL OS v0.45.0 - Check 45: C3a-B4 Bottleneck report - how long work waits in front of each machine group between
# Job Order operations (this operation's start - the previous operation's finish, from the Job Card time logs),
# overlaps, work waiting now, red above the Wait Warning Hours.
# Runs on 0.45.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the
# end. Then open the report in the browser: see the steps in the chat.
VERSION = "0.45.0"
PARAMS = "PEPL System Parameters"
REPORT = "PEPL Bottleneck"
WARNING = "custom_bottleneck_wait_warning_hours"
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
    except Exception as e:
        text = frappe.utils.strip_html(str(e))
        check(words.lower() in text.lower(), label + " -> " + text[:200])


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


def run_report(filters):
    return frappe.call("frappe.desk.query_report.run", report_name=REPORT, filters=filters)


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
DAY = frappe.utils.add_days(today, -2)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def at(clock):
    return frappe.utils.get_datetime(DAY + " " + clock + ":00")


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(frappe.db.get_value("Report", REPORT, "report_type") == "Script Report" and bool(frappe.get_all("Workspace Link", filters={"parent": "Production Command Centre", "link_to": REPORT})),
      "1. report '" + REPORT + "' exists and is listed on the Production Command Centre")
check(bool(frappe.get_meta(PARAMS).get_field(WARNING)), "1. System Parameters > Production > Bottleneck: Wait Warning Hours (this site: " + str(frappe.db.get_single_value(PARAMS, WARNING)) + ")")
params = frappe.get_doc(PARAMS)
params.set(WARNING, 8)
params.save()
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.save()

# ---------------- 2. a Job Order with three operations on three machine groups ----------------
MILLS = "CHK45 MILL " + RUN
LATHES = "CHK45 LATHE " + RUN
GRINDERS = "CHK45 GRIND " + RUN
ops = [["CHK45 Milling " + RUN, "CHK45 MILL-01 " + RUN, MILLS], ["CHK45 Turning " + RUN, "CHK45 LATHE-01 " + RUN, LATHES], ["CHK45 Grinding " + RUN, "CHK45 GRIND-01 " + RUN, GRINDERS]]
for row in ops:
    frappe.get_doc({"doctype": "Workstation Type", "workstation_type": row[2]}).insert()
    frappe.get_doc({"doctype": "Workstation", "workstation_name": row[1], "workstation_type": row[2]}).insert()
    frappe.get_doc({"doctype": "Operation", "name": row[0], "workstation": row[1]}).insert()
FG = frappe.get_doc({"doctype": "Item", "item_code": "CHK45-FG-" + RUN, "item_name": "CHK45 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert().name
BO = frappe.get_doc({"doctype": "Item", "item_code": "CHK45-BO-" + RUN, "item_name": "CHK45 Bought-out " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
bom = frappe.get_doc({"doctype": "BOM", "item": FG, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
                      "currency": frappe.db.get_value("Company", company, "default_currency"), "items": [{"item_code": BO, "qty": 1, "rate": 10}],
                      "operations": [{"operation": r[0], "workstation": r[1], "time_in_mins": 6} for r in ops]}).insert()
bom.submit()
wo = frappe.get_doc({"doctype": "Work Order", "production_item": FG, "bom_no": bom.name, "qty": 10, "stock_uom": "Nos", "company": company, "skip_transfer": 1,
                     "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.add_days(frappe.utils.now(), -3), "transfer_material_against": "Work Order"})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
cards = {}
for c in frappe.get_all("Job Card", filters={"work_order": wo.name}, fields=["name", "operation"]):
    cards[c.operation] = c.name
check(len(cards) == 3, "2. Job Order " + wo.name + " has 3 Job Cards: milling, turning, grinding (" + ", ".join(sorted(cards.values())) + ")")


def log(card, start, end, qty):
    frappe.get_doc({"doctype": "Job Card Time Log", "parent": card, "parenttype": "Job Card", "parentfield": "time_logs", "from_time": start, "to_time": end,
                    "completed_qty": qty, "time_in_mins": (end - start).total_seconds() / 60}).db_insert()


# the shift entries' blocks, as they land on the Job Cards (written directly here: the report only reads them)
log(cards[ops[0][0]], at("08:00"), at("10:00"), 6)
log(cards[ops[0][0]], at("10:00"), at("12:00"), 4)  # milling 10 of 10: finished 12:00
log(cards[ops[1][0]], at("22:00"), at("23:00"), 10)  # turning started 22:00: waited 10 h; finished 23:00
print("INFO  " + DAY + ": milling 08:00-12:00 (10 of 10), turning 22:00-23:00 (10 of 10), grinding not started")

# ---------------- 3. the report ----------------
filters = {"job_order": wo.name, "from_date": frappe.utils.add_days(today, -7), "to_date": today}
out = run_report(filters)
groups = out.get("result") or []
lathe = [g for g in groups if g.get("workstation_type") == LATHES]
grind = [g for g in groups if g.get("workstation_type") == GRINDERS]
for g in groups:
    print("INFO  " + str(g.get("rank")) + ". " + str(g.get("workstation_type")) + ": waits " + str(g.get("waits")) + ", average " + str(g.get("average_hours")) + " h, waiting now "
          + str(g.get("waiting_now")) + " (oldest " + str(g.get("oldest_waiting_hours")) + " h), run " + str(g.get("run_hours")) + " h")
check(bool(lathe) and lathe[0].get("waits") == 1 and lathe[0].get("average_hours") == 10, "3. turning waited 10 h after milling finished (12:00 -> 22:00)")
check(bool(lathe) and lathe[0].get("colour") == "red" and lathe[0].get("bottleneck") == 1 and lathe[0].get("rank") == 1, "3. " + LATHES + " is the bottleneck, red (10 h above the 8 h warning)")
check(bool(lathe) and lathe[0].get("run_hours") == 1, "3. run hours on " + LATHES + ": 1")
check(bool(grind) and grind[0].get("waiting_now") == 1 and grind[0].get("oldest_waiting_hours") > 24 and grind[0].get("colour") == "orange",
      "3. grinding is waiting now since 23:00 on " + DAY + " (" + str(grind[0].get("oldest_waiting_hours") if grind else "-") + " h), orange")
check(not [g for g in groups if g.get("workstation_type") == MILLS], "3. milling (the first operation) has no wait")
check("Bottleneck: " + LATHES in str(out.get("message")), "3. the line above the report -> " + str(out.get("message"))[:200])
out = run_report(dict(filters, show="Operations"))
rows = out.get("result") or []
states = [str(r.get("operation")) + ": " + str(r.get("state_text")) + " " + str(r.get("hours")) + " h" for r in rows]
print("INFO  operations: " + "; ".join(states))
check(len(rows) == 2 and "Waiting now" in [r.get("state_text") for r in rows] and "Waited" in [r.get("state_text") for r in rows], "3. 'Show: Operations' lists turning (waited) and grinding (waiting now)")

# ---------------- 4. an overlap, and the setting ----------------
log(cards[ops[2][0]], at("22:30"), at("23:30"), 4)  # grinding started 22:30, before turning finished 23:00
out = run_report(dict(filters, show="Operations"))
grinding = [r for r in out.get("result") or [] if r.get("operation") == ops[2][0]]
check(bool(grinding) and grinding[0].get("state_text") == "Overlapped" and grinding[0].get("hours") == 0, "4. grinding started before turning finished: 'Overlapped', no wait")
params = frappe.get_doc(PARAMS)
params.set(WARNING, 12)
params.save()
out = run_report(filters)
lathe = [g for g in out.get("result") or [] if g.get("workstation_type") == LATHES]
check(bool(lathe) and lathe[0].get("colour") != "red", "4. with Wait Warning Hours = 12 the 10 h wait is no longer red")


def bad_warning():
    p = frappe.get_doc(PARAMS)
    p.set(WARNING, 0)
    p.save()


refused("4. Wait Warning Hours of 0 is refused", bad_warning, "Bottleneck: Wait Warning Hours")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
