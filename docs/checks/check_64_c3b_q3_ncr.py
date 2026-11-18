# PEPL OS v0.64.0 - Check 64: C3b-Q3 Non-Conformance Reports - the three rules that raise an NCR by themselves (a
# QC Inspection submitted as Rejected; a customer return; a day's rejection rate above the threshold on the shift
# entries), the Quality ToDo, and the severity sign-off matrix that must be complete before an NCR can be closed.
# Runs on 0.64.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes it makes, is undone at the end. Afterwards look at the screens in the browser (see chat).
VERSION = "0.64.0"
PARAMS = "PEPL System Parameters"
NCR = "PEPL NCR"
QI = "Quality Inspection"
PR = "Purchase Receipt"
SPR = "PEPL Shift Production Entry"
MOD = "pepl_os.pepl_quality.ncr"
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
yesterday = frappe.utils.add_days(today, -1)
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def set_params(values):
    doc = frappe.get_doc(PARAMS)
    for field in values:
        doc.set(field, values[field])
    doc.save()


def ncrs(filters):
    return frappe.get_all(NCR, filters=filters, fields=["name", "source", "severity", "status", "item", "qty_affected", "supplier", "purchase_receipt",
                                                       "customer", "delivery_note", "raise_rule", "pieces_made", "pieces_rejected",
                                                       "rejection_rate", "defect_description", "required_sign_offs"])


def todos(name):
    return frappe.get_all("ToDo", filters={"reference_type": NCR, "reference_name": name, "status": "Open"}, fields=["allocated_to", "description"])


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.db.exists("DocType", NCR)) and bool(frappe.db.exists("DocType", "PEPL NCR Sign-off")), "1. PEPL NCR and its Sign-off table exist")
matrix = []
for sev in ["minor", "major", "critical"]:
    matrix.append(sev.title() + ": " + str(frappe.db.get_single_value(PARAMS, "custom_ncr_signoff_" + sev) or "").replace("\n", " + "))
check(bool(frappe.get_meta(PARAMS).get_field("custom_ncr_rejection_rate_percent")), "1. System Parameters > Quality > NCR sign-off matrix -> " + "; ".join(matrix))
hooks = frappe.get_hooks("doc_events")
check(MOD + ".on_inspection_submit" in str(hooks.get(QI)) and MOD + ".on_delivery_note_submit" in str(hooks.get("Delivery Note")),
      "1. the NCR rules are wired to QC Inspection and Delivery Note")

# ---------------- 2. settings for this run ----------------
values = {"enable_operational_todos": 1, "custom_ncr_auto_severity": "Major", "custom_ncr_on_customer_return": 1,
          "custom_ncr_rejection_rate_percent": 5, "custom_ncr_rejection_min_pieces": 10, "custom_incoming_qc_gate_mode": "Advisory",
          "custom_ncr_signoff_minor": "Quality Manager", "custom_ncr_signoff_major": "Quality Manager\nManufacturing Manager",
          "custom_ncr_signoff_critical": "Quality Manager\nManufacturing Manager\nPEPL CEO",
          "custom_rejections_to_scrap": 0, "skill_check_mode": "Advisory", "custom_spr_tool_photo_required": 0, "custom_spr_max_unaccounted_minutes": 15}
if not frappe.db.get_single_value(PARAMS, "custom_quality_notification_owner"):
    values["custom_quality_notification_owner"] = "Administrator"
set_params(values)
OWNER = frappe.db.get_single_value(PARAMS, "custom_quality_notification_owner")
refused("2. an unknown role in the sign-off matrix is refused", lambda: set_params({"custom_ncr_signoff_major": "Quality Manager\nChief Wizard"}), "Chief Wizard")
refused("2. a threshold of 150 % is refused", lambda: set_params({"custom_ncr_rejection_rate_percent": 150}), "Rejection Rate Threshold")

# ---------------- 3. QA-NCR-QI: a rejected incoming inspection ----------------
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    hsn = codes[0] if codes else ""


def item(code, group, sales):
    v = {"doctype": "Item", "item_code": code + "-" + RUN, "item_name": code + " " + RUN, "item_group": group, "stock_uom": "Nos",
         "is_stock_item": 1, "is_sales_item": 1 if (sales and hsn) else 0, "is_purchase_item": 1, "valuation_rate": 10}
    if hsn:
        v["gst_hsn_code"] = hsn
    return frappe.get_doc(v).insert().name


PARAM = "CHK64 Pin Diameter " + RUN
frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": PARAM}).insert()
PLAN = frappe.get_doc({"doctype": "Quality Inspection Template", "quality_inspection_template_name": "CHK64 Pin Plan " + RUN,
                       "item_quality_inspection_parameter": [{"specification": PARAM, "numeric": 1, "min_value": 9.9, "max_value": 10.1}]}).insert().name
