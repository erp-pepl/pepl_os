# PEPL OS v0.73.0 - Check 73: C3b-B3 CAPA effectiveness verification - a CAPA whose actions are complete waits for a
# future-date effectiveness check ("Awaiting Verification", ToDo for its owner); Effective only from the due day and
# not while a new Major / Critical NCR came in since; Not Effective sends it back to In Progress; the CAPA and NCR
# panels show the check.
# Rev 2: no tuple unpacking (rev 1 stopped at "FIRST, NAME = ...": the System Console cannot unpack).
# Runs on 0.73.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters change it makes, is undone at the end. The pop-ups after Execute are the refusals it provokes on
# purpose. Afterwards look at a CAPA in the browser (see chat).
VERSION = "0.73.0"
PARAMS = "PEPL System Parameters"
NCR = "PEPL NCR"
CAPA = "PEPL CAPA"
PANEL = "pepl_os.pepl_quality.capa_panel.get_capa_panel"
NCR_PANEL = "pepl_os.pepl_quality.ncr_panel.get_ncr_panel"
VERIFY = "pepl_os.pepl_quality.capa.verify_capa"
REMARKS = "Three lots inspected since, all accepted"
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
    rows = frappe.call(PANEL, name=name) or []
    for r in rows:
        print("INFO  panel: " + r.get("text") + " [" + r.get("colour") + "]")
    return rows


def find(rows, start):
    for r in rows:
        if r.get("text").startswith(start):
            return r
    return {"text": "", "colour": ""}


def verify_todos(name):
    return frappe.db.count("ToDo", {"reference_type": CAPA, "reference_name": name, "status": "Open", "description": ["like", "%QA-CAPA-VERIFY%"]})


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()

# ---------------- 1. installed; 90 days to the check, 1 why for a short run ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
print("INFO  CAPA: Verification After (Days) on this site = " + str(frappe.db.get_single_value(PARAMS, "custom_capa_verification_days")))
params = frappe.get_doc(PARAMS)
params.set("custom_capa_verification_days", 90)
params.set("custom_capa_whys_required", 1)
params.save()
check(frappe.get_meta(CAPA).get_field("verification_due_on") is not None and "Awaiting Verification" in (frappe.get_meta(CAPA).get_field("status").options or ""),
      "1. PEPL CAPA has the status Awaiting Verification and the Effectiveness Verification fields")


def item(code):
    return frappe.get_doc({"doctype": "Item", "item_code": "CHK73-" + code + "-" + RUN, "item_name": "CHK73 " + code + " " + RUN,
                           "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0,
                           "is_purchase_item": 1, "valuation_rate": 10}).insert().name


def ncr(code, severity):
    return frappe.get_doc({"doctype": NCR, "source": "In-Process", "severity": severity, "item": code, "qty_affected": 3,
                           "defect_description": severity + " defect"}).insert()


def complete_capa(code):
    first = ncr(item(code), "Critical")
    doc = frappe.get_doc(CAPA, frappe.db.get_value(NCR, first.name, "capa"))
    doc.why_1 = "Collet worn"
    doc.root_cause = "No collet change interval"
    doc.append("actions", {"action_type": "Corrective Action", "description": "Collet in the PM list", "done_on": today})
    doc.save()
    return [first.name, doc.name]


def close(name):
    doc = frappe.get_doc(CAPA, name)
    doc.status = "Closed"
    doc.save()
    return frappe.get_doc(CAPA, name)


# ---------------- 2. actions complete: ready ----------------
PAIR = complete_capa("SHAFT")  # no "a, b = ..." in the System Console: it has no unpacking guard
FIRST = PAIR[0]
NAME = PAIR[1]
rows = show(NAME)
check(rows[-1].get("text") == "Ready: set the Status to Closed and save - the effectiveness check is then due in 90 day(s)", "2. 'Ready: ... the effectiveness check is then due in 90 day(s)'")

