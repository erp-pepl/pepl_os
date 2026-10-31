# PEPL OS v0.42.3 - Check 42 rev 3: C3a-B1 the shift-entry kiosk and the foreman view - code + PIN (wrong PINs lock the
# code), the operator's own entry saved from the kiosk rows (with the same help as the Desk), a tool-change photo
# taken on the kiosk, submit, read-only afterwards, and the foreman's board. Rev 2 (v0.42.2): a kiosk login opens
# the kiosk after logging in (Default App pepl_os -> /kiosk, PEPL Kiosk role home page = kiosk). Rev 3 (v0.42.3):
# times come back to the page as 08:00, not 8:00: (CI #45).
# Runs on 0.42.3 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below is undone at the
# end, except two things outside the database: the tiny test photo file (a few hundred bytes in private/files) and the
# kiosk's short-lived lock / session entries in the cache (they expire by themselves; the locked test code is unique).
# Then try the pages in the browser: see the steps in the chat (kiosk login, /kiosk?machine=..., /foreman).
VERSION = "0.42.3"
PARAMS = "PEPL System Parameters"
SPR = "PEPL Shift Production Entry"
K = "pepl_os.pepl_production.kiosk."
PHOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGM8ISfHwMDAxMDAwMDAAAANBAEIfXHKZgAAAABJRU5ErkJggg=="
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


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(frappe.db.get_value("Role", "PEPL Kiosk", "desk_access") == 0 and bool(frappe.db.exists("Role Profile", "PEPL Kiosk")), "1. role 'PEPL Kiosk' (no Desk access) and Role Profile 'PEPL Kiosk' exist")
meta = frappe.get_meta(PARAMS)
check(all(meta.get_field(f) for f in ("custom_kiosk_pin_tries", "custom_kiosk_lock_minutes", "custom_kiosk_session_minutes")), "1. System Parameters > Production has Kiosk: Wrong PIN Tries / Lock Minutes / Session Minutes")
params = frappe.get_doc(PARAMS)
print("INFO  this site: wrong PIN tries " + str(params.custom_kiosk_pin_tries) + ", lock " + str(params.custom_kiosk_lock_minutes) + " min, session " + str(params.custom_kiosk_session_minutes) + " min")
params.custom_kiosk_pin_tries = 3
params.custom_spr_tool_photo_required = 1
params.custom_spr_max_unaccounted_minutes = 15
params.save()
settings = frappe.get_doc("Manufacturing Settings")
settings.disable_capacity_planning = 1
settings.overproduction_percentage_for_work_order = 0
settings.save()