PIN = item("CHK64-PIN", "Bought-Out Components", False)
frappe.db.set_value("Item", PIN, {"inspection_required_before_purchase": 1, "quality_inspection_template": PLAN})
SUPPLIER = frappe.get_doc({"doctype": "Supplier", "supplier_name": "CHK64 Pins " + RUN}).insert().name
frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")
pr = frappe.get_doc({"doctype": PR, "supplier": SUPPLIER, "company": company, "posting_date": today,
                     "items": [{"item_code": PIN, "qty": 25, "received_qty": 25, "rate": 10, "warehouse": wh("Bought-Out Stores")}]}).insert()
qi = frappe.get_doc(QI, pr.items[0].quality_inspection)
qi.readings[0].reading_1 = "10.4"
qi.save()
qi.submit()
got = ncrs({"quality_inspection": qi.name})
n = got[0] if got else {}
print("INFO  " + qi.name + " " + str(qi.status) + " -> " + str(n.get("name")) + ": " + str(n.get("defect_description")))
check(len(got) == 1 and n.get("source") == "Incoming" and n.get("severity") == "Major" and n.get("status") == "Open" and n.get("raise_rule") == "QA-NCR-QI",
      "3. reading 10.4 (plan 9.9 - 10.1) -> inspection Rejected -> NCR " + str(n.get("name")) + " (Incoming, Major, Open)")
check(n.get("supplier") == SUPPLIER and n.get("purchase_receipt") == pr.name and n.get("qty_affected") == 25,
      "3. it names the supplier, receipt " + pr.name + " and the 25 pins received")
t = todos(n.get("name")) if n else []
check(len(t) == 1 and t[0].allocated_to == OWNER, "3. Quality (" + str(OWNER) + ") has a ToDo: " + (t[0].description.split("\n")[-1][:140] if t else "none"))
qi_doc = frappe.get_doc(QI, qi.name)
qi_doc.cancel()
check(frappe.db.get_value(NCR, n.get("name"), "status") == "Cancelled" and not todos(n.get("name")),
      "3. cancelling the inspection cancels the unsigned NCR and closes the ToDo")

# ---------------- 4. QA-NCR-RETURN: a customer return ----------------
try:
    SHAFT = item("CHK64-SHAFT", "Finished Goods", True)
    groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
    territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
    customer = frappe.get_doc({"doctype": "Customer", "customer_name": "CHK64 Customer " + RUN, "customer_type": "Company",
                               "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert().name
    due = frappe.utils.add_days(today, 10)
    so = frappe.get_doc({"doctype": "Sales Order", "customer": customer, "company": company, "transaction_date": today, "delivery_date": due,
                         "custom_sector": "Private", "items": [{"item_code": SHAFT, "qty": 10, "rate": 100, "warehouse": wh("FG Stores"), "delivery_date": due}]}).insert()
    so.submit()
    receipt = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
                              "items": [{"item_code": SHAFT, "qty": 10, "t_warehouse": wh("FG Stores"), "basic_rate": 100}]}).insert()
    receipt.submit()
    dn = frappe.get_doc({"doctype": "Delivery Note", "customer": customer, "company": company, "posting_date": today,
                         "items": [{"item_code": SHAFT, "qty": 10, "rate": 100, "warehouse": wh("FG Stores"), "against_sales_order": so.name,
                                    "so_detail": so.items[0].name}]}).insert()
    dn.submit()
    back = frappe.call("erpnext.stock.doctype.delivery_note.delivery_note.make_sales_return", source_name=dn.name)
    back.items[0].qty = -3
    back.insert()
    back.submit()
    got = ncrs({"delivery_note": back.name})
    r = got[0] if got else {}
    print("INFO  return " + back.name + " of 3 against " + dn.name + " -> " + str(r.get("name")) + ": " + str(r.get("defect_description")))
    check(len(got) == 1 and r.get("source") == "Customer" and r.get("customer") == customer and r.get("qty_affected") == 3 and r.get("raise_rule") == "QA-NCR-RETURN",
          "4. the customer return of 3 shafts raised NCR " + str(r.get("name")) + " (Customer, 3)")
    check("returned 3 " in str(r.get("defect_description")), "4. its description says 'returned 3' (no '.0')")
    frappe.get_doc("Delivery Note", back.name).cancel()
    check(frappe.db.get_value(NCR, r.get("name"), "status") == "Cancelled", "4. cancelling the return cancels the NCR")
