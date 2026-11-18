# PEPL OS v0.72.0 - Check 72: C3b-C1 Quality configuration - the report PEPL Quality Settings (every Quality setting
# with its value, default and status; the Quality Notification Owner; the sign-off matrix in practice - who holds each
# role; Stock Settings for QC; items and instruments the rules need) and the warning when a sign-off role is held by
# nobody (an orange pop-up after Execute).
# Runs on 0.72.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters change it makes, is undone at the end. The first INFO lines are this site's Quality Settings sheet.
# Afterwards open the report PEPL Quality Settings (see chat).
VERSION = "0.72.0"
PARAMS = "PEPL System Parameters"
REPORT = "PEPL Quality Settings"
FIELDS = ["custom_incoming_qc_stock_classes", "custom_incoming_qc_gate_mode", "custom_calibration_alert_days", "custom_calibration_gate_mode",
          "custom_ncr_signoff_minor", "custom_ncr_signoff_major", "custom_ncr_signoff_critical", "custom_ncr_auto_severity",
          "custom_ncr_on_customer_return", "custom_ncr_rejection_rate_percent", "custom_ncr_rejection_min_pieces", "custom_capa_repeat_count",
          "custom_capa_repeat_window_days", "custom_capa_whys_required", "custom_capa_target_days", "custom_dispatch_gate_mode",
          "custom_vendor_weight_delivery", "custom_vendor_weight_quality"]
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


def sheet(show):
    result = frappe.call("frappe.desk.query_report.run", report_name=REPORT, filters={})
    rows = [r for r in (result.get("result") or []) if isinstance(r, dict)]
    if show:
        for r in rows:
            print("INFO  sheet: " + str(r.get("area")) + " | " + str(r.get("setting")) + " = " + str(r.get("value")) + " | "
                  + str(r.get("status")) + " [" + str(r.get("colour")) + "]")
    return rows


def find(rows, key):
    for r in rows:
        if r.get("fieldname") == key or r.get("setting") == key:
            return r
    return {}


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.db.exists("Report", REPORT)), "1. the report PEPL Quality Settings exists")

# ---------------- 2. this site's sheet ----------------
rows = sheet(True)
check(all(find(rows, f) for f in FIELDS), "2. all 18 Quality settings are on the sheet")
check(bool(find(rows, "custom_quality_notification_owner")) and bool(find(rows, "custom_vendor_score_lookback_days")), "2. Quality Notification Owner and Vendor Score Period are on the sheet")
check(bool(find(rows, "action_if_quality_inspection_is_not_submitted")) and bool(find(rows, "action_if_quality_inspection_is_rejected")), "2. both Stock Settings QC actions are on the sheet")
check(bool(find(rows, "inspection_required_before_purchase")) and bool(find(rows, "inspection_required_before_delivery")) and bool(find(rows, "Instruments (not scrapped)")),
      "2. items inspected on receipt / before delivery and instruments are on the sheet")
check(len([r for r in rows if str(r.get("setting")).endswith(" NCRs") and r.get("area") == "Sign-off matrix in practice"]) >= 1, "2. the sign-off matrix in practice: one row per role")
check(all(r.get("colour") in ("green", "orange", "red") for r in rows), "2. every row has a colour (green / orange / red)")

# ---------------- 3. a changed setting; a sign-off role nobody holds ----------------
ROLE = "CHK72 Approver " + RUN
frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert()
params = frappe.get_doc(PARAMS)
critical = params.get("custom_ncr_signoff_critical") or "Quality Manager\nManufacturing Manager\nPEPL CEO"
params.set("custom_capa_target_days", 45)
params.set("custom_ncr_signoff_critical", critical + "\n" + ROLE)
params.save()  # an orange pop-up "NCR sign-off: no user holds the role ..." appears after Execute: the save went on
check(ROLE in (frappe.db.get_single_value(PARAMS, "custom_ncr_signoff_critical") or ""), "3. the matrix with a role nobody holds is saved (with a warning)")
rows = sheet(False)
row = find(rows, "custom_capa_target_days")
check(row.get("value") == "45" and row.get("default") == "30" and row.get("status") == "Changed from default" and row.get("colour") == "green",
      "3. CAPA: Target Days 45 -> 'Changed from default' (green), default 30")
row = find(rows, ROLE + " signs Critical NCRs")
check(row.get("value") == "nobody" and row.get("status") == "No user holds this role: Critical NCRs can never be closed" and row.get("colour") == "red",
      "3. '" + ROLE + " signs Critical NCRs': nobody - 'Critical NCRs can never be closed' (red)")
USER = "chk72." + RUN + "@example.com"
user = frappe.get_doc({"doctype": "User", "email": USER, "first_name": "CHK72", "send_welcome_email": 0, "user_type": "System User"}).insert()
user.add_roles(ROLE)
row = find(sheet(False), ROLE + " signs Critical NCRs")
check(row.get("value") == "1 user(s): " + USER and row.get("status") == "Ready" and row.get("colour") == "green", "3. a user given the role -> '1 user(s): ...', Ready (green)")

# ---------------- 4. an inspected item without a plan, an instrument never calibrated ----------------
item = frappe.get_doc({"doctype": "Item", "item_code": "CHK72-BARE-" + RUN, "item_name": "CHK72 Bare " + RUN, "item_group": "Bought-Out Components",
                       "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "is_purchase_item": 1, "valuation_rate": 10}).insert().name
frappe.db.set_value("Item", item, {"inspection_required_before_purchase": 1, "quality_inspection_template": None})
frappe.get_doc({"doctype": "PEPL Instrument", "instrument_id": "CHK72-GAUGE-" + RUN, "instrument_name": "CHK72 gauge", "calibration_frequency_days": 30}).insert()
rows = sheet(False)
row = find(rows, "inspection_required_before_purchase")
check(" without an inspection plan" in str(row.get("status")) and row.get("colour") == "orange", "4. items inspected on receipt: '... without an inspection plan' (orange)")
row = find(rows, "Instruments (not scrapped)")
check(" overdue or never calibrated" in str(row.get("status")) and row.get("colour") == "orange", "4. instruments: '... overdue or never calibrated' (orange)")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
