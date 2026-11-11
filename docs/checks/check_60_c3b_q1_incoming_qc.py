# PEPL OS v0.60.0 - Check 60: C3b-Q1 incoming QC Inspection with the Purchase Receipt - items of the stock classes
# in "Incoming QC: Stock Classes" are inspected on receipt; saving a receipt makes one draft QC Inspection per such
# line (with the item's inspection plan); an item without a plan gives Quality a ToDo; the incoming QC gate
# (Advisory / Soft Block / Hard Block) stops a receipt until its inspections are submitted and accepted.
# Runs on 0.60.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes it makes, is undone at the end. Afterwards look at a receipt in the browser (see chat).
VERSION = "0.60.0"
PARAMS = "PEPL System Parameters"
QI = "Quality Inspection"
PR = "Purchase Receipt"
QC = "pepl_os.pepl_quality.incoming_qc"
GATE_RULE = "QA-IN-QC"
PLAN_RULE = "QA-NO-QC-PLAN"
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


def set_params(values):
    doc = frappe.get_doc(PARAMS)
    for field in values:
        doc.set(field, values[field])
    doc.save()


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
pmeta = frappe.get_meta(PARAMS)
check(bool(pmeta.get_field("custom_incoming_qc_stock_classes")) and bool(pmeta.get_field("custom_incoming_qc_gate_mode")),
      "1. System Parameters > Quality: Incoming QC: Stock Classes ("
      + str(frappe.db.get_single_value(PARAMS, "custom_incoming_qc_stock_classes") or "empty").replace("\n", ", ")
      + ") and Incoming QC Gate (" + str(frappe.db.get_single_value(PARAMS, "custom_incoming_qc_gate_mode")) + ")")
qmeta = frappe.get_meta(QI)
check(bool(qmeta.get_field("custom_auto_created")) and bool(qmeta.get_field("custom_supplier")), "1. QC Inspection has 'Created with the Receipt' and 'Supplier'")
s1 = frappe.db.get_single_value("Stock Settings", "action_if_quality_inspection_is_not_submitted")
s2 = frappe.db.get_single_value("Stock Settings", "action_if_quality_inspection_is_rejected")
check(s1 == "Warn" and s2 == "Warn", "1. Stock Settings: not submitted -> " + str(s1) + ", rejected -> " + str(s2) + " (PEPL's gate decides)")

# ---------------- 2. settings for this run ----------------
values = {"custom_incoming_qc_stock_classes": "Bought-Out Components", "custom_incoming_qc_gate_mode": "Soft Block",
          "enable_operational_todos": 1, "custom_enforce_override_reason": 1}
if not frappe.db.get_single_value(PARAMS, "custom_quality_notification_owner"):
    values["custom_quality_notification_owner"] = "Administrator"
set_params(values)
OWNER = frappe.db.get_single_value(PARAMS, "custom_quality_notification_owner")
refused("2. an unknown stock class is refused", lambda: set_params({"custom_incoming_qc_stock_classes": "Bought-Out Components\nGold Bars"}), "Gold Bars")

hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "7318%"]}, pluck="name", limit=20) if len(c) == 8]
    codes = codes or [c for c in frappe.get_all("GST HSN Code", pluck="name", limit=200) if len(c) == 8]
    hsn = codes[0] if codes else ""


def item(code, group):
    values = {"doctype": "Item", "item_code": code + "-" + RUN, "item_name": code + " " + RUN, "item_group": group, "stock_uom": "Nos",
              "is_stock_item": 1, "is_sales_item": 0, "is_purchase_item": 1, "valuation_rate": 10}
    if hsn:
        values["gst_hsn_code"] = hsn
    return frappe.get_doc(values).insert().name


PARAM = "CHK60 Thread Pitch " + RUN
frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": PARAM}).insert()
PLAN = frappe.get_doc({"doctype": "Quality Inspection Template", "quality_inspection_template_name": "CHK60 Washer Plan " + RUN,
                       "item_quality_inspection_parameter": [{"specification": PARAM, "numeric": 1, "min_value": 1.4, "max_value": 1.6}]}).insert().name
BOLT = item("CHK60-BOLT", "Bought-Out Components")
WASHER = item("CHK60-WASHER", "Bought-Out Components")
frappe.db.set_value("Item", WASHER, "quality_inspection_template", PLAN)
OIL = item("CHK60-OIL", "Consumables")
check(frappe.db.get_value("Item", BOLT, "inspection_required_before_purchase") == 1 and frappe.db.get_value("Item", OIL, "inspection_required_before_purchase") == 0,
      "2. new bought-out item " + BOLT + " is inspected on receipt; consumable " + OIL + " is not")
SUPPLIER = frappe.get_doc({"doctype": "Supplier", "supplier_name": "CHK60 Fasteners " + RUN}).insert().name
frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")


def receipt(lines):
    doc = frappe.get_doc({"doctype": PR, "supplier": SUPPLIER, "company": company, "posting_date": today, "set_posting_time": 1, "items": []})
    for line in lines:
        store = "Consumables Stores" if line[0] == OIL else "Bought-Out Stores"
        doc.append("items", {"item_code": line[0], "qty": line[1], "received_qty": line[1], "rate": 10, "warehouse": wh(store)})
    doc.insert()
    return doc


def inspect(name, value):
    qi = frappe.get_doc(QI, name)
    if qi.readings:
        qi.readings[0].reading_1 = value
    else:
        qi.status = value
    qi.save()
    qi.submit()
    return qi


