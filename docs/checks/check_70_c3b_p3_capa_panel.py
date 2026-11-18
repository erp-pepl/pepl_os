# PEPL OS v0.70.0 - Check 70: C3b-P3 the CAPA panel - status, age and owner, target (days left / due today /
# overdue), the NCRs, containment, five-why completeness (next why), each open action with who and when (overdue in
# red), what still stops closing, and how closing compared with the target.
# Runs on 0.70.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the end.
# Afterwards look at a CAPA in the browser (see chat).
VERSION = "0.70.0"
NCR = "PEPL NCR"
CAPA = "PEPL CAPA"
PANEL = "pepl_os.pepl_quality.capa_panel.get_capa_panel"
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
WHYS = int(frappe.db.get_single_value("PEPL System Parameters", "custom_capa_whys_required") or 5)
print("INFO  CAPA: Whys Required on this site = " + str(WHYS))

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")


# ---------------- 2. a Critical NCR raises a CAPA ----------------
def item(code):
    return frappe.get_doc({"doctype": "Item", "item_code": "CHK70-" + code + "-" + RUN, "item_name": "CHK70 " + code + " " + RUN,
                           "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0,
                           "is_purchase_item": 1, "valuation_rate": 10}).insert().name


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


SHAFT = item("SHAFT")
first = frappe.get_doc({"doctype": NCR, "source": "In-Process", "severity": "Critical", "item": SHAFT, "qty_affected": 3,
                        "defect_description": "crack at the keyway"}).insert()
NAME = frappe.db.get_value(NCR, first.name, "capa")
check(bool(NAME), "2. the Critical NCR raised a CAPA (" + str(NAME) + ")")
rows = show(NAME)
check(rows[0].get("text").startswith("CAPA (Critical NCR) on " + SHAFT + ", Open · raised today by the system · owner ") and rows[0].get("colour") == "orange",
      "2. header: trigger, item, Open, raised today by the system, owner (orange)")
check(rows[1].get("text").startswith("Target ") and rows[1].get("text").endswith(" day(s) left"), "2. 'Target ...: n day(s) left'")
check(rows[2].get("text") == "NCRs (1): " + first.name + " Critical, Open", "2. 'NCRs (1): ... Critical, Open'")
check(find(rows, "Containment").get("text") == "Containment: not recorded" and find(rows, "Containment").get("colour") == "orange",
      "2. 'Containment: not recorded' (orange)")
check(find(rows, "Five-why").get("text") == "Five-why: 0 of " + str(WHYS) + " whys answered, root cause missing · next: Why 1", "2. 'Five-why: 0 of n ... next: Why 1'")
check(find(rows, "Actions").get("text") == "Actions: none yet", "2. 'Actions: none yet'")
check(rows[-1].get("text").startswith("To close: ") and "no Corrective Action" in rows[-1].get("text"), "2. 'To close: ... no Corrective Action'")

# ---------------- 3. containment, a why, three actions ----------------
doc = frappe.get_doc(CAPA, NAME)
doc.containment = "Held all shafts of the lot at stores"
doc.why_1 = "Keyway corner too sharp"
doc.append("actions", {"action_type": "Correction", "description": "Sort the lot", "done_on": today})
doc.append("actions", {"action_type": "Corrective Action", "description": "Radius the keyway corner", "responsible": "Administrator",
                       "due_date": frappe.utils.add_days(today, -3)})
doc.append("actions", {"action_type": "Preventive Action", "description": "Add the radius to the drawing"})
doc.save()
rows = show(NAME)
check(", In Progress · " in rows[0].get("text"), "3. work started: In Progress")
check(find(rows, "Containment").get("text") == "Containment: Held all shafts of the lot at stores", "3. containment shown")
check(("Five-why: 1 of " + str(WHYS) + " whys answered, root cause missing") in find(rows, "Five-why").get("text")
      and (WHYS < 2 or "next: Why 2" in find(rows, "Five-why").get("text")), "3. 'Five-why: 1 of n ... next: Why 2'")
row = find(rows, "Actions")
check(row.get("text") == "Actions: 3 (Correction 1, Corrective Action 1, Preventive Action 1) · 1 done · 2 open, 1 overdue" and row.get("colour") == "red",
      "3. 'Actions: 3 (...) · 1 done · 2 open, 1 overdue' (red)")
row = find(rows, "Corrective Action: ")
check(row.get("text").startswith("Corrective Action: Radius the keyway corner · Administrator · due ") and row.get("text").endswith(" - OVERDUE by 3 day(s)")
      and row.get("colour") == "red", "3. the overdue Corrective Action: who, due, 'OVERDUE by 3 day(s)' (red)")
check(find(rows, "Preventive Action: ").get("text") == "Preventive Action: Add the radius to the drawing · no one responsible · no due date"
      and find(rows, "Preventive Action: ").get("colour") == "orange", "3. 'no one responsible · no due date' (orange)")
check(not find(rows, "Correction: ").get("text"), "3. a done action gets no line of its own")

# ---------------- 4. the CAPA's target passed ----------------
frappe.db.set_value(CAPA, NAME, "target_date", frappe.utils.add_days(today, -4))
rows = show(NAME)
check(rows[0].get("colour") == "red" and rows[1].get("text").endswith(" - OVERDUE by 4 day(s)") and rows[1].get("colour") == "red",
      "4. target 4 days ago: header red, 'Target ... - OVERDUE by 4 day(s)'")

# ---------------- 5. complete, ready, closed late ----------------
doc = frappe.get_doc(CAPA, NAME)
for n in range(1, WHYS + 1):
    doc.set("why_" + str(n), "because " + str(n))
doc.root_cause = "Drawing gives no keyway radius"
for a in doc.actions:
    a.done_on = today
doc.save()
rows = show(NAME)
check(find(rows, "Five-why").get("text") == "Five-why: complete · root cause: Drawing gives no keyway radius" and find(rows, "Five-why").get("colour") == "green",
      "5. 'Five-why: complete · root cause: ...' (green)")
check(rows[-1].get("text") == "Ready to close: set the Status to Closed and save" and rows[-1].get("colour") == "green", "5. 'Ready to close'")
doc = frappe.get_doc(CAPA, NAME)
doc.status = "Closed"
doc.save()
rows = show(NAME)
check(rows[0].get("colour") == "green" and rows[1].get("text").startswith("Closed on ") and rows[1].get("text").endswith(" - 4 day(s) after the target")
      and rows[1].get("colour") == "orange", "5. closed: 'Closed on ... by ... - 4 day(s) after the target' (orange)")

# ---------------- 6. a manual CAPA, cancelled ----------------
manual = frappe.get_doc({"doctype": CAPA, "trigger": "Manual", "item": item("PIN"), "problem_statement": "Customer complaint on finish"}).insert()
rows = show(manual.name)
check(rows[0].get("text").startswith("CAPA (Manual) on ") and find(rows, "NCRs").get("text") == "NCRs: none listed", "6. manual CAPA: 'NCRs: none listed'")
manual.status = "Cancelled"
manual.cancel_reason = "Complaint withdrawn by the customer"
manual.save()
rows = show(manual.name)
check(rows[0].get("colour") == "gray" and rows[-1].get("text") == "Cancelled: Complaint withdrawn by the customer" and not find(rows, "Target").get("text"),
      "6. cancelled: grey, 'Cancelled: reason', no target line")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
