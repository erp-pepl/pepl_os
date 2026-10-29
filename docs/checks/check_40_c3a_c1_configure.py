# PEPL OS v0.40.0 - Check 40: C3a-C1 Production configuration - the Production Settings sheet, OEE targets per factor
# (the Daily OEE names the factor below target), standard-time governance settings, the downtime category review and
# "Merge into", and one measure for slow / fast runs (the v0.39.0 slow-speed field is gone).
# Runs on 0.40.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes it makes, is undone at the end. Afterwards open the reports PEPL Production Settings and
# PEPL Downtime Category Review.
VERSION = "0.40.0"
PARAMS = "PEPL System Parameters"
SPR = "PEPL Shift Production Entry"
CATEGORY = "PEPL Downtime Category"
PATCH = "pepl_os.patches.v0_40.remove_spr_slow_speed_parameter"
MERGE = "pepl_os.pepl_production.config.merge_downtime_category"
NEW_FIELDS = ["custom_oee_availability_target_percent", "custom_oee_performance_target_percent", "custom_oee_quality_target_percent",
              "custom_std_time_lookback_days", "custom_std_time_min_runs", "custom_std_time_basis", "custom_std_time_max_change_percent",
              "custom_std_time_approver_role"]
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


def report(name, filters):
    result = frappe.call("frappe.desk.query_report.run", report_name=name, filters=filters)
    return [r for r in (result.get("result") or []) if isinstance(r, dict)]


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
yesterday = frappe.utils.add_days(today, -1)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def set_params(values):
    params = frappe.get_doc(PARAMS)
    for key in values:
        params.set(key, values[key])
    params.save()


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
meta = frappe.get_meta(PARAMS)
check(all(meta.get_field(f) for f in NEW_FIELDS), "1. System Parameters > Production has the 3 OEE factor targets and the 5 Standard Times (governance) settings")
check(not meta.get_field("custom_spr_slow_speed_percent") and bool(frappe.db.exists("Patch Log", {"patch": PATCH})), "1. the v0.39.0 field 'Shift Entry: Slow Below % of Standard Speed' was removed on this site (patch ran)")
check(bool(frappe.db.exists("Report", "PEPL Production Settings")) and bool(frappe.db.exists("Report", "PEPL Downtime Category Review")), "1. the reports PEPL Production Settings and PEPL Downtime Category Review exist")

# ---------------- 2. the settings sheet ----------------
sheet = report("PEPL Production Settings", {})
by_name = {}
for r in sheet:
    by_name[r.get("fieldname") or r.get("setting")] = r
changed = [r.get("setting") for r in sheet if str(r.get("status") or "").startswith("Changed")]
print("INFO  Production Settings: " + str(len(sheet)) + " settings; changed from default on this site: " + (", ".join(changed) if changed else "none"))
a = by_name.get("custom_oee_availability_target_percent") or {}
check(a.get("default") == "90" and bool(a.get("status")), "2. the sheet lists 'OEE: Availability Target %' with its default 90 and a status (" + str(a.get("value")) + ", " + str(a.get("status")) + ")")
check(all(k in by_name for k in ("skill_check_mode", "cycle_deviation_threshold_high", "disable_capacity_planning")), "2. it also lists Operator Skill Check Mode, the cycle deviation band and Manufacturing Settings capacity planning")
stored = [frappe.db.get_single_value(PARAMS, f) for f in ("custom_std_time_lookback_days", "custom_std_time_min_runs", "custom_std_time_basis", "custom_std_time_max_change_percent")]
print("INFO  this site: standard-time look-back " + str(stored[0]) + " days, minimum runs " + str(stored[1]) + ", from the " + str(stored[2]) + ", largest change " + str(stored[3]) + " %")
check(stored[0] is not None and stored[2] in ("Median", "Average"), "2. the standard-time governance settings are stored (defaults 90 days, 5 runs, Median, 20 %)")

# ---------------- 3. the settings are checked when saved ----------------
refused("3. an Availability target of 150 % is refused", lambda: set_params({"custom_oee_availability_target_percent": 150}), "Availability Target")
refused("3. a look-back of 3 days is refused (7 to 365)", lambda: set_params({"custom_std_time_lookback_days": 3}), "Look-back Days")
set_params({"custom_oee_availability_target_percent": 90, "custom_oee_performance_target_percent": 95, "custom_oee_quality_target_percent": 99,
            "custom_std_time_lookback_days": 90, "custom_spr_tool_photo_required": 0, "custom_spr_max_unaccounted_minutes": 15})

