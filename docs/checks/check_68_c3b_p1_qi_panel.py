# PEPL OS v0.68.0 - Check 68: C3b-P1 the QC Inspection panel - one line per characteristic with its tolerance, the
# readings typed, in tolerance or OUT (which values), the instrument used and its calibration inline, and the result
# the inspection will have on submit.
# Runs on 0.68.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the end.
# Afterwards look at a QC Inspection in the browser (see chat).
VERSION = "0.68.0"
QI = "Quality Inspection"
PR = "Purchase Receipt"
INSTRUMENT = "PEPL Instrument"
RECORD = "PEPL Calibration Record"
PANEL = "pepl_os.pepl_quality.qi_panel.get_inspection_panel"
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

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")

# ---------------- 2. a pin with a two-line plan, two gauges ----------------
DIA = "CHK68 Diameter " + RUN
FIN = "CHK68 Finish " + RUN
frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": DIA}).insert()
frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": FIN}).insert()
PLAN = frappe.get_doc({"doctype": "Quality Inspection Template", "quality_inspection_template_name": "CHK68 Plan " + RUN,
                       "item_quality_inspection_parameter": [{"specification": DIA, "numeric": 1, "min_value": 9.9, "max_value": 10.1},
                                                             {"specification": FIN, "numeric": 0, "value": "Smooth"}]}).insert().name
values = {"doctype": "Item", "item_code": "CHK68-PIN-" + RUN, "item_name": "CHK68 Pin " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos",
          "is_stock_item": 1, "is_sales_item": 0, "is_purchase_item": 1, "valuation_rate": 10, "quality_inspection_template": PLAN}
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "7318%"]}, pluck="name", limit=20) if len(c) == 8]
    if codes:
        values["gst_hsn_code"] = codes[0]
PIN = frappe.get_doc(values).insert().name
frappe.db.set_value("Item", PIN, "inspection_required_before_purchase", 1)
SUPPLIER = frappe.get_doc({"doctype": "Supplier", "supplier_name": "CHK68 Pins " + RUN}).insert().name
STORE = frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": "Bought-Out Stores", "is_group": 0}, "name")


def gauge(code, days_ago):
    name = frappe.get_doc({"doctype": INSTRUMENT, "instrument_id": code + "-" + RUN, "instrument_name": code, "calibration_frequency_days": 30}).insert().name
    rec = frappe.get_doc({"doctype": RECORD, "instrument": name, "calibration_date": frappe.utils.add_days(today, -days_ago), "result": "Pass",
                          "certificate_no": "CHK68-" + code}).insert()
    rec.submit()
    return name


GOOD = gauge("CHK68-VC", 1)
LATE = gauge("CHK68-DIAL", 40)


def inspection():
    pr = frappe.get_doc({"doctype": PR, "supplier": SUPPLIER, "company": company, "posting_date": today,
                         "items": [{"item_code": PIN, "qty": 10, "received_qty": 10, "rate": 10, "warehouse": STORE}]}).insert()
    return frappe.get_doc(QI, pr.items[0].quality_inspection)


def show(name):
    rows = frappe.call(PANEL, name=name) or []
    for r in rows:
        print("INFO  panel: " + r.get("text") + " [" + r.get("colour") + "]")
    return rows


# ---------------- 3. nothing measured ----------------
qi = inspection()
rows = show(qi.name)
check(len(rows) >= 4 and rows[1].get("text") == DIA + " 9.9 - 10.1: not measured yet · no instrument named" and rows[1].get("colour") == "orange",
      "3. each characteristic shows its tolerance and 'not measured yet'")
check(rows[3].get("text") == "2 characteristic(s) still to measure", "3. '2 characteristic(s) still to measure'")

# ---------------- 4. measured in tolerance with a calibrated gauge ----------------
qi.readings[0].reading_1 = "10"
qi.readings[0].reading_2 = "10.05"
qi.readings[0].custom_instrument = GOOD
qi.readings[1].reading_value = "Smooth"
qi.save()
rows = show(qi.name)
check(rows[1].get("colour") == "green" and (DIA + " 9.9 - 10.1: 10, 10.05 (2 readings) - in tolerance · " + GOOD + " is calibrated until") in rows[1].get("text"),
      "4. 10 and 10.05 in 9.9 - 10.1, gauge " + GOOD + " calibrated -> green")
check(rows[2].get("text") == FIN + " expected Smooth: Smooth - Accepted · no instrument named", "4. the finish is judged Smooth = Accepted")
check(rows[3].get("text") == "Result on submit: Accepted", "4. 'Result on submit: Accepted'")

# ---------------- 5. a value out, an overdue gauge ----------------
qi2 = inspection()
qi2.readings[0].reading_1 = "10.0"
qi2.readings[0].reading_2 = "10.2"
qi2.readings[0].custom_instrument = LATE
qi2.readings[1].reading_value = "Smooth"
qi2.save()
rows = show(qi2.name)
check(rows[1].get("colour") == "red" and "10, 10.2 (2 readings) - OUT: 10.2" in rows[1].get("text") and (LATE + " is overdue for calibration") in rows[1].get("text"),
      "5. 10.2 shown as OUT, gauge " + LATE + " shown overdue, line red (no '10.0')")
check(rows[3].get("text") == "Result on submit: Rejected", "5. 'Result on submit: Rejected'")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
