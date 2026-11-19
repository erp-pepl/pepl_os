# PEPL OS v0.78.0 - Check 78: C3b-T1 end to end - incoming inspection -> NCR -> CAPA -> effectiveness verification
# -> closure, and the dispatch gate: two rejected incoming lots of a pin raise two Major NCRs and one CAPA (repeat
# Major); the CAPA is completed, waits for its effectiveness check and is verified; the NCRs are dispositioned, costed,
# signed and closed; a rejected final inspection holds a delivery until its NCR is closed and a new inspection passes;
# the Command Centre and the Cost of Quality follow.
# Runs on 0.78.0 or later. System Console, Type = Python. Everything below is undone at the end: the last lines roll
# back, even if "Commit" were ticked. The pop-ups after Execute are the refusals it provokes on purpose.
VERSION = "0.78.0"
PARAMS = "PEPL System Parameters"
QI = "Quality Inspection"
PR = "Purchase Receipt"
DN = "Delivery Note"
NCR = "PEPL NCR"
CAPA = "PEPL CAPA"
CC = "pepl_os.pepl_quality.command_centre."
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


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


# ---------------- 1. installed; the rules for this run ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
params = frappe.get_doc(PARAMS)
for field, value in [["custom_capa_verification_days", 90], ["custom_capa_whys_required", 1], ["custom_capa_repeat_count", 2],
                     ["custom_capa_repeat_window_days", 90], ["custom_ncr_auto_severity", "Major"], ["custom_dispatch_gate_mode", "Hard Block"],
                     ["dn_material_gate_mode", "Off"], ["custom_incoming_qc_gate_mode", "Advisory"]]:
    params.set(field, value)
params.save()
cards = {"open": frappe.call(CC + "open_ncrs_by_severity").get("total"), "coq": frappe.call(CC + "cost_of_quality_month").get("value")}

# ---------------- 2. a pin bought in, a shaft sold, their plans ----------------
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    hsn = codes[0] if codes else ""


def plan(code, low, high):
    param = "CHK78 " + code + " Diameter " + RUN
    frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": param}).insert()
    return frappe.get_doc({"doctype": "Quality Inspection Template", "quality_inspection_template_name": "CHK78 " + code + " Plan " + RUN,
                           "item_quality_inspection_parameter": [{"specification": param, "numeric": 1, "min_value": low, "max_value": high}]}).insert().name


def item(code, group, values):
    v = {"doctype": "Item", "item_code": "CHK78-" + code + "-" + RUN, "item_name": "CHK78 " + code + " " + RUN, "item_group": group, "stock_uom": "Nos",
         "is_stock_item": 1, "valuation_rate": 50}
    if hsn:
        v["gst_hsn_code"] = hsn
    v.update(values)
    return frappe.get_doc(v).insert().name


PIN = item("PIN", "Bought-Out Components", {"is_purchase_item": 1, "is_sales_item": 0, "quality_inspection_template": plan("PIN", 9.9, 10.1)})
frappe.db.set_value("Item", PIN, "inspection_required_before_purchase", 1)
SHAFT = item("SHAFT", "Finished Goods", {"is_sales_item": 1 if hsn else 0, "quality_inspection_template": plan("SHAFT", 19.9, 20.1)})
frappe.db.set_value("Item", SHAFT, "inspection_required_before_delivery", 1)
SUPPLIER = frappe.get_doc({"doctype": "Supplier", "supplier_name": "CHK78 Pins " + RUN}).insert().name
check(bool(PIN) and bool(SHAFT), "2. " + PIN + " (inspected on receipt) and " + SHAFT + " (inspected before delivery) with their plans")

# ---------------- 3. two rejected incoming lots -> two Major NCRs -> one CAPA ----------------


def rejected_lot(reading):
    pr = frappe.get_doc({"doctype": PR, "supplier": SUPPLIER, "company": company, "posting_date": today,
                         "items": [{"item_code": PIN, "qty": 10, "received_qty": 10, "rate": 10, "warehouse": wh("Bought-Out Stores")}]}).insert()
    qi = frappe.get_doc(QI, pr.items[0].quality_inspection)
    qi.readings[0].reading_1 = reading
    qi.save()
    qi.submit()
    return frappe.db.get_value(NCR, {"quality_inspection": qi.name}, "name")


N1 = rejected_lot("10.4")
N2 = rejected_lot("9.6")
check(bool(N1) and bool(N2) and frappe.db.get_value(NCR, N1, "severity") == "Major" and frappe.db.get_value(NCR, N1, "supplier") == SUPPLIER,
      "3. two rejected incoming lots raised Major NCRs " + str(N1) + " and " + str(N2) + " against the supplier")
CAPA_NAME = frappe.db.get_value(NCR, N2, "capa")
check(bool(CAPA_NAME) and frappe.db.get_value(NCR, N1, "capa") == CAPA_NAME and frappe.db.get_value(CAPA, CAPA_NAME, "trigger") == "Repeat Major",
      "3. the second Major NCR raised one CAPA (Repeat Major) " + str(CAPA_NAME) + " for both")
