# PEPL OS v0.66.0 - Check 66: C3b-Q5 the dispatch gate - a Delivery Note of an item with "Inspection Required before
# Delivery" gets its final QC Inspection by itself; the delivery cannot go (Hard Block) or needs a reason (Soft Block)
# until that inspection is Accepted and no NCR is open on the item; Advisory only warns.
# Runs on 0.66.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes it makes, is undone at the end. Afterwards look at the screens in the browser (see chat).
VERSION = "0.66.0"
PARAMS = "PEPL System Parameters"
QI = "Quality Inspection"
DN = "Delivery Note"
NCR = "PEPL NCR"
MOD = "pepl_os.pepl_quality.dispatch"
RULE = "QA-DISPATCH"
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
check(bool(frappe.get_meta(PARAMS).get_field("custom_dispatch_gate_mode")),
      "1. System Parameters > Quality > Dispatch Gate (" + str(frappe.db.get_single_value(PARAMS, "custom_dispatch_gate_mode")) + ")")
check(MOD + ".before_submit_delivery" in str(frappe.get_hooks("doc_events").get(DN)), "1. the dispatch gate is wired to the Delivery Note")

# ---------------- 2. an item inspected before delivery, stock, a customer and an order ----------------
set_params({"custom_dispatch_gate_mode": "Hard Block", "custom_enforce_override_reason": 1, "dn_material_gate_mode": "Off"})
refused("2. an unknown gate mode is refused", lambda: set_params({"custom_dispatch_gate_mode": "Sometimes"}), "Dispatch Gate")
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    hsn = codes[0] if codes else ""
PARAM = "CHK66 Shaft Diameter " + RUN
frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": PARAM}).insert()
PLAN = frappe.get_doc({"doctype": "Quality Inspection Template", "quality_inspection_template_name": "CHK66 Final Plan " + RUN,
                       "item_quality_inspection_parameter": [{"specification": PARAM, "numeric": 1, "min_value": 19.9, "max_value": 20.1}]}).insert().name


def item(code, inspected):
    v = {"doctype": "Item", "item_code": code + "-" + RUN, "item_name": code + " " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos",
         "is_stock_item": 1, "is_sales_item": 1 if hsn else 0, "valuation_rate": 50}
    if hsn:
        v["gst_hsn_code"] = hsn
    if inspected:
        v["inspection_required_before_delivery"] = 1
        v["quality_inspection_template"] = PLAN
    return frappe.get_doc(v).insert().name


SHAFT = item("CHK66-SHAFT", True)
BUSH = item("CHK66-BUSH", False)
receipt = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
                          "items": [{"item_code": SHAFT, "qty": 30, "t_warehouse": wh("FG Stores"), "basic_rate": 50},
                                    {"item_code": BUSH, "qty": 30, "t_warehouse": wh("FG Stores"), "basic_rate": 50}]}).insert()