except Exception as e:
    check(False, "4. customer return could not be run on this site -> " + frappe.utils.strip_html(str(e))[:300])

# ---------------- 5. QA-NCR-RATE: rejection rate on a day's shift entries ----------------
MILL = "CHK64 MILL-01 " + RUN
DAY = "CHK64 Day " + RUN
OP = "CHK64-OP-" + RUN
NO_LOAD = "CHK64 No Load " + RUN
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
pin_code = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Suresh " + RUN, "pin": pin_code}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
FG = item("CHK64-FG", "Finished Goods", False)
BO = item("CHK64-BO", "Bought-Out Components", False)
TURNING = "CHK64 Turning " + RUN
frappe.get_doc({"doctype": "Operation", "name": TURNING, "workstation": MILL}).insert()
bom = frappe.get_doc({"doctype": "BOM", "item": FG, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
                      "currency": frappe.db.get_value("Company", company, "default_currency"), "items": [{"item_code": BO, "qty": 1, "rate": 10}],
                      "operations": [{"operation": TURNING, "workstation": MILL, "time_in_mins": 6}]}).insert()
bom.submit()
wo = frappe.get_doc({"doctype": "Work Order", "production_item": FG, "bom_no": bom.name, "qty": 60, "stock_uom": "Nos", "company": company, "skip_transfer": 1,
                     "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order"})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
CARD = frappe.get_all("Job Card", filters={"work_order": wo.name}, pluck="name")[0]


def entry(good, rejected, on):
    doc = frappe.get_doc({"doctype": SPR, "posting_date": on, "shift": DAY, "workstation": MILL, "operator": OP, "company": company})
    doc.append("production", {"job_card": CARD, "from_time": "08:00", "to_time": "10:00", "good_qty": good, "rejected_qty": rejected, "rejection_reason": "Undersize"})
    doc.append("downtime", {"downtime_category": NO_LOAD, "from_time": "10:00", "to_time": "16:30"})
    doc.insert()
    doc.submit()
    return doc.name


low = entry(6, 3, frappe.utils.add_days(today, -2))
check(not ncrs({"item": FG, "rate_date": frappe.utils.add_days(today, -2)}), "5. 9 pieces made (below the minimum of 10): no NCR")
high = entry(8, 4, yesterday)
got = ncrs({"item": FG, "rate_date": yesterday})
h = got[0] if got else {}
print("INFO  " + high + ": 8 good, 4 rejected -> " + str(h.get("name")) + ": " + str(h.get("defect_description")))
check(len(got) == 1 and h.get("source") == "In-Process" and h.get("raise_rule") == "QA-NCR-RATE" and h.get("pieces_made") == 12
      and h.get("pieces_rejected") == 4 and abs(frappe.utils.flt(h.get("rejection_rate")) - 33.33) < 0.01,
      "5. 4 of 12 rejected (33.33 % above 5 %) -> NCR " + str(h.get("name")) + " (In-Process)")
frappe.get_doc(SPR, high).cancel()
check(frappe.db.get_value(NCR, h.get("name"), "status") == "Cancelled", "5. cancelling the shift entry cancels the NCR (rate gone)")

# ---------------- 6. sign-off matrix and closing ----------------
# Administrator holds every role, so here it signs for both roles of a Major NCR at once. In the browser each person
# signs for their own role only (see the chat).
doc = frappe.get_doc({"doctype": NCR, "source": "Other", "severity": "Major", "item": PIN, "qty_affected": 5, "defect_description": "CHK64 burr on chamfer"}).insert()
check(doc.required_sign_offs == "Quality Manager, Manufacturing Manager", "6. a Major NCR needs: " + str(doc.required_sign_offs))
doc.disposition = "Rework"
doc.status = "Closed"
refused("6. closing without the sign-offs is refused", lambda: doc.save(), "still needs the sign-off")
state = frappe.call(MOD + ".get_sign_off_state", ncr=doc.name)
check(state.get("missing") == ["Quality Manager", "Manufacturing Manager"], "6. the form shows still to sign: " + ", ".join(state.get("missing") or []))
signed = frappe.call(MOD + ".sign_off", ncr=doc.name, remarks="CHK64 reworked and re-checked")
check(signed.get("missing") == [] and signed.get("status") == "Under Review", "6. after signing nothing is missing; status Under Review")
done = frappe.get_doc(NCR, doc.name)
done.disposition = "Rework"
done.status = "Closed"
done.save()
check(done.status == "Closed" and bool(done.closed_on), "6. with every signature and a disposition it closes")
done.reload()
done.qty_affected = 9
refused("6. a closed NCR cannot be changed", lambda: done.save(), "cannot be changed")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