check(frappe.call(CC + "open_ncrs_by_severity").get("total") == cards["open"] + 2, "3. Command Centre: open NCRs + 2")

# ---------------- 4. CAPA: five-why, action, Closed -> Awaiting Verification -> Effective ----------------
doc = frappe.get_doc(CAPA, CAPA_NAME)
doc.containment = "Both lots held at stores and returned"
doc.why_1 = "Supplier's grinding wheel worn"
doc.root_cause = "Supplier has no wheel-change interval"
doc.append("actions", {"action_type": "Corrective Action", "description": "Supplier adds wheel change every 500 pieces", "done_on": today})
doc.status = "Closed"
doc.save()
doc = frappe.get_doc(CAPA, CAPA_NAME)
check(doc.status == "Awaiting Verification" and str(doc.verification_due_on) == frappe.utils.add_days(today, 90), "4. Closed -> Awaiting Verification, check due in 90 days")
refused("4. Effective before the check day is refused", lambda: frappe.call("pepl_os.pepl_quality.capa.verify_capa", capa=CAPA_NAME, result="Effective", remarks="Next three lots accepted"), "due on")
frappe.db.set_value(CAPA, CAPA_NAME, "verification_due_on", frappe.utils.add_days(today, -1))
check(frappe.call(CC + "capas_overdue_for_verification").get("value") >= 1, "4. Command Centre: CAPAs Overdue for Verification counts it")
frappe.call("pepl_os.pepl_quality.capa.verify_capa", capa=CAPA_NAME, result="Effective", remarks="Next three lots accepted")
check(frappe.db.get_value(CAPA, CAPA_NAME, "status") == "Closed" and frappe.db.get_value(CAPA, CAPA_NAME, "verification_result") == "Effective",
      "4. verified Effective -> CAPA Closed")

# ---------------- 5. the NCRs: disposition, cost, sign-off, closed ----------------


def close_ncr(name, disposition, cost):
    n = frappe.get_doc(NCR, name)
    n.disposition = disposition
    n.estimated_cost = cost
    n.save()
    frappe.call("pepl_os.pepl_quality.ncr.sign_off", ncr=name, remarks="CHK78")
    n = frappe.get_doc(NCR, name)
    n.status = "Closed"
    n.save()
    return frappe.db.get_value(NCR, name, "status")




def close_unsigned():
    n = frappe.get_doc(NCR, N1)
    n.disposition = "Return to Supplier"
    n.status = "Closed"
    n.save()


refused("5. an NCR cannot close before its sign-offs", close_unsigned, "still needs the sign-off")
check(close_ncr(N1, "Return to Supplier", 100) == "Closed" and close_ncr(N2, "Return to Supplier", 100) == "Closed",
      "5. both NCRs: Return to Supplier, cost 100 each, signed, Closed")

# ---------------- 6. the dispatch gate: a rejected final inspection holds the shafts ----------------
receipt = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
                          "items": [{"item_code": SHAFT, "qty": 10, "t_warehouse": wh("FG Stores"), "basic_rate": 50}]}).insert()
receipt.submit()
groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
customer = frappe.get_doc({"doctype": "Customer", "customer_name": "CHK78 Customer " + RUN, "customer_type": "Company",
                           "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert().name


def delivery(qty, reading):
    dn = frappe.get_doc({"doctype": DN, "customer": customer, "company": company, "posting_date": today,
                         "items": [{"item_code": SHAFT, "qty": qty, "rate": 100, "warehouse": wh("FG Stores")}]}).insert()
    qi = frappe.get_doc(QI, dn.items[0].quality_inspection)
    qi.readings[0].reading_1 = reading
    qi.save()
    qi.submit()
    return [dn.name, qi.name]


BAD = delivery(5, "20.6")
N3 = frappe.db.get_value(NCR, {"quality_inspection": BAD[1]}, "name")
check(bool(N3) and frappe.db.get_value(NCR, N3, "source") == "Dispatch", "6. final inspection 20.6 Rejected -> NCR " + str(N3) + " (Dispatch)")
refused("6. the rejected shafts cannot go", lambda: frappe.get_doc(DN, BAD[0]).submit(), "is Rejected")
GOOD = delivery(5, "20.0")
refused("6. good shafts are held while the shaft's NCR is open", lambda: frappe.get_doc(DN, GOOD[0]).submit(), "open NCR " + str(N3))
check(close_ncr(N3, "Rework", 50) == "Closed", "6. NCR " + str(N3) + ": Rework, cost 50, signed, Closed")
dn = frappe.get_doc(DN, GOOD[0])
dn.submit()
check(dn.docstatus == 1, "6. now the accepted shafts go: " + dn.name)

# ---------------- 7. the cards follow ----------------
check(frappe.call(CC + "open_ncrs_by_severity").get("total") == cards["open"], "7. Command Centre: open NCRs back to where they were")
check(abs(frappe.call(CC + "cost_of_quality_month").get("value") - cards["coq"] - 250) < 0.01, "7. Cost of Quality (month) + 250 (2 x 100 returned + 50 rework)")

frappe.db.rollback()
print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Everything above was rolled back: nothing was saved.")
