# PEPL OS v0.76.0 - Check 76: C3b-B1 inspection-lot management - a lot of a Sales Order line goes lot request ->
# proof inspection -> bulk lot offer -> the agency's IC; each step needs the one before; a rejected quantity raises an
# NCR; the Delivery Note may ship only what the ICs accepted (dispatch gate).
# Runs on 0.76.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters change it makes, is undone at the end. The pop-ups after Execute are the refusals it provokes on
# purpose. Afterwards look at an Inspection Lot in the browser (see chat).
VERSION = "0.76.0"
PARAMS = "PEPL System Parameters"
LOT = "PEPL Inspection Lot"
NCR = "PEPL NCR"
DN = "Delivery Note"
PANEL = "pepl_os.pepl_quality.inspection_lot.get_lot_panel"
GATE = "pepl_os.pepl_quality.dispatch.get_dispatch_panel"
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


def show(name):
    rows = frappe.call(PANEL, name=name) or []
    for r in rows:
        print("INFO  panel: " + r.get("text") + " [" + r.get("colour") + "]")
    return rows


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.db.exists("DocType", LOT)) and frappe.get_meta(NCR).get_field("inspection_lot") is not None, "1. PEPL Inspection Lot exists; the NCR links to its lot")

# ---------------- 2. an item, stock, a customer, an order of 30 ----------------
params = frappe.get_doc(PARAMS)
params.set("custom_dispatch_gate_mode", "Hard Block")
params.set("dn_material_gate_mode", "Off")
params.save()
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    hsn = codes[0] if codes else ""
v = {"doctype": "Item", "item_code": "CHK76-PIN-" + RUN, "item_name": "CHK76 Pin " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos",
     "is_stock_item": 1, "is_sales_item": 1 if hsn else 0, "valuation_rate": 50}
if hsn:
    v["gst_hsn_code"] = hsn
PIN = frappe.get_doc(v).insert().name
receipt = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
                          "items": [{"item_code": PIN, "qty": 30, "t_warehouse": wh("FG Stores"), "basic_rate": 50}]}).insert()
receipt.submit()
groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
customer = frappe.get_doc({"doctype": "Customer", "customer_name": "CHK76 Railway " + RUN, "customer_type": "Company",
                           "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}).insert().name
due = frappe.utils.add_days(today, 10)
so = frappe.get_doc({"doctype": "Sales Order", "customer": customer, "company": company, "transaction_date": today, "delivery_date": due, "custom_sector": "Private",
                     "items": [{"item_code": PIN, "qty": 30, "rate": 100, "warehouse": wh("FG Stores"), "delivery_date": due}]}).insert()
so.submit()
LINE = so.items[0].name


def delivery(qty):
    return frappe.get_doc({"doctype": DN, "customer": customer, "company": company, "posting_date": today,
                           "items": [{"item_code": PIN, "qty": qty, "rate": 100, "warehouse": wh("FG Stores"), "against_sales_order": so.name,
                                      "so_detail": LINE}]}).insert()


def new_lot(qty, values):
    base = {"doctype": LOT, "sales_order": so.name, "item": PIN, "lot_qty": qty, "inspection_agency": "RITES"}
    base.update(values)
    return frappe.get_doc(base).insert()


# ---------------- 3. lot of 20: request -> proof -> offer -> IC ----------------
refused("3. a lot bigger than the order is refused", lambda: new_lot(31, {}), "more than the 30 ordered")
lot = new_lot(20, {"proof_required": 1})
check(lot.status == "Draft" and lot.so_qty == 30, "3. new lot: Draft, ordered 30")
lot.requested_on = frappe.utils.add_days(today, -10)
lot.lot_no = "CHK76/LOT/1"
lot.save()
lot.proof_scheduled_on = frappe.utils.add_days(today, -8)
lot.save()
check(lot.status == "Proof Scheduled", "3. lot number requested, proof scheduled -> Proof Scheduled")


def offer_too_early():
    d = frappe.get_doc(LOT, lot.name)
    d.offered_on = today
    d.offered_qty = 20
    d.save()


refused("3. offering before the proof has Passed is refused", offer_too_early, "once the proof inspection has Passed")
lot = frappe.get_doc(LOT, lot.name)
lot.proof_result = "Passed"
lot.offered_on = frappe.utils.add_days(today, -2)
lot.offered_qty = 20
lot.save()
check(lot.status == "Offered", "3. proof Passed, 20 offered -> Offered")


def ic_without_number():
    d = frappe.get_doc(LOT, lot.name)
    d.update({"inspected_on": today, "accepted_qty": 18, "rejected_qty": 2})
    d.save()


refused("3. an accepted quantity without the IC number is refused", ic_without_number, "IC / Inspection Note number")
lot = frappe.get_doc(LOT, lot.name)
lot.update({"inspected_on": today, "inspector": "IE CHK76", "accepted_qty": 18, "rejected_qty": 2, "ic_number": "RITES/CHK76/IC/1", "ic_date": today})
lot.save()
lot = frappe.get_doc(LOT, lot.name)
rows = show(lot.name)
check(lot.status == "Inspected" and rows[0].get("colour") == "green", "3. IC: 18 accepted, 2 rejected -> Inspected (green)")
check(bool(lot.ncr) and frappe.db.get_value(NCR, lot.ncr, "inspection_lot") == lot.name and frappe.db.get_value(NCR, lot.ncr, "qty_affected") == 2,
      "3. the 2 rejected raised NCR " + str(lot.ncr) + " for the lot")


def change_ic():
    d = frappe.get_doc(LOT, lot.name)
    d.accepted_qty = 20
    d.rejected_qty = 0
    d.save()


refused("3. an inspected lot is locked", change_ic, "locked")

# ---------------- 4. the dispatch gate counts the IC ----------------
frappe.db.set_value(NCR, lot.ncr, {"status": "Cancelled", "cancel_reason": "Check 76: not about this test"})  # leave only the IC rule
refused("4. delivering 20 against an IC of 18 is refused", lambda: delivery(20).submit(), "this delivery would make 20")
first = delivery(18)
first.submit()
check(first.docstatus == 1, "4. delivering the 18 the IC accepted goes through")
second = delivery(1)
panel = " | ".join([r.get("text") for r in (frappe.call(GATE, delivery_note=second.name) or [])])
print("INFO  dispatch panel: " + panel)
check("agency ICs accepted 18, delivered 18, left to ship 0" in panel, "4. the Dispatch QC panel: 'agency ICs accepted 18, delivered 18, left to ship 0'")
refused("4. one more is refused", lambda: second.submit(), "18 already delivered")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
