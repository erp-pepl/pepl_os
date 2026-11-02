"""Build docs/checks/check_all_c3a.py (rev 4): every Cycle 3a check (23-49) from one System Console run.

Rev 1 ran all checks inside the System Console web request; Frappe Cloud cuts a web request off at 120 s (504), and
the System Console only shows output when the request ends, so nothing came back.

Rev 2: the System Console script only puts the checks on the background queue ("long", no 120 s limit) and returns
at once. The background job runs each check unchanged (indented inside try/except at module level, so its scope is
the same as when it runs alone), rolls everything back after each check, and then writes the results to a Note
"PEPL Check ALL <time>" and commits only that Note. The Note is updated after every check, so progress is visible.
"""

import json
import pathlib
import sys

# Usage (WSL, from the app folder):  python3 docs/checks/build_check_all.py . docs/checks/check_all_c3a.py

repo = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
checks = sorted(repo.glob("docs/checks/check_[2-4][0-9]_c3a_*.py"))
checks = [c for c in checks if 23 <= int(c.name.split("_")[1]) <= 49]
assert len(checks) == 27, len(checks)

# ------------------------------------------------------------------ inner script (runs in the background job)
inner_head = """# PEPL OS - Check ALL (Cycle 3a), background part. Started from check_all_c3a.py; do not run this by hand.
FIRST = int("ALL_FIRST_VALUE")
LAST = int("ALL_LAST_VALUE")
ALL_TITLE = "ALL_TITLE_VALUE"
ALL_STARTED = frappe.utils.now_datetime()
ALL_RESULTS = []
ALL_VERSION = str(frappe.db.get_value("Installed Application", {"app_name": "pepl_os"}, "app_version"))


def all_seconds(since):
    return round(frappe.utils.time_diff_in_seconds(frappe.utils.now_datetime(), since), 1)


def all_note(status):
    lines = [ALL_TITLE, "Status: " + status, "Site pepl_os version: " + ALL_VERSION, "Checks chosen: " + str(FIRST) + " to " + str(LAST), ""]
    bad = []
    for row in ALL_RESULTS:
        lines.append(("OK    " if not row[3] else "FAIL  ") + "Check " + str(row[0]) + ": " + str(row[2]) + " passed, " + str(row[3]) + " failed  (" + str(row[4]) + " s)  " + row[1])
        for label in row[5]:
            lines.append("          FAIL  " + label)
        if row[3]:
            bad.append(str(row[0]))
    lines.append("")
    lines.append("RESULT ALL: " + str(len(ALL_RESULTS)) + " checks run, " + str(sum(r[2] for r in ALL_RESULTS)) + " passed, " + str(sum(r[3] for r in ALL_RESULTS)) + " failed, in " + str(all_seconds(ALL_STARTED)) + " s")
    if bad:
        lines.append("Checks with a FAIL: " + ", ".join(bad) + " - run that check file on its own and send its full output.")
    lines.append("Every check was undone after it ran; only this Note is saved.")
    html = "<pre>" + frappe.utils.escape_html("\\n".join(lines)) + "</pre>"
    name = frappe.db.get_value("Note", {"title": ALL_TITLE}, "name")
    if name:
        frappe.db.set_value("Note", name, "content", html)
    else:
        frappe.get_doc({"doctype": "Note", "title": ALL_TITLE, "public": 0, "content": html}).insert()
    frappe.db.commit()


all_note("RUNNING")

"""

parts = [inner_head]
for path in checks:
	number = int(path.name.split("_")[1])
	title = path.name[:-3]
	body = path.read_text(encoding="utf-8").rstrip("\n").split("\n")
	assert not any("\t" in line for line in body), path
	assert not any('"""' in line or "'''" in line for line in body), path
	indented = "\n".join(("        " + line) if line.strip() else "" for line in body)
	parts.append(f'''# =====================================================================================================
# Check {number}: {title}
# =====================================================================================================
if FIRST <= {number} <= LAST:
    print("CHECK {number}  ({title})")
    ALL_T = frappe.utils.now_datetime()
    passed = []
    failed = []
    try:
{indented}
        ALL_RESULTS.append([{number}, "{title}", len(passed), len(failed), all_seconds(ALL_T), list(failed)])
    except Exception as all_error:
        all_text = frappe.utils.strip_html(str(all_error))[:400]
        ALL_RESULTS.append([{number}, "{title}", len(passed), len(failed) + 1, all_seconds(ALL_T), list(failed) + ["CRASHED: " + all_text]])
    frappe.db.rollback()
    all_note("RUNNING - Check {number} done")

''')
parts.append('all_note("FINISHED")\n')
inner = "".join(parts)

# ------------------------------------------------------------------ outer script (pasted into the System Console)
outer = [
	"""# PEPL OS v0.51.0 - Check ALL rev 4 (Cycle 3a): runs Checks 23 to 49 (unchanged) in the background and writes the
# results to a Note. System Console, Type = Python. Leave "Commit" UNTICKED.
#
# rev 4: the job is packed with json.dumps (frappe.as_json is not offered in the System Console).
# rev 3: the Note title is made from frappe.utils.now() (rev 2 used strftime, which the System Console refuses).
# Why rev 2: Frappe Cloud stops a web request after 120 seconds, and the System Console only shows its output when
# the request ends, so running all checks inside the console showed nothing. This script only queues the checks
# (it returns in a second); a background worker runs them with no time limit.
# Each check is undone (rollback) as soon as it has run, so every check starts from the untouched site, exactly
# as when it is run on its own. The only thing saved is the result Note.
#
# Choose which checks to run (both included). Default: 29 to 49 (23 to 28 already passed on the demo site).
FIRST = 29
LAST = 49

ALL_TITLE = "PEPL Check ALL " + frappe.utils.now()[:19]
INNER_LINES = [
"""
]
for line in inner.split("\n"):
	outer.append("    " + json.dumps(line) + ",\n")
outer.append("""]
if FIRST < 23 or LAST > 49 or FIRST > LAST:
    print("FIRST and LAST must be between 23 and 49, FIRST not after LAST. Nothing was queued.")
else:
    inner = "\\n".join(INNER_LINES)
    inner = inner.replace("ALL_FIRST_VALUE", str(FIRST), 1).replace("ALL_LAST_VALUE", str(LAST), 1).replace("ALL_TITLE_VALUE", ALL_TITLE, 1)
    frappe.enqueue(
        "frappe.desk.doctype.system_console.system_console.execute_code",
        queue="long",
        timeout=3600,
        doc=json.dumps({"doctype": "System Console", "type": "Python", "commit": 0, "console": inner}),
    )
    print("QUEUED: Checks " + str(FIRST) + " to " + str(LAST) + " are now running in the background.")
    print("")
    print("Results go to the Note:  " + ALL_TITLE)
    print("Open it: search bar -> type  Note List  -> open that Note (refresh the Note to see progress).")
    print("Its first lines say  Status: RUNNING - Check NN done  while it runs and  Status: FINISHED  at the end.")
    print("If no Note with this title appears within 3 minutes, the background workers are not running: tell me.")
""")
out.write_text("".join(outer), encoding="utf-8")
print(out, out.stat().st_size, "bytes,", len(checks), "checks")