# ---------------- 4. the Daily OEE names the factor below target ----------------
DAY = "CHK40 Day " + RUN
MILL = "CHK40 MILL-01 " + RUN
OP = "CHK40-OP-" + RUN
NO_LOAD = "CHK40 No Load " + RUN
TWIN = "CHK40 No-load " + RUN
WAITING = "CHK40 Waiting " + RUN
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Check " + OP, "pin": pin}).insert()
for name, stop in ((NO_LOAD, "Planned"), (TWIN, "Planned"), (WAITING, "Unplanned")):
    frappe.get_doc({"doctype": CATEGORY, "category_name": name, "stop_type": stop, "is_breakdown": 0}).insert()
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.overproduction_percentage_for_work_order = 0
settings.save()
FG = frappe.get_doc({"doctype": "Item", "item_code": "CHK40-FG-" + RUN, "item_name": "CHK40 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert().name
BO = frappe.get_doc({"doctype": "Item", "item_code": "CHK40-BO-" + RUN, "item_name": "CHK40 Bought-out " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
MILLING = "CHK40 Milling " + RUN
frappe.get_doc({"doctype": "Operation", "name": MILLING, "workstation": MILL}).insert()
bom = frappe.get_doc({"doctype": "BOM", "item": FG, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
                      "currency": frappe.db.get_value("Company", company, "default_currency"), "items": [{"item_code": BO, "qty": 1, "rate": 10}],
                      "operations": [{"operation": MILLING, "workstation": MILL, "time_in_mins": 6}]}).insert()
bom.submit()
wo = frappe.get_doc({"doctype": "Work Order", "production_item": FG, "bom_no": bom.name, "qty": 40, "stock_uom": "Nos", "company": company,
                     "skip_transfer": 1, "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order"})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
card = frappe.get_all("Job Card", filters={"work_order": wo.name}, pluck="name")[0]
entry = frappe.get_doc({"doctype": SPR, "posting_date": yesterday, "shift": DAY, "workstation": MILL, "operator": OP, "company": company})
entry.append("production", {"job_card": card, "from_time": "08:00", "to_time": "12:00", "good_qty": 38, "rejected_qty": 2, "rejection_reason": "Undersize"})
entry.append("downtime", {"downtime_category": TWIN, "from_time": "12:00", "to_time": "16:00"})
entry.insert()
entry.submit()
print("INFO  shift entry " + entry.name + ": 40 pieces (38 good) x 6 min in 08:00-12:00, planned stop 12:00-16:00 (" + TWIN + ")")


def daily():
    rows = frappe.get_all("PEPL OEE Daily", filters={"workstation": MILL, "oee_date": yesterday}, fields=["oee", "availability", "performance", "quality", "factors_below_target"])
    if rows:
        print("INFO  Daily OEE: OEE " + str(rows[0].oee) + " = A " + str(rows[0].availability) + " x P " + str(rows[0].performance) + " x Q " + str(rows[0].quality) + "; below target: " + str(rows[0].factors_below_target or "none"))
    return rows[0] if rows else {}


d = daily()
check(d.get("availability") == 100 and d.get("performance") == 100 and d.get("quality") == 95, "4. Daily OEE: Availability 100 %, Performance 100 %, Quality 95 % (38 of 40 good)")
check(d.get("factors_below_target") == "Quality 95 % (target 99 %)", "4. the Daily OEE names the factor below target: 'Quality 95 % (target 99 %)'")
set_params({"custom_oee_quality_target_percent": 90})
frappe.call("pepl_os.pepl_production.oee.rebuild_oee", from_date=yesterday)
check(not daily().get("factors_below_target"), "4. with the Quality target at 90 % and the day rebuilt: no factor below target")

# ---------------- 5. downtime category review and merge ----------------
review = {r.get("category"): r for r in report("PEPL Downtime Category Review", {"days": 90})}
twin = review.get(TWIN) or {}
check("Looks like the same stop as " + NO_LOAD in str(twin.get("notes")) and twin.get("recent") == 1, "5. the review shows '" + TWIN + "' used once and 'Looks like the same stop as " + NO_LOAD + "'")
refused("5. merging a Planned stop into an Unplanned one is refused", lambda: frappe.call(MERGE, source=TWIN, target=WAITING), "same kind")
result = frappe.call(MERGE, source=TWIN, target=NO_LOAD)
print("INFO  merge: " + str(result.get("message")))
check(result.get("moved") == 1 and result.get("rebuilt_days") == 1, "5. merge " + TWIN + " into " + NO_LOAD + ": 1 shift-entry row moved, 1 Daily OEE rebuilt")
check(frappe.db.get_value("PEPL SPR Downtime", {"parent": entry.name}, "downtime_category") == NO_LOAD and not frappe.db.get_value(CATEGORY, TWIN, "is_active"), "5. the shift entry now says " + NO_LOAD + "; " + TWIN + " is switched off")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
