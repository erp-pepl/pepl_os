# PEPL OS v0.71.0 - Check 71: C3b-P4 the instrument panel - fit to measure today (days left / overdue), the last
# calibration and the history (fails), where the instrument was used, draft QC Inspections the Calibration Gate would
# stop, and the next step.
# Runs on 0.71.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the end.
# Afterwards look at an instrument in the browser (see chat).
VERSION = "0.71.0"
QI = "Quality Inspection"
PR = "Purchase Receipt"
INSTRUMENT = "PEPL Instrument"
RECORD = "PEPL Calibration Record"
PANEL = "pepl_os.pepl_quality.instrument_panel.get_instrument_panel"
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
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
ALERT = int(frappe.db.get_single_value("PEPL System Parameters", "custom_calibration_alert_days") or 15)
GATE = frappe.db.get_single_value("PEPL System Parameters", "custom_calibration_gate_mode") or "Hard Block"
print("INFO  Calibration: Alert Days = " + str(ALERT) + ", Calibration Gate = " + GATE)

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")


def gauge(code, frequency):
    return frappe.get_doc({"doctype": INSTRUMENT, "instrument_id": "CHK71-" + code + "-" + RUN, "instrument_name": "CHK71 " + code,
                           "instrument_type": "Vernier Caliper", "calibration_frequency_days": frequency, "measuring_range": "0-150 mm",
                           "least_count": "0.02 mm", "location": "QC room"}).insert().name


def record(name, days_ago, result):
    values = {"doctype": RECORD, "instrument": name, "calibration_date": frappe.utils.add_days(today, -days_ago), "result": result,
              "agency": "CHK71 Labs"}
    if result == "Fail":
        values["errors_found"] = "jaw worn 0.05 mm"
    else:
        values["certificate_no"] = "CHK71-" + str(days_ago)
    rec = frappe.get_doc(values).insert()
    rec.submit()
    return rec.name


def show(name):
    rows = frappe.call(PANEL, name=name) or []
    for r in rows:
        print("INFO  panel: " + r.get("text") + " [" + r.get("colour") + "]")
    return rows


def find(rows, start):
    for r in rows:
        if r.get("text").startswith(start):
            return r
    return {"text": "", "colour": ""}


# ---------------- 2. never calibrated ----------------
NEW = gauge("NEW", 365)
rows = show(NEW)
check(rows[0].get("text") == NEW + ": CHK71 NEW (Vernier Caliper) · Active · range 0-150 mm, least count 0.02 mm · at QC room", "2. header: id, name, type, status, range, least count, location")
check(rows[1].get("text") == NEW + " has never been calibrated · every 365 days" and rows[1].get("colour") == "red", "2. 'has never been calibrated · every 365 days' (red)")
check(rows[2].get("text") == "No calibration record yet", "2. 'No calibration record yet'")
check(rows[-1].get("text").startswith("Next: stop using it, calibrate it") and rows[-1].get("colour") == "red", "2. 'Next: stop using it, calibrate it ...' (red)")

# ---------------- 3. calibrated 10 days ago, every 365 days ----------------
OK = gauge("OK", 365)
REC = record(OK, 10, "Pass")
rows = show(OK)
check(rows[1].get("text").endswith(" (355 day(s) left) · every 365 days") and rows[1].get("colour") == "green", "3. '(355 day(s) left)' (green)")
check(rows[2].get("text").endswith(": Pass · certificate CHK71-10 · by CHK71 Labs (" + REC + ")") and rows[2].get("colour") == "green", "3. last calibration: Pass, certificate, agency, record")
check(rows[3].get("text") == "Calibration records: 1 (Pass 1)", "3. 'Calibration records: 1 (Pass 1)'")
check(not find(rows, "Next").get("text"), "3. nothing to do: no 'Next' line")

# ---------------- 4. due soon ----------------
if ALERT >= 5:
    SOON = gauge("SOON", 15)
    record(SOON, 10, "Pass")
    rows = show(SOON)
    check(" is due for calibration on " in rows[1].get("text") and "(5 day(s) left)" in rows[1].get("text") and rows[1].get("colour") == "orange",
          "4. due in 5 days: 'is due for calibration on ... (5 day(s) left)' (orange)")
    check(rows[-1].get("text").startswith("Next: book the calibration before "), "4. 'Next: book the calibration before ...'")
