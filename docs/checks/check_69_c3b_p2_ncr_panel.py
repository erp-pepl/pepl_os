# PEPL OS v0.69.0 - Check 69: C3b-P2 the NCR panel - severity, status and age, what and where from, disposition
# and cost (with a hint at the item's valuation rate), who signed and who still signs, the CAPA (five-why, actions,
# target, overdue), what the NCR holds back at dispatch, and what still stops closing.
# Runs on 0.69.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the end.
# Afterwards look at an NCR in the browser (see chat).
VERSION = "0.69.0"
NCR = "PEPL NCR"
CAPA = "PEPL CAPA"
PANEL = "pepl_os.pepl_quality.ncr_panel.get_ncr_panel"
SIGN = "pepl_os.pepl_quality.ncr.sign_off"
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

# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")


# ---------------- 2. test items, a supplier ----------------
def item(code):
    return frappe.get_doc({"doctype": "Item", "item_code": "CHK69-" + code + "-" + RUN, "item_name": "CHK69 " + code + " " + RUN,
                           "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0,
                           "is_purchase_item": 1, "valuation_rate": 10}).insert().name


SUPPLIER = frappe.get_doc({"doctype": "Supplier", "supplier_name": "CHK69 Pins " + RUN}).insert().name


def ncr(code, severity, days_ago, extra):
    values = {"doctype": NCR, "source": "Incoming", "severity": severity, "item": code, "qty_affected": 5,
              "raised_on": frappe.utils.add_days(today, -days_ago), "defect_type": "Burr", "defect_description": "burr on the chamfer"}
    values.update(extra)
    return frappe.get_doc(values).insert()


def show(name):
    state = frappe.call(PANEL, name=name) or {}
    for r in state.get("rows") or []:
        print("INFO  panel: " + r.get("text") + " [" + r.get("colour") + "]")
    return state


def find(rows, start):
    for r in rows:
        if r.get("text").startswith(start):
            return r
    return {"text": "", "colour": ""}


# ---------------- 3. an open Minor NCR from a supplier ----------------
PIN = item("PIN")
first = ncr(PIN, "Minor", 3, {"supplier": SUPPLIER})
rows = show(first.name).get("rows") or []
check(rows[0].get("text").startswith("Minor NCR, Open · Incoming · raised ") and rows[0].get("text").endswith("(3 day(s) ago)")
      and rows[0].get("colour") == "orange", "3. header: Minor NCR, Open, Incoming, raised 3 day(s) ago (orange)")
check(rows[1].get("text") == "What: 5 Nos of " + PIN + " · Burr: burr on the chamfer", "3. 'What: 5 Nos of ...' (no '5.0')")
check(rows[2].get("text") == "From: supplier " + SUPPLIER, "3. 'From: supplier ...'")
check(find(rows, "Disposition").get("text") == "Disposition: not chosen yet", "3. 'Disposition: not chosen yet'")
check(find(rows, "CAPA").get("text") == "CAPA: not needed for a Minor NCR", "3. 'CAPA: not needed for a Minor NCR'")
check(" until this NCR is closed (gate: " in find(rows, "Dispatch: " + PIN).get("text"), "3. the dispatch hold on the item is shown")
check(rows[-1].get("text").startswith("To close: choose the disposition") and rows[-1].get("colour") == "orange",
      "3. 'To close: choose the disposition ...'")

# ---------------- 4. disposition and cost ----------------
first.disposition = "Scrap"
first.save()
row = find(show(first.name).get("rows") or [], "Disposition")
check(row.get("text").startswith("Disposition: Scrap · cost not entered yet (about ") and "50" in row.get("text") and row.get("colour") == "orange",
      "4. Scrap without a cost: hint 'about 50' (5 x valuation 10), orange")
first.estimated_cost = 75
first.save()
row = find(show(first.name).get("rows") or [], "Disposition")
check(row.get("text").startswith("Disposition: Scrap · cost ") and "75" in row.get("text") and row.get("colour") == "gray", "4. cost 75 shown, gray")

# ---------------- 5. signed, ready, closed ----------------
frappe.call(SIGN, ncr=first.name, remarks="Check 69")
state = show(first.name)
rows = state.get("rows") or []
check(find(rows, "Signed: ").get("colour") == "green" and not find(rows, "Still to sign").get("text"), "5. signed rows green, nobody still to sign")
check(rows[-1].get("text") == "Ready to close: set the Status to Closed and save" and not state.get("can_sign"), "5. 'Ready to close', no Sign off button")
first = frappe.get_doc(NCR, first.name)
first.status = "Closed"
first.save()
rows = show(first.name).get("rows") or []
check(rows[0].get("colour") == "green" and rows[-1].get("text").startswith("Closed on ") and not find(rows, "Dispatch").get("text"),
      "5. closed: green header, 'Closed on ... by ...', no dispatch hold")

# ---------------- 6. a Critical NCR and its CAPA ----------------
crit = ncr(item("CRIT"), "Critical", 0, {})
NAME = frappe.db.get_value(NCR, crit.name, "capa")
rows = show(crit.name).get("rows") or []
row = find(rows, "CAPA")
check(bool(NAME) and row.get("text").startswith("CAPA " + str(NAME) + ": Open · target ") and "five-why: 0 of " in row.get("text")
      and "no Corrective Action" in row.get("text") and row.get("colour") == "orange", "6. CAPA line: Open, target, five-why 0 of n, no Corrective Action")
check(rows[0].get("colour") == "red", "6. a Critical NCR's header is red")
frappe.db.set_value(CAPA, NAME, "target_date", frappe.utils.add_days(today, -4))
row = find(show(crit.name).get("rows") or [], "CAPA")
check("- OVERDUE by 4 day(s)" in row.get("text") and row.get("colour") == "red", "6. target 4 days ago: 'OVERDUE by 4 day(s)', red")

# ---------------- 7. one Major NCR, no CAPA yet ----------------
MAJ = item("MAJ")
major = ncr(MAJ, "Major", 0, {})
row = find(show(major.name).get("rows") or [], "CAPA")
check(row.get("text").startswith("CAPA: none yet · 1 of ") and (" Major / Critical NCRs on " + MAJ + " within ") in row.get("text"),
      "7. 'CAPA: none yet · 1 of n Major / Critical NCRs on ... raise one'")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
