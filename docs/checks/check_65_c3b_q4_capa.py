# PEPL OS v0.65.0 - Check 65 rev 2: C3b-Q4 Corrective and Preventive Action - a Critical NCR raises a CAPA by itself, a
# repeated Major NCR on the same item raises one CAPA for all of them, a later NCR joins the open CAPA, and a CAPA
# closes only with the five-why, the root cause, a Corrective Action and every action done.
# Rev 2 (18 Nov 2026): the "old" Major NCR is dated 150 days back. Rev 1 dated it 120 days back, which is exactly 90 days
# before the 30-day-old NCR - inside the window, as the rule says - so the check, not the app, was wrong.
# Runs on 0.65.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes it makes, is undone at the end. Afterwards look at the screens in the browser (see chat).
VERSION = "0.65.0"
PARAMS = "PEPL System Parameters"
NCR = "PEPL NCR"
CAPA = "PEPL CAPA"
MOD = "pepl_os.pepl_quality.capa"
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


def set_params(values):
    doc = frappe.get_doc(PARAMS)
    for field in values:
        doc.set(field, values[field])
    doc.save()


def item(code):
    return frappe.get_doc({"doctype": "Item", "item_code": code + "-" + RUN, "item_name": code + " " + RUN, "item_group": "Bought-Out Components",
                           "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert().name


def ncr(item_code, severity, days_ago):
    return frappe.get_doc({"doctype": NCR, "source": "In-Process", "severity": severity, "item": item_code, "qty_affected": 3,
                           "raised_on": frappe.utils.add_days(today, -days_ago), "defect_description": "CHK65 " + severity + " burr"}).insert().name


def capa_of(ncr_name):
    return frappe.db.get_value(NCR, ncr_name, "capa")


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.db.exists("DocType", CAPA)) and bool(frappe.db.exists("DocType", "PEPL CAPA Action")) and bool(frappe.get_meta(NCR).get_field("capa")),
      "1. PEPL CAPA with its NCR and Action tables exists; the NCR has a 'CAPA' field")
check(bool(frappe.get_meta(PARAMS).get_field("custom_capa_repeat_count")),
      "1. System Parameters > Quality > CAPA: repeat count " + str(frappe.db.get_single_value(PARAMS, "custom_capa_repeat_count"))
      + " in " + str(frappe.db.get_single_value(PARAMS, "custom_capa_repeat_window_days")) + " days, whys required "
      + str(frappe.db.get_single_value(PARAMS, "custom_capa_whys_required")) + ", target " + str(frappe.db.get_single_value(PARAMS, "custom_capa_target_days")) + " days")

# ---------------- 2. settings for this run ----------------
values = {"enable_operational_todos": 1, "custom_capa_repeat_count": 2, "custom_capa_repeat_window_days": 90, "custom_capa_whys_required": 5,
          "custom_capa_target_days": 30}
if not frappe.db.get_single_value(PARAMS, "custom_quality_notification_owner"):
    values["custom_quality_notification_owner"] = "Administrator"
set_params(values)
OWNER = frappe.db.get_single_value(PARAMS, "custom_quality_notification_owner")
refused("2. a repeat count of 1 is refused", lambda: set_params({"custom_capa_repeat_count": 1}), "CAPA: Repeat Major Count")

# ---------------- 3. a Critical NCR raises a CAPA ----------------
GEAR = item("CHK65-GEAR")
crit = ncr(GEAR, "Critical", 0)
c1 = capa_of(crit)
doc = frappe.get_doc(CAPA, c1) if c1 else None
print("INFO  Critical " + crit + " -> " + str(c1) + ": " + (doc.problem_statement if doc else ""))
check(bool(doc) and doc.trigger == "Critical NCR" and doc.status == "Open" and [r.ncr for r in doc.ncrs] == [crit],
      "3. Critical NCR " + crit + " raised CAPA " + str(c1) + " (Raised For: Critical NCR, Open)")
