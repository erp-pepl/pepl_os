# PEPL OS v0.67.0 - Check 67: C3b-Q6 vendor scorecard - every incoming QC Inspection updates its supplier's quality score
# (lots Accepted / lots inspected in the Vendor Score Period), NCR count and composite score (delivery and quality
# weighted by the Vendor Score Weights); the daily job and "Run now" score every supplier.
# Runs on 0.67.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes it makes, is undone at the end. Afterwards look at the screens in the browser (see chat).
VERSION = "0.67.0"
PARAMS = "PEPL System Parameters"
QI = "Quality Inspection"
PR = "Purchase Receipt"
MOD = "pepl_os.pepl_quality.scorecard"
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
        check(words.lower() in text.lower(), label + " -> " + text[:220])


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def set_params(values):
    doc = frappe.get_doc(PARAMS)
    for field in values:
        doc.set(field, values[field])
    doc.save()


def scores(supplier):
    return frappe.db.get_value("Supplier", supplier, ["custom_quality_score", "custom_quality_scored_lots", "custom_supplier_ncrs",
                                                      "custom_composite_score", "custom_delivery_score", "custom_scores_updated_on"], as_dict=True)


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
smeta = frappe.get_meta("Supplier")
check(bool(smeta.get_field("custom_composite_score")) and bool(smeta.get_field("custom_quality_scored_lots")) and bool(smeta.get_field("custom_supplier_ncrs")),
      "1. the Supplier shows Quality Score, Lots Inspected, NCRs in the Period and Composite Score")
check(bool(frappe.get_meta("PEPL Quotation Comparison Row").get_field("composite_score")), "1. the Quotation Comparison has a Composite Score column")
check(MOD + ".daily_vendor_scores" in (frappe.get_hooks("scheduler_events").get("daily") or []),
      "1. the daily scoring job is scheduled; weights " + str(frappe.db.get_single_value(PARAMS, "custom_vendor_weight_delivery")) + " / "
      + str(frappe.db.get_single_value(PARAMS, "custom_vendor_weight_quality")))

# ---------------- 2. settings ----------------
set_params({"custom_vendor_weight_delivery": 50, "custom_vendor_weight_quality": 50, "custom_vendor_score_lookback_days": 365,
            "custom_incoming_qc_gate_mode": "Advisory"})
refused("2. weights 60 + 60 are refused", lambda: set_params({"custom_vendor_weight_delivery": 60, "custom_vendor_weight_quality": 60}), "add up to 100")

# ---------------- 3. four incoming lots ----------------
PARAM = "CHK67 Pin Diameter " + RUN
frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": PARAM}).insert()
PLAN = frappe.get_doc({"doctype": "Quality Inspection Template", "quality_inspection_template_name": "CHK67 Pin Plan " + RUN,
                       "item_quality_inspection_parameter": [{"specification": PARAM, "numeric": 1, "min_value": 9.9, "max_value": 10.1}]}).insert().name
values = {"doctype": "Item", "item_code": "CHK67-PIN-" + RUN, "item_name": "CHK67 Pin " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos",
          "is_stock_item": 1, "is_sales_item": 0, "is_purchase_item": 1, "valuation_rate": 10, "quality_inspection_template": PLAN}
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "7318%"]}, pluck="name", limit=20) if len(c) == 8]
    if codes:
        values["gst_hsn_code"] = codes[0]
PIN = frappe.get_doc(values).insert().name
frappe.db.set_value("Item", PIN, "inspection_required_before_purchase", 1)
SUPPLIER = frappe.get_doc({"doctype": "Supplier", "supplier_name": "CHK67 Pins " + RUN}).insert().name
frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")
STORE = frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": "Bought-Out Stores", "is_group": 0}, "name")


def lot(reading):
    pr = frappe.get_doc({"doctype": PR, "supplier": SUPPLIER, "company": company, "posting_date": today,
                         "items": [{"item_code": PIN, "qty": 10, "received_qty": 10, "rate": 10, "warehouse": STORE}]}).insert()
    qi = frappe.get_doc(QI, pr.items[0].quality_inspection)
    qi.readings[0].reading_1 = reading
    qi.save()
    qi.submit()
    return qi


lot("10.0")
s = scores(SUPPLIER)
check(s.custom_quality_score == 100 and s.custom_quality_scored_lots == 1 and s.custom_composite_score == 100,
      "3. first lot Accepted -> quality 100 %, 1 lot, composite 100 % (no delivery score yet) - updated at once")
bad = lot("10.4")
lot("10.05")
lot("9.95")
s = scores(SUPPLIER)
print("INFO  " + SUPPLIER + ": quality " + str(s.custom_quality_score) + " % of " + str(s.custom_quality_scored_lots) + " lots, NCRs "
      + str(s.custom_supplier_ncrs) + ", composite " + str(s.custom_composite_score) + " %, updated " + str(s.custom_scores_updated_on))
check(s.custom_quality_score == 75 and s.custom_quality_scored_lots == 4, "3. 3 of 4 lots Accepted -> quality 75 %")
check(s.custom_supplier_ncrs == 1, "3. the rejected lot raised 1 NCR, counted on the supplier")
check(s.custom_composite_score == 75, "3. composite 75 % (delivery not scored yet, so quality alone)")

# ---------------- 4. cancel, daily job, run now ----------------
bad.cancel()
s = scores(SUPPLIER)
check(s.custom_quality_score == 100 and s.custom_quality_scored_lots == 3, "4. cancelling the rejected lot -> 3 of 3 = 100 % at once")
frappe.db.set_value("Supplier", SUPPLIER, {"custom_quality_score": 0, "custom_quality_scored_lots": 0, "custom_composite_score": 0})
run = frappe.call(MOD + ".run_vendor_scores_now") or {}
s = scores(SUPPLIER)
check(run.get("records_touched", 0) >= 1 and s.custom_quality_scored_lots == 3 and s.custom_composite_score == 100,
      "4. 'Run now' of the daily job scored " + str(run.get("records_touched")) + " supplier(s) and restored 100 % / 3 lots")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