receipt.submit()
groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
customer = frappe.get_doc({"doctype": "Customer", "customer_name": "CHK66 Customer " + RUN, "customer_type": "Company",
                           "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert().name
due = frappe.utils.add_days(today, 10)
so = frappe.get_doc({"doctype": "Sales Order", "customer": customer, "company": company, "transaction_date": today, "delivery_date": due, "custom_sector": "Private",
                     "items": [{"item_code": SHAFT, "qty": 30, "rate": 100, "warehouse": wh("FG Stores"), "delivery_date": due},
                               {"item_code": BUSH, "qty": 30, "rate": 100, "warehouse": wh("FG Stores"), "delivery_date": due}]}).insert()
so.submit()
line = {r.item_code: r.name for r in so.items}


def delivery(code, qty):
    return frappe.get_doc({"doctype": DN, "customer": customer, "company": company, "posting_date": today,
                           "items": [{"item_code": code, "qty": qty, "rate": 100, "warehouse": wh("FG Stores"), "against_sales_order": so.name,
                                      "so_detail": line[code]}]}).insert()


# ---------------- 3. the final inspection is made with the delivery ----------------
dn = delivery(SHAFT, 5)
qi_name = dn.items[0].quality_inspection
q = frappe.db.get_value(QI, qi_name, ["inspection_type", "sample_size", "docstatus", "quality_inspection_template"], as_dict=True) or {}
print("INFO  " + dn.name + ": 5 shafts -> final inspection " + str(qi_name))
check(bool(qi_name) and q.get("inspection_type") == "Outgoing" and q.get("sample_size") == 5 and q.get("docstatus") == 0 and q.get("quality_inspection_template") == PLAN,
      "3. saving the delivery made draft final inspection " + str(qi_name) + " (Outgoing, sample 5, with the plan)")
panel = frappe.call(MOD + ".get_dispatch_panel", delivery_note=dn.name) or []
for r in panel:
    print("INFO  panel: " + r.get("text") + " [" + r.get("colour") + "]")
check(len(panel) == 2 and panel[0].get("colour") == "orange" and panel[1].get("text") == "Dispatch gate: Hard Block", "3. the Dispatch QC panel shows it 'to be inspected'")

# ---------------- 4. Hard Block until Accepted ----------------
check(not frappe.call(MOD + ".dispatch_gate_check", name=dn.name), "4. Hard Block never offers a reason")
refused("4. Hard Block: the delivery cannot go before the final inspection", lambda: frappe.get_doc(DN, dn.name).submit(), "not finished")
qi = frappe.get_doc(QI, qi_name)
qi.readings[0].reading_1 = "20.0"
qi.save()
qi.submit()
done = frappe.get_doc(DN, dn.name)
done.submit()
check(qi.status == "Accepted" and done.docstatus == 1, "4. reading 20.0 (plan 19.9 - 20.1) Accepted -> the delivery submits")

# ---------------- 5. an open NCR on the item ----------------
bad = frappe.get_doc({"doctype": NCR, "source": "In-Process", "severity": "Minor", "item": BUSH, "qty_affected": 2, "defect_description": "CHK66 scratch"}).insert()
dn2 = delivery(BUSH, 3)
refused("5. a bush with open NCR " + bad.name + " cannot go", lambda: frappe.get_doc(DN, dn2.name).submit(), "open NCR " + bad.name)
set_params({"custom_dispatch_gate_mode": "Soft Block"})
gate = frappe.call(MOD + ".dispatch_gate_check", name=dn2.name) or {}
check(gate.get("rule_code") == RULE, "5. Soft Block: the form asks for a reason -> " + str(gate.get("message"))[:160])
refused("5. Soft Block: without a reason it is refused", lambda: frappe.get_doc(DN, dn2.name).submit(), RULE)
frappe.call("pepl_os.common.overrides.record_override", rule_code=RULE, reference_doctype=DN, reference_name=dn2.name,
            message=gate.get("message") or "", reason="Scratch is cosmetic, customer accepted by mail")
d2 = frappe.get_doc(DN, dn2.name)
d2.submit()
check(d2.docstatus == 1 and bool(frappe.db.exists("PEPL Override Log", {"rule_code": RULE, "reference_name": dn2.name})),
      "5. with a reason it goes; the reason is in the Override Log (" + RULE + ")")

# ---------------- 6. a rejected final inspection; Advisory ----------------
set_params({"custom_dispatch_gate_mode": "Hard Block"})
dn3 = delivery(SHAFT, 4)
qi3 = frappe.get_doc(QI, dn3.items[0].quality_inspection)
qi3.readings[0].reading_1 = "20.6"
qi3.save()
qi3.submit()
raised = frappe.get_all(NCR, filters={"quality_inspection": qi3.name}, fields=["name", "source"])
check(qi3.status == "Rejected" and len(raised) == 1 and raised[0].source == "Dispatch", "6. reading 20.6 -> final inspection Rejected -> NCR " + (raised[0].name if raised else "none") + " (Dispatch)")
refused("6. the rejected shafts cannot go", lambda: frappe.get_doc(DN, dn3.name).submit(), "is Rejected")
set_params({"custom_dispatch_gate_mode": "Advisory"})
d3 = frappe.get_doc(DN, dn3.name)
d3.submit()
check(d3.docstatus == 1, "6. Advisory: it goes with a warning only")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