# ---------------- 3. saving the receipt makes the QC Inspections ----------------
pr = receipt([[BOLT, 20], [OIL, 5], [WASHER, 100]])
rows = {r.item_code: r for r in pr.items}
bolt_qi = rows[BOLT].quality_inspection
washer_qi = rows[WASHER].quality_inspection
print("INFO  " + pr.name + ": bolt -> " + str(bolt_qi) + ", oil -> " + str(rows[OIL].quality_inspection) + ", washer -> " + str(washer_qi))
q = frappe.db.get_value(QI, bolt_qi, ["inspection_type", "sample_size", "docstatus", "custom_auto_created", "custom_supplier"], as_dict=True) or {}
check(bool(bolt_qi) and q.get("inspection_type") == "Incoming" and q.get("sample_size") == 20 and q.get("docstatus") == 0 and q.get("custom_auto_created") == 1,
      "3. the bolt line got draft QC Inspection " + str(bolt_qi) + " (Incoming, sample 20, created with the receipt)")
check(q.get("custom_supplier") == SUPPLIER, "3. it names the supplier " + SUPPLIER)
check(not rows[OIL].quality_inspection, "3. the consumable line got none")
wq = frappe.get_doc(QI, washer_qi) if washer_qi else None
check(bool(wq) and wq.quality_inspection_template == PLAN and [r.specification for r in wq.readings] == [PARAM],
      "3. the washer's inspection carries its plan: " + (", ".join([r.specification + " " + str(r.min_value) + "-" + str(r.max_value) for r in wq.readings]) if wq else "none"))
pr = frappe.get_doc(PR, pr.name)
pr.save()
check(frappe.db.count(QI, {"reference_name": pr.name}) == 2, "3. saving again makes nothing new (2 inspections)")
todo = frappe.get_all("ToDo", filters={"reference_type": "Item", "reference_name": BOLT, "status": "Open", "description": ["like", "%" + PLAN_RULE + "%"]},
                      fields=["allocated_to", "description"])
check(len(todo) == 1 and todo[0].allocated_to == OWNER, "3. Quality (" + str(OWNER) + ") has a ToDo: " + (todo[0].description.split("\n")[-1][:160] if todo else "none"))
panel = frappe.call(QC + ".get_receipt_qc_panel", purchase_receipt=pr.name) or []
for r in panel:
    print("INFO  panel: " + r.get("text") + " [" + r.get("colour") + "]")
check(len(panel) == 3 and panel[0].get("colour") == "orange" and "no inspection plan" in panel[0].get("text") and panel[2].get("text") == "Incoming QC gate: Soft Block",
      "3. the receipt's Incoming QC panel lists both lines and the gate")

# ---------------- 4. Soft Block: a reason until inspected ----------------
gate = frappe.call(QC + ".qc_gate_check", name=pr.name) or {}
check(gate.get("rule_code") == GATE_RULE, "4. the form asks for a reason -> " + str(gate.get("message"))[:200])
refused("4. submit without a reason is refused", lambda: frappe.get_doc(PR, pr.name).submit(), GATE_RULE)

# ---------------- 5. Hard Block, accepted and rejected inspections ----------------
set_params({"custom_incoming_qc_gate_mode": "Hard Block"})
check(not frappe.call(QC + ".qc_gate_check", name=pr.name), "5. Hard Block never offers a reason")
inspect(washer_qi, "1.5")
check(frappe.db.get_value(QI, washer_qi, "status") == "Accepted", "5. washer reading 1.5 (plan 1.4-1.6) -> Accepted")
inspect(bolt_qi, "Rejected")
refused("5. bolt inspection Rejected while 20 are accepted into stores -> refused", lambda: frappe.get_doc(PR, pr.name).submit(), "Rejected but 20")

# ---------------- 6. Soft Block with a reason ----------------
set_params({"custom_incoming_qc_gate_mode": "Soft Block"})
gate = frappe.call(QC + ".qc_gate_check", name=pr.name) or {}
frappe.call("pepl_os.common.overrides.record_override", rule_code=GATE_RULE, reference_doctype=PR, reference_name=pr.name,
            message=gate.get("message") or "", reason="Concession from the customer, letter attached")
done = frappe.get_doc(PR, pr.name)
done.submit()
check(done.docstatus == 1, "6. with a reason the receipt submits")
check(bool(frappe.db.exists("PEPL Override Log", {"rule_code": GATE_RULE, "reference_name": pr.name})), "6. the reason is in the Override Log (" + GATE_RULE + ")")

# ---------------- 7. removed line / deleted receipt ----------------
pr2 = receipt([[BOLT, 4], [WASHER, 6]])
gone = [r.quality_inspection for r in pr2.items if r.item_code == WASHER][0]
pr2 = frappe.get_doc(PR, pr2.name)
pr2.remove([r for r in pr2.items if r.item_code == WASHER][0])
pr2.save()
check(not frappe.db.exists(QI, gone), "7. removing the washer line removed its unused draft " + gone)
kept = pr2.items[0].quality_inspection
frappe.delete_doc(PR, pr2.name)
check(not frappe.db.exists(QI, kept), "7. deleting the draft receipt removed its draft " + str(kept))

# ---------------- 8. plan set -> ToDo closed; Advisory ----------------
item_doc = frappe.get_doc("Item", BOLT)
item_doc.quality_inspection_template = PLAN
item_doc.save()
check(not frappe.get_all("ToDo", filters={"reference_name": BOLT, "status": "Open", "description": ["like", "%" + PLAN_RULE + "%"]}),
      "8. setting the bolt's inspection plan closed the Quality ToDo")
set_params({"custom_incoming_qc_gate_mode": "Advisory"})
pr3 = receipt([[BOLT, 3]])
pr3 = frappe.get_doc(PR, pr3.name)
pr3.submit()
check(pr3.docstatus == 1, "8. Advisory: a receipt with an open inspection submits with a warning only")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
