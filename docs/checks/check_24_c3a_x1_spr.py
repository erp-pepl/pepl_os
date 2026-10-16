# PEPL OS v0.24.0 - Check 24 (rev 3): C3a-X1 Shift Production Entry - times, overlaps, submit rules, Job Card time logs,
# consumables issue, cancel, permissions. Runs on 0.24.0 or later.
# System Console, Type = Python. Leave "Commit" UNTICKED: every record below (machines, items, BOM, Job Order,
# Job Card, stock, entries) is undone at the end. Every name carries this run's time, so runs never clash.
VERSION = "0.24.0"
SPR = "PEPL Shift Production Entry"
PANEL = "pepl_os.pepl_production.spr.get_spr_panel"
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
        check(words.lower() in text.lower(), label + " -> " + text[:220])
        return text


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
yesterday = frappe.utils.add_days(today, -1)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
print("INFO  company " + company)


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
for dt in (SPR, "PEPL SPR Production", "PEPL SPR Downtime", "PEPL SPR Tool Change", "PEPL SPR Consumable"):
    check(frappe.db.exists("DocType", dt), "1. DocType " + dt + " exists")
check(frappe.get_meta(SPR).is_submittable and frappe.get_meta(SPR).track_changes, "1. the entry is submittable and every change is tracked")
check(bool(frappe.get_meta("Job Card Time Log").get_field("custom_pepl_spr")), "1. Job Card time logs can carry the Shift Production Entry")
check(bool(frappe.get_meta("Stock Entry").get_field("custom_shift_production_entry")), "1. Stock Entry can carry the Shift Production Entry")
grace = int(frappe.db.get_single_value("PEPL System Parameters", "custom_spr_shift_grace_minutes") or 0)
limit = int(frappe.db.get_single_value("PEPL System Parameters", "custom_spr_max_unaccounted_minutes") or 0)
photo_rule = int(frappe.db.get_single_value("PEPL System Parameters", "custom_spr_tool_photo_required") or 0)
print("INFO  System Parameters: grace " + str(grace) + " min, unexplained allowed " + str(limit) + " min, tool photo required " + str(photo_rule))
check(0 <= grace <= 120 and limit >= 0, "1. Production rules have valid values")

# ---------------- masters for this run ----------------
DAY = "CHK24 Day " + RUN
NIGHT = "CHK24 Night " + RUN
VMC_TYPE = "CHK24 VMC " + RUN
VMC = "CHK24 VMC-01 " + RUN
LATHE = "CHK24 LATHE-01 " + RUN
OP1 = "CHK24-A-" + RUN
OP2 = "CHK24-B-" + RUN
NO_LOAD = "CHK24 No Load " + RUN
SPINDLE = "CHK24 Spindle " + RUN
pin = "1" * int(frappe.db.get_single_value("PEPL System Parameters", "custom_operator_pin_digits") or 4)

frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": NIGHT, "start_time": "22:00:00", "end_time": "06:00:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "Workstation Type", "workstation_type": VMC_TYPE}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": VMC, "workstation_type": VMC_TYPE}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": LATHE}).insert()
# Both operators are fully skilled on the VMC group, so the skill check (X7, any mode) never interferes here.
for code in (OP1, OP2):
    frappe.get_doc({"doctype": "PEPL Operator", "employee_code": code, "operator_name": "Check " + code, "pin": pin,
                    "skills": [{"workstation_type": VMC_TYPE, "level": "4 - Sets up and trains others"}]}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": SPINDLE, "stop_type": "Unplanned", "is_breakdown": 1}).insert()


def entry(machine, shift, operator, day, production=None, downtime=None, tools=None, consumables=None):
    doc = frappe.get_doc({"doctype": SPR, "posting_date": day, "shift": shift, "workstation": machine, "operator": operator, "company": company})
    for table, rows in (("production", production), ("downtime", downtime), ("tool_changes", tools), ("consumables", consumables)):
        for row in rows or []:
            doc.append(table, row)
    return doc


def down(category, start, end):
    return {"downtime_category": category, "from_time": start, "to_time": end}


# ---------------- 2. times, overlaps, one entry per machine / shift / day / operator ----------------
first = entry(VMC, DAY, OP1, yesterday, downtime=[down(NO_LOAD, "08:00", "12:00"), down(SPINDLE, "12:00", "12:45")]).insert()
check(first.downtime[0].minutes == 240 and first.planned_minutes == 480, "2. 08:00-12:00 = 240 minutes; day shift has 480 planned minutes")
check(first.downtime[1].stop_type == "Unplanned" and first.downtime[1].is_breakdown == 1, "2. the breakdown row carries 'Unplanned' and Breakdown from its category")
check(first.unaccounted_minutes == 480 - 285, "2. minutes not explained = 480 - 285 = " + str(first.unaccounted_minutes))
night = entry(VMC, NIGHT, OP1, yesterday, downtime=[down(NO_LOAD, "23:00", "01:30")]).insert()
check(str(night.downtime[0].to_datetime)[:10] == today and night.downtime[0].minutes == 150, "2. night shift 23:00-01:30: 150 minutes, the 01:30 is on the next day")
refused("2. a row outside the shift is refused", lambda: entry(LATHE, DAY, OP1, yesterday, downtime=[down(NO_LOAD, "18:00", "19:00")]).insert(), "outside the shift")
refused("2. To before From is refused", lambda: entry(LATHE, DAY, OP1, yesterday, downtime=[down(NO_LOAD, "11:00", "10:00")]).insert(), "after from")
refused("2. two rows of one entry cannot overlap", lambda: entry(LATHE, DAY, OP1, yesterday, downtime=[down(NO_LOAD, "08:00", "10:00"), down(SPINDLE, "09:30", "10:30")]).insert(), "overlaps")
refused("2. another operator's entry on the same machine cannot overlap", lambda: entry(VMC, DAY, OP2, yesterday, downtime=[down(NO_LOAD, "11:00", "13:00")]).insert(), "same machine")
refused("2. a second entry for the same machine, shift, day and operator is refused", lambda: entry(VMC, DAY, OP1, yesterday, downtime=[down(NO_LOAD, "15:00", "15:30")]).insert(), "already has an entry")
refused("2. a future shift date is refused", lambda: entry(LATHE, DAY, OP2, frappe.utils.add_days(today, 1), downtime=[down(NO_LOAD, "08:00", "09:00")]).insert(), "future")

# ---------------- 3. submit rules ----------------
refused("3. submit refused while " + str(first.unaccounted_minutes) + " minutes are not explained", lambda: first.submit(), "not explained")
first.reload()
tool = {"change_time": "10:00", "tool_description": "CNMG insert", "reason": "Worn out"}
second = entry(LATHE, DAY, OP2, yesterday, downtime=[down(NO_LOAD, "08:00", "16:00")], tools=[tool]).insert()
if photo_rule:
    refused("3. submit refused while a tool change has no photo", lambda: second.submit(), "photo")
    second.reload()
    second.tool_changes[0].photo = "/assets/frappe/images/frappe-favicon.svg"
    second.save()
else:
    print("INFO  tool photo rule is off on this site; photo check skipped")
second.submit()
check(second.docstatus == 1, "3. an entry with every minute explained (and the photo) is submitted")
panel = frappe.call(PANEL, name=first.name)["rows"]
print("INFO  panel: " + " | ".join(r["text"] for r in panel))
check(any("not explained" in r["text"] and r["colour"] == "red" for r in panel), "3. panel shows the unexplained minutes in red")
check(any("breakdown" in r["text"] and r["colour"] == "red" for r in panel), "3. panel shows the breakdown stop")

# ---------------- 4. Job Card: a real Job Order on its own machine ----------------
# Test items are not sales items, so India Compliance does not ask them for an HSN/SAC code.
MILL = "CHK24 MILL-01 " + RUN
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.overproduction_percentage_for_work_order = 0
settings.save()
fg = frappe.get_doc({"doctype": "Item", "item_code": "CHK24-FG-" + RUN, "item_name": "CHK24 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert()
rm = frappe.get_doc({"doctype": "Item", "item_code": "CHK24-RM-" + RUN, "item_name": "CHK24 RM " + RUN, "item_group": "Raw Material", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert()
frappe.get_doc({"doctype": "Operation", "name": "CHK24 Milling " + RUN, "workstation": MILL}).insert()
bom = frappe.get_doc({
    "doctype": "BOM", "item": fg.name, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
    "currency": frappe.db.get_value("Company", company, "default_currency"),
    "items": [{"item_code": rm.name, "qty": 1, "rate": 10}],
    "operations": [{"operation": "CHK24 Milling " + RUN, "workstation": MILL, "time_in_mins": 6}],
}).insert()
bom.submit()
wo = frappe.get_doc({
    "doctype": "Work Order", "production_item": fg.name, "bom_no": bom.name, "qty": 10, "stock_uom": "Nos", "company": company,
    "skip_transfer": 1, "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order",
})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
card_name = frappe.get_all("Job Card", filters={"work_order": wo.name}, pluck="name")[0]
print("INFO  Job Order " + wo.name + " -> Job Card " + card_name + " on " + MILL)


def block(start, end, good, rejected=0, reason=None):
    row = {"job_card": card_name, "from_time": start, "to_time": end, "good_qty": good}
    if rejected:
        row["rejected_qty"] = rejected
        row["rejection_reason"] = reason or ""
    return row


refused("4. a Job Card of another machine is refused", lambda: entry(LATHE, NIGHT, OP1, yesterday, production=[block("22:00", "23:00", 1)]).insert(), "is for machine")
refused("4. a rejection without a reason is refused", lambda: entry(MILL, DAY, OP2, yesterday, production=[block("08:00", "09:00", 1, 1)]).insert(), "reason")
refused("4. more good quantity than the Job Card is for is refused", lambda: entry(MILL, DAY, OP2, yesterday, production=[block("08:00", "09:00", 11)]).insert(), "more than")
job = entry(
    MILL, DAY, OP2, yesterday,
    production=[block("08:00", "11:00", 4, 1, "Undersize bore"), block("11:00", "14:00", 3)],
    downtime=[down(NO_LOAD, "14:00", "16:00")],
).insert()
check(job.production[0].work_order == wo.name and job.production[0].production_item == fg.name, "4. the row takes Job Order and item from the Job Card")
check(job.total_good_qty == 7 and job.total_rejected_qty == 1 and abs(job.rejection_percent - 12.5) < 0.01, "4. good 7, rejected 1, rejection 12.5%")
check(job.production_minutes == 360 and job.downtime_minutes == 120 and job.unaccounted_minutes == 0, "4. 360 production + 120 downtime: every minute explained")
job.submit()
card = frappe.get_doc("Job Card", card_name)
mine = [t for t in card.time_logs if t.custom_pepl_spr == job.name]
check(len(mine) == 2 and sum(t.completed_qty for t in mine) == 7, "4. submit added 2 time logs with 7 good to the Job Card")
check(card.total_completed_qty == 7 and round(card.total_time_in_mins) == 360, "4. Job Card shows 7 completed and 360 minutes")
check(str(mine[0].from_time)[:16] == str(yesterday) + " 08:00", "4. the first time log starts " + str(yesterday) + " 08:00")
refused("4. another entry adding 4 more (7 + 4 > 10) is refused", lambda: entry(MILL, NIGHT, OP1, yesterday, production=[block("22:00", "23:00", 4)]).insert(), "more than")
job.cancel()
card.reload()
check(len([t for t in card.time_logs if t.custom_pepl_spr == job.name]) == 0 and card.total_completed_qty == 0, "4. cancel took the time logs back off the Job Card")

# ---------------- 5. consumables ----------------
oil = frappe.get_doc({"doctype": "Item", "item_code": "CHK24-COOLANT-" + RUN, "item_name": "CHK24 Coolant " + RUN, "item_group": "Consumables", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert()
receipt = frappe.get_doc({
    "doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
    "set_posting_time": 1, "posting_date": frappe.utils.add_days(today, -5),
    "items": [{"item_code": oil.name, "qty": 50, "t_warehouse": wh("Consumables Stores"), "basic_rate": 10}],
}).insert()
receipt.submit()
refused(
    "5. a raw material item is refused as a consumable",
    lambda: entry(LATHE, NIGHT, OP2, yesterday, downtime=[down(NO_LOAD, "22:00", "06:00")], consumables=[{"item_code": rm.name, "qty": 1}]).insert(),
    "not a Consumables",
)
used = entry(LATHE, NIGHT, OP2, yesterday, downtime=[down(NO_LOAD, "22:00", "06:00")], consumables=[{"item_code": oil.name, "qty": 4}]).insert()
check(used.consumables[0].warehouse == wh("Consumables Stores"), "5. the consumable is issued from Consumables Stores")
used.submit()
se = frappe.get_doc("Stock Entry", used.consumables_stock_entry)
check(se.docstatus == 1 and se.purpose == "Material Issue" and se.custom_shift_production_entry == used.name, "5. submit made a submitted Material Issue " + se.name + " linked to the entry")
check(se.items[0].qty == 4 and se.items[0].custom_machine_group == LATHE, "5. the issue carries 4 and the machine (no group on this machine, so its name)")
check(str(se.posting_date) == str(yesterday), "5. the issue is dated on the shift date")
used.cancel()
check(frappe.db.get_value("Stock Entry", se.name, "docstatus") == 2, "5. cancel cancelled the Material Issue")

# ---------------- 6. who may do what (read live from this site's permissions) ----------------
def rights(profile):
    out = frappe.call("frappe.desk.query_report.run", report_name="PEPL Role Access Matrix", filters={"area": "Production", "role_profile": profile})
    return {r["doctype"]: r for r in (out.get("result") or []) if isinstance(r, dict) and r.get("doctype")}

fo = rights("PEPL Foreman").get(SPR, {})
mo = rights("PEPL Production Manager").get(SPR, {})
check(fo.get("create") == "Yes" and fo.get("submit") == "Yes" and not fo.get("cancel"), "6. Foreman creates and submits entries but cannot cancel them")
check(mo.get("cancel") == "Yes" and mo.get("amend") == "Yes", "6. Production Manager also cancels and amends")
check(not fo.get("delete") and not mo.get("delete"), "6. neither can delete an entry (System Manager only)")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
