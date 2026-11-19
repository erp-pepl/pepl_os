# PEPL OS v0.77.1 - Check 77 rev 3: C3b-B4 drawing-revision mid-production alert - a Job Order records the drawing revision it
# is made to; a new current revision on the Product Master flags the open Job Orders of the item (Drawing Change, ToDo
# PRD-DRAWING-REV); a Production / Quality Manager acknowledges what the job is made to from now.
# Rev 3 (19 Nov 2026): makes its own item and BOM (rev 2 used an item with a default BOM on the site; the demo site has
# none). Rev 2: every drawing revision has its Drawing File, which pepl_sales requires.
# Runs on 0.77.1 or later. System Console, Type = Python. Everything below is undone at the end: the last lines roll
# back, even if "Commit" were ticked. The pop-ups after Execute are the refusals it provokes on purpose.
VERSION = "0.77.1"
WO = "Work Order"
PRODUCT = "PEPL Product Master"
PANEL = "pepl_os.pepl_quality.drawing.get_drawing_panel"
ACK = "pepl_os.pepl_quality.drawing.acknowledge"
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


def show(name):
    data = frappe.call(PANEL, work_order=name) or {}
    for r in data.get("rows") or []:
        print("INFO  panel: " + r.get("text") + " [" + r.get("colour") + "]")
    return data


def todos(name):
    return frappe.db.count("ToDo", {"reference_type": WO, "reference_name": name, "status": "Open", "description": ["like", "%PRD-DRAWING-REV%"]})


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
events = frappe.get_hooks("doc_events")
check("pepl_os.pepl_quality.drawing.on_product_update" in str(events.get(PRODUCT)) and "pepl_os.pepl_quality.drawing.stamp_revision" in str(events.get(WO))
      and frappe.get_meta(WO).get_field("custom_drawing_revision") is not None, "1. Job Orders record their drawing revision; Product Master changes are watched")

# ---------------- 2. its own item with a BOM, and its Product Master on revision CHK77-A ----------------
RM = frappe.get_doc({"doctype": "Item", "item_code": "CHK77-RM-" + RUN, "item_name": "CHK77 bar " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos",
                     "is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
ITEM = frappe.get_doc({"doctype": "Item", "item_code": "CHK77-SHAFT-" + RUN, "item_name": "CHK77 shaft " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos",
                       "is_stock_item": 1, "is_purchase_item": 0, "is_sales_item": 0, "valuation_rate": 50}).insert().name
bom = frappe.get_doc({"doctype": "BOM", "item": ITEM, "company": company, "quantity": 1, "items": [{"item_code": RM, "qty": 1, "rate": 10}]}).insert()
bom.submit()
BOM = bom.name
check(frappe.db.get_value("BOM", BOM, "docstatus") == 1, "2. its own item " + ITEM + " with BOM " + BOM)
DRAWING = frappe.get_doc({"doctype": "File", "file_name": "chk77-drawing-" + RUN + ".txt", "content": "CHK77 drawing", "is_private": 1}).insert().file_url
product = frappe.get_doc({"doctype": PRODUCT, "product_name": "CHK77 " + ITEM, "product_type": "Single Component", "status": "Active", "linked_item": ITEM,
                          "drawing_revisions": [{"revision": "CHK77-A", "issue_date": frappe.utils.add_days(frappe.utils.today(), -30), "is_current": 1, "drawing_file": DRAWING}]}).insert()
wo = frappe.get_doc({"doctype": WO, "production_item": ITEM, "bom_no": BOM, "qty": 5, "company": company, "skip_transfer": 1,
                     "planned_start_date": frappe.utils.now(), "fg_warehouse": frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": "FG Stores", "is_group": 0}, "name")})
wo.get_items_and_operations_from_bom()
wo.insert()
check(frappe.db.get_value(WO, wo.name, "custom_drawing_revision") == "CHK77-A", "2. the new Job Order " + wo.name + " records Rev CHK77-A")
data = show(wo.name)
check(data.get("rows")[0].get("text") == "Made to drawing Rev CHK77-A · current Rev CHK77-A" and data.get("rows")[0].get("colour") == "green",
      "2. Drawing panel: 'Made to drawing Rev CHK77-A · current Rev CHK77-A' (green)")

# ---------------- 3. the drawing changes to CHK77-B ----------------
product = frappe.get_doc(PRODUCT, product.name)
for row in product.drawing_revisions:
    row.is_current = 0
product.append("drawing_revisions", {"revision": "CHK77-B", "issue_date": frappe.utils.today(), "is_current": 1, "change_description": "Hole moved 2 mm", "drawing_file": DRAWING})
product.save()
alert = frappe.db.get_value(WO, wo.name, "custom_drawing_alert") or ""
print("INFO  Drawing Change: " + alert)
check(alert.startswith("Drawing changed from Rev CHK77-A to Rev CHK77-B on ") and alert.endswith(": Hole moved 2 mm"), "3. the Job Order is flagged: Rev CHK77-A -> CHK77-B and what changed")
check(todos(wo.name) == 1, "3. Production has a High ToDo for it (PRD-DRAWING-REV)")
data = show(wo.name)
check(data.get("rows")[0].get("colour") == "red" and data.get("can_acknowledge"), "3. the panel is red, with 'Acknowledge Drawing Change'")

# ---------------- 4. acknowledged ----------------
refused("4. acknowledging without saying what was checked is refused", lambda: frappe.call(ACK, work_order=wo.name, work_to="CHK77-B", remarks="ok"), "at least 10 characters")
frappe.call(ACK, work_order=wo.name, work_to="CHK77-B", remarks="First piece checked to Rev CHK77-B")
data = show(wo.name)
check(frappe.db.get_value(WO, wo.name, "custom_drawing_revision") == "CHK77-B" and todos(wo.name) == 0 and data.get("rows")[0].get("colour") == "green"
      and not data.get("can_acknowledge"), "4. acknowledged: made to CHK77-B, ToDo closed, panel green")

frappe.db.rollback()
print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Everything above was rolled back: nothing was saved.")