else:
    print("INFO  4. skipped: Alert Days is below 5 on this site")

# ---------------- 5. overdue ----------------
LATE = gauge("LATE", 30)
record(LATE, 40, "Pass")
rows = show(LATE)
check(" is overdue for calibration (due " in rows[1].get("text") and " - 10 day(s) overdue" in rows[1].get("text") and rows[1].get("colour") == "red",
      "5. 'overdue for calibration (due ...) - 10 day(s) overdue' (red)")

# ---------------- 6. a failed calibration ----------------
FAIL = gauge("FAIL", 365)
record(FAIL, 40, "Pass")
record(FAIL, 5, "Fail")
rows = show(FAIL)
check(" · Out of Service · " in rows[0].get("text") and "is not in use (Out of Service)" in rows[1].get("text") and rows[1].get("colour") == "red",
      "6. the Fail took it Out of Service (red)")
check(rows[3].get("text").startswith("Calibration records: 2 (Pass 1, Fail 1) · last Fail ") and rows[3].get("text").endswith(": jaw worn 0.05 mm"),
      "6. 'Calibration records: 2 (Pass 1, Fail 1) · last Fail ...: jaw worn 0.05 mm'")
check(rows[-1].get("text") == "Next: repair it, then submit a passed Calibration Record to bring it back to Active", "6. 'Next: repair it ...'")

# ---------------- 7. use in QC Inspections ----------------
DIA = "CHK71 Diameter " + RUN
frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": DIA}).insert()
PLAN = frappe.get_doc({"doctype": "Quality Inspection Template", "quality_inspection_template_name": "CHK71 Plan " + RUN,
                       "item_quality_inspection_parameter": [{"specification": DIA, "numeric": 1, "min_value": 9.9, "max_value": 10.1}]}).insert().name
values = {"doctype": "Item", "item_code": "CHK71-PIN-" + RUN, "item_name": "CHK71 Pin " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos",
          "is_stock_item": 1, "is_sales_item": 0, "is_purchase_item": 1, "valuation_rate": 10, "quality_inspection_template": PLAN}
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "7318%"]}, pluck="name", limit=20) if len(c) == 8]
    if codes:
        values["gst_hsn_code"] = codes[0]
PIN = frappe.get_doc(values).insert().name
frappe.db.set_value("Item", PIN, "inspection_required_before_purchase", 1)
SUPPLIER = frappe.get_doc({"doctype": "Supplier", "supplier_name": "CHK71 Pins " + RUN}).insert().name
STORE = frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": "Bought-Out Stores", "is_group": 0}, "name")


def inspection(instrument):
    pr = frappe.get_doc({"doctype": PR, "supplier": SUPPLIER, "company": company, "posting_date": today,
                         "items": [{"item_code": PIN, "qty": 10, "received_qty": 10, "rate": 10, "warehouse": STORE}]}).insert()
    qi = frappe.get_doc(QI, pr.items[0].quality_inspection)
    qi.readings[0].reading_1 = "10"
    qi.readings[0].custom_instrument = instrument
    qi.save()
    return qi


qi = inspection(OK)
row = find(show(OK), "1 draft")
check(row.get("text") == "1 draft QC Inspection(s) name this instrument (" + qi.name + ")" and row.get("colour") == "gray", "7. a draft with a calibrated gauge: listed, grey")
qi.submit()
rows = show(OK)
check(find(rows, "Used in").get("text").startswith("Used in 1 submitted QC Inspection(s) in the last 90 days · last " + qi.name + " (" + PIN + ") on ")
      and not find(rows, "1 draft").get("text"), "7. after submit: 'Used in 1 submitted QC Inspection(s) ... last ...'")
draft = inspection(LATE)
row = find(show(LATE), "1 draft")
check(row.get("text").startswith("1 draft QC Inspection(s) name this instrument (" + draft.name + ") - the Calibration Gate (" + GATE + ") ")
      and row.get("colour") == ("red" if GATE == "Hard Block" else "orange"), "7. a draft with the overdue gauge: what the Calibration Gate (" + GATE + ") will do")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