# ---------------- 2. a machine, a shift, an operator, a Job Card ----------------
DAY = "CHK42 Day " + RUN
MILL = "CHK42 MILL-01 " + RUN
OP = "CHK42-OP-" + RUN
LOCKED = "CHK42-OP2-" + RUN  # used only to show the lock
NO_LOAD = "CHK42 No Load " + RUN
pin = "1" * int(frappe.db.get_single_value(PARAMS, "custom_operator_pin_digits") or 4)
frappe.get_doc({"doctype": "PEPL Shift", "shift_name": DAY, "start_time": "08:00:00", "end_time": "16:30:00", "break_minutes": 30}).insert()
frappe.get_doc({"doctype": "Workstation", "workstation_name": MILL}).insert()
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": OP, "operator_name": "Ramesh " + RUN, "pin": pin}).insert()
frappe.get_doc({"doctype": "PEPL Operator", "employee_code": LOCKED, "operator_name": "Suresh " + RUN, "pin": pin}).insert()
frappe.get_doc({"doctype": "PEPL Downtime Category", "category_name": NO_LOAD, "stop_type": "Planned", "is_breakdown": 0}).insert()
FG = frappe.get_doc({"doctype": "Item", "item_code": "CHK42-FG-" + RUN, "item_name": "CHK42 FG " + RUN, "item_group": "Finished Goods", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0}).insert().name
BO = frappe.get_doc({"doctype": "Item", "item_code": "CHK42-BO-" + RUN, "item_name": "CHK42 Bought-out " + RUN, "item_group": "Bought-Out Components", "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0, "valuation_rate": 10}).insert().name
MILLING = "CHK42 Milling " + RUN
frappe.get_doc({"doctype": "Operation", "name": MILLING, "workstation": MILL}).insert()
bom = frappe.get_doc({"doctype": "BOM", "item": FG, "company": company, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 1,
                      "currency": frappe.db.get_value("Company", company, "default_currency"), "items": [{"item_code": BO, "qty": 1, "rate": 10}],
                      "operations": [{"operation": MILLING, "workstation": MILL, "time_in_mins": 6}]}).insert()
bom.submit()
wo = frappe.get_doc({"doctype": "Work Order", "production_item": FG, "bom_no": bom.name, "qty": 40, "stock_uom": "Nos", "company": company,
                     "skip_transfer": 1, "fg_warehouse": wh("FG Stores"), "planned_start_date": frappe.utils.now(), "transfer_material_against": "Work Order"})
wo.get_items_and_operations_from_bom()
wo.insert()
wo.submit()
CARD = frappe.get_all("Job Card", filters={"work_order": wo.name}, pluck="name")[0]
ctx = frappe.call(K + "kiosk_context", machine=MILL)
check(ctx.get("machine") == MILL and DAY in [s.get("name") for s in ctx.get("shifts")], "2. the kiosk page for " + MILL + " offers shift " + DAY + " (current shift here: " + str(ctx.get("shift")) + ")")

# ---------------- 3. code + PIN ----------------
refused("3. a wrong PIN is refused without saying which part was wrong", lambda: frappe.call(K + "sign_in", machine=MILL, shift=DAY, posting_date=today, employee_code=LOCKED, pin="9876"), "not recognised")
refused("3. an unknown code gets the very same message", lambda: frappe.call(K + "sign_in", machine=MILL, shift=DAY, posting_date=today, employee_code="NO-SUCH-" + RUN, pin=pin), "not recognised")
refused("3. second wrong PIN for " + LOCKED, lambda: frappe.call(K + "sign_in", machine=MILL, shift=DAY, posting_date=today, employee_code=LOCKED, pin="9876"), "not recognised")
refused("3. third wrong PIN (the code locks now)", lambda: frappe.call(K + "sign_in", machine=MILL, shift=DAY, posting_date=today, employee_code=LOCKED, pin="9876"), "not recognised")
refused("3. locked: even the right PIN waits (Kiosk: Lock Minutes)", lambda: frappe.call(K + "sign_in", machine=MILL, shift=DAY, posting_date=today, employee_code=LOCKED, pin=pin), "Too many wrong PINs")
out = frappe.call(K + "sign_in", machine=MILL, shift=DAY, posting_date=today, employee_code=OP, pin=pin)
TOKEN = out.get("token")
check(bool(TOKEN) and out.get("operator") == OP and out.get("entry") is None and CARD in [c.get("name") for c in out.get("job_cards")], "3. right code + PIN: signed in as " + str(out.get("operator_name")) + ", no entry yet, Job Card " + CARD + " offered")

# ---------------- 4. the entry from the kiosk ----------------
out = frappe.call(K + "save_entry", token=TOKEN, production=[{"job_card": CARD, "from_time": "08:00", "to_time": "12:00", "good_qty": 38, "rejected_qty": 2, "rejection_reason": "Undersize"}],
            tool_changes=[{"change_time": "10:00", "tool_description": "Insert CNMG 120408", "reason": "Worn out", "photo": PHOTO}])
ENTRY = out.get("entry")
print("INFO  entry " + str(ENTRY) + " - help shown: " + " | ".join(r.get("text") for r in out.get("aids") or []))
doc = frappe.get_doc(SPR, ENTRY)
check(doc.docstatus == 0 and doc.operator == OP and doc.workstation == MILL and doc.shift == DAY and doc.total_good_qty == 38, "4. saved as draft " + str(ENTRY) + " for " + OP + " on " + MILL + ", " + DAY + ": 38 good, 2 rejected")
photo = (out.get("tool_changes") or [{}])[0].get("photo") or ""
check(photo.startswith("/private/files/") and bool(frappe.db.exists("File", {"file_url": photo, "attached_to_name": ENTRY})), "4. the tool-change photo taken on the kiosk is attached to the entry (" + photo + ")")
check(any("gap" in r.get("text") for r in out.get("aids") or []), "4. the kiosk shows the same help as the Desk form (the afternoon is a gap)")
out = frappe.call(K + "save_entry", token=TOKEN, production=[{"job_card": CARD, "from_time": "08:00", "to_time": "12:00", "good_qty": 38, "rejected_qty": 2, "rejection_reason": "Undersize"}],
            downtime=[{"downtime_category": NO_LOAD, "from_time": "12:00", "to_time": "16:30"}],
            tool_changes=[{"change_time": "10:00", "tool_description": "Insert CNMG 120408", "reason": "Worn out", "photo": photo}])
check(out.get("entry") == ENTRY and len(frappe.get_doc(SPR, ENTRY).downtime) == 1, "4. saving again updates the same entry (stop 12:00-16:30 added), no second entry")
again = frappe.call(K + "sign_in", machine=MILL, shift=DAY, posting_date=today, employee_code=OP, pin=pin)
check(again.get("entry") == ENTRY and len(again.get("production")) == 1, "4. signing in again brings back the draft")
times = [again.get("production")[0].get("from_time"), again.get("production")[0].get("to_time")] + [r.get("from_time") for r in again.get("downtime")]
shift_times = [[x.get("start"), x.get("end")] for x in ctx.get("shifts") if x.get("name") == DAY][0]
check(times == ["08:00", "12:00", "12:00"] and shift_times == ["08:00", "16:30"], "4. times come back to the page as two-digit clock times: rows " + ", ".join(str(x) for x in times) + "; shift " + "-".join(str(x) for x in shift_times))

# ---------------- 5. submit, then read-only ----------------
out = frappe.call(K + "submit_entry", token=TOKEN)
check(out.get("docstatus") == 1 and frappe.db.get_value(SPR, ENTRY, "docstatus") == 1, "5. submitted from the kiosk: " + str(ENTRY))
refused("5. a submitted entry cannot be changed from the kiosk", lambda: frappe.call(K + "save_entry", token=TOKEN, production=[]), "already submitted")
frappe.call(K + "sign_out", token=TOKEN)
refused("5. after Sign out the session is gone", lambda: frappe.call(K + "save_entry", token=TOKEN, production=[]), "session has ended")

# ---------------- 6. foreman view ----------------
board = frappe.call(K + "foreman_board", posting_date=today, shift=DAY)
mine = [r for r in board.get("rows") or [] if r.get("machine") == MILL]
print("INFO  foreman board " + today + " " + DAY + ": " + str(board.get("submitted")) + " submitted, " + str(board.get("drafts")) + " draft, " + str(board.get("missing")) + " missing")
check(bool(mine) and mine[0].get("state") == "Submitted" and mine[0].get("good") == "38" and ENTRY in mine[0].get("entries"), "6. the foreman board shows " + MILL + ": Submitted, 38 good, entry " + str(ENTRY))

# ---------------- 7. a kiosk login opens the kiosk after logging in ----------------
check(frappe.db.get_value("Role", "PEPL Kiosk", "home_page") == "kiosk", "7. the PEPL Kiosk role's home page is the kiosk")
tablet = frappe.get_doc({"doctype": "User", "email": "chk42-tablet-" + RUN + "@example.com", "first_name": "CHK42 Tablet " + RUN, "send_welcome_email": 0,
                         "roles": [{"role": "PEPL Kiosk"}]}).insert()
tablet_values = frappe.db.get_value("User", tablet.name, ["user_type", "default_app"], as_dict=True)
check(tablet_values.user_type == "Website User" and tablet_values.default_app == "pepl_os", "7. a new kiosk login is a Website User whose Default App is pepl_os (its page: /kiosk)")
kiosk_users = [u for u in frappe.get_all("Has Role", filters={"role": "PEPL Kiosk", "parenttype": "User"}, pluck="parent") if frappe.db.get_value("User", u, "user_type") == "Website User"]
missing = [u for u in kiosk_users if not frappe.db.get_value("User", u, "default_app")]
print("INFO  kiosk logins on this site: " + (", ".join(u + " -> " + str(frappe.db.get_value("User", u, "default_app")) for u in kiosk_users) or "none"))
check(not missing, "7. every kiosk login on this site opens the kiosk after logging in" + (" - not yet: " + ", ".join(missing) if missing else ""))

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved (the test photo file and cache entries are harmless).")