# ---------------- 3. Closed -> Awaiting Verification ----------------
doc = close(NAME)
DUE = frappe.utils.add_days(today, 90)
check(doc.status == "Awaiting Verification" and str(doc.verification_due_on) == DUE and not doc.closed_on, "3. 'Closed' puts it Awaiting Verification, check due " + DUE + ", not closed yet")
check(verify_todos(NAME) == 1, "3. the CAPA owner has a ToDo for the check (QA-CAPA-VERIFY)")
rows = show(NAME)
check(find(rows, "Actions completed on ").get("text").endswith(" - target met"), "3. 'Actions completed on ... - target met'")
check(find(rows, "Effectiveness check ").get("text").endswith(": 90 day(s) left"), "3. 'Effectiveness check ...: 90 day(s) left'")
check(rows[-1].get("text").startswith("To close: Verify Effectiveness on or after "), "3. 'To close: Verify Effectiveness on or after ...'")
row = find(frappe.call(NCR_PANEL, name=FIRST).get("rows") or [], "CAPA")
check(row.get("text").startswith("CAPA " + NAME + ": Awaiting Verification · effectiveness check due "), "3. the NCR's panel: 'CAPA ...: Awaiting Verification · effectiveness check due ...'")

# ---------------- 4. what is refused while it waits ----------------
refused("4. Effective before the due day is refused", lambda: frappe.call(VERIFY, capa=NAME, result="Effective", remarks=REMARKS), "due on")


def reopen_by_hand():
    d = frappe.get_doc(CAPA, NAME)
    d.status = "In Progress"
    d.save()


refused("4. changing the status by hand is refused", reopen_by_hand, "awaiting its effectiveness check")
refused("4. a result without what was checked is refused", lambda: frappe.call(VERIFY, capa=NAME, result="Not Effective", remarks="no"), "at least 10 characters")

# ---------------- 5. Not Effective: back to In Progress, then a new check ----------------
frappe.call(VERIFY, capa=NAME, result="Not Effective", remarks="Two rejections at the lathe again")
doc = frappe.get_doc(CAPA, NAME)
check(doc.status == "In Progress" and doc.verification_count == 1 and not doc.verification_due_on and verify_todos(NAME) == 0,
      "5. Not Effective -> In Progress, counted once, check and ToDo cleared")
row = find(show(NAME), "Found not effective")
check(row.get("text").startswith("Found not effective 1 time(s), last: ") and "Two rejections at the lathe again" in row.get("text") and row.get("colour") == "red",
      "5. 'Found not effective 1 time(s), last: ...' (red)")
doc.append("actions", {"action_type": "Corrective Action", "description": "Harder collet type", "done_on": today})
doc.save()
doc = close(NAME)
check(doc.status == "Awaiting Verification" and str(doc.verification_due_on) == DUE, "5. closed again -> a new check due " + DUE)

# ---------------- 6. the day passes: Effective closes it ----------------
frappe.db.set_value(CAPA, NAME, "verification_due_on", frappe.utils.add_days(today, -2))
rows = show(NAME)
check(rows[0].get("colour") == "red" and rows[-1].get("text").startswith("To close: press Verify Effectiveness") and rows[-1].get("colour") == "red",
      "6. check 2 days overdue: header red, 'To close: press Verify Effectiveness ...' (red)")
frappe.call(VERIFY, capa=NAME, result="Effective", remarks=REMARKS)
doc = frappe.get_doc(CAPA, NAME)
check(doc.status == "Closed" and doc.verification_result == "Effective" and bool(doc.closed_on) and verify_todos(NAME) == 0, "6. Effective -> Closed, result recorded, ToDo closed")
check(find(show(NAME), "Verified effective on ").get("colour") == "green", "6. 'Verified effective on ... by ...' (green)")

# ---------------- 7. a new NCR since the actions were complete ----------------
PAIR2 = complete_capa("PIN")
NAME2 = PAIR2[1]
close(NAME2)
frappe.db.set_value(CAPA, NAME2, "verification_due_on", today)
again = ncr(frappe.db.get_value(CAPA, NAME2, "item"), "Major")
check(frappe.db.get_value(NCR, again.name, "capa") == NAME2, "7. the new Major NCR joined the CAPA awaiting verification")
row = find(show(NAME2), "Effectiveness check ")
check(again.name in row.get("text") and row.get("colour") == "red", "7. the panel names it: '... since the actions were completed: ... - not effective' (red)")
refused("7. Effective is refused while that NCR stands", lambda: frappe.call(VERIFY, capa=NAME2, result="Effective", remarks=REMARKS), again.name)

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