check(bool(doc) and doc.capa_owner == OWNER and str(doc.target_date) == str(frappe.utils.add_days(today, 30)),
      "3. owner " + str(OWNER) + ", target date in 30 days (" + (str(doc.target_date) if doc else "-") + ")")
todo = frappe.get_all("ToDo", filters={"reference_type": CAPA, "reference_name": c1, "status": "Open"}, fields=["allocated_to", "priority"])
check(len(todo) == 1 and todo[0].allocated_to == OWNER and todo[0].priority == "High", "3. the owner has a High ToDo for it")

# ---------------- 4. repeated Major NCRs ----------------
SHAFT = item("CHK65-SHAFT")
old = ncr(SHAFT, "Major", 150)  # 120 days before "first": outside the 90-day window
first = ncr(SHAFT, "Major", 30)
check(not capa_of(old) and not capa_of(first), "4. a Major NCR 30 days ago (and one 150 days ago, 120 days before it - outside 90): no CAPA yet")
second = ncr(SHAFT, "Major", 0)
c2 = capa_of(second)
rows = [r.ncr for r in frappe.get_doc(CAPA, c2).ncrs] if c2 else []
check(bool(c2) and frappe.db.get_value(CAPA, c2, "trigger") == "Repeat Major" and sorted(rows) == sorted([first, second]) and capa_of(first) == c2,
      "4. the second Major within 90 days raised CAPA " + str(c2) + " for both (" + ", ".join(rows) + "); the 150-day one is left out")
minor = ncr(SHAFT, "Minor", 0)
check(not capa_of(minor), "4. a Minor NCR never joins a CAPA")
third = ncr(SHAFT, "Major", 0)
check(capa_of(third) == c2 and len(frappe.get_doc(CAPA, c2).ncrs) == 3, "4. a third Major joins the open CAPA " + str(c2) + " (3 NCRs)")

# ---------------- 5. five-why, actions, closing ----------------
cap = frappe.get_doc(CAPA, c1)
cap.status = "Closed"
refused("5. closing an empty CAPA is refused", lambda: cap.save(), "0 of 5 whys answered; no root cause; no Corrective Action")
cap = frappe.get_doc(CAPA, c1)
cap.containment = "CHK65: 40 gears on hand sorted, 3 rejected"
cap.why_1 = "Tooth profile out of tolerance"
cap.why_2 = "Hob worn"
cap.why_3 = "Hob changed by count, not by wear"
cap.root_cause = "No hob wear check in the setter's routine"
cap.append("actions", {"action_type": "Corrective Action", "description": "Replace the hob", "done_on": today})
cap.append("actions", {"action_type": "Preventive Action", "description": "Add hob wear check to the setup sheet"})
cap.save()
state = frappe.call(MOD + ".get_capa_state", capa=c1)
print("INFO  " + c1 + ": " + str(cap.five_why_status) + "; before closing: " + "; ".join(state.get("closing_gaps") or []))
check(cap.status == "In Progress" and cap.five_why_status == "3 of 5 whys, root cause given", "5. work started -> In Progress; five-why 3 of 5")
check(state.get("closing_gaps") == ["five-why: 3 of 5 whys answered", "1 action(s) not done"], "5. the form says what still stops closing")
cap = frappe.get_doc(CAPA, c1)
cap.why_4 = "Setter not trained on hob wear"
cap.why_5 = "No standard for hob life"
cap.actions[1].done_on = today
cap.status = "Closed"
cap.save()
check(cap.status == "Closed" and bool(cap.closed_on), "5. with five whys, the root cause and both actions done it closes")
check(not frappe.get_all("ToDo", filters={"reference_type": CAPA, "reference_name": c1, "status": "Open"}), "5. the owner's ToDo closed by itself")
cap = frappe.get_doc(CAPA, c1)
cap.root_cause = "changed"
refused("5. a closed CAPA cannot be changed", lambda: cap.save(), "cannot be changed")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
