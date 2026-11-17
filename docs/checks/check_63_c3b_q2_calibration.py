# PEPL OS v0.63.0 - Check 63: C3b-Q2 instruments and calibration - the PEPL Instrument master and its Calibration
# Records (dates, certificate and state taken from the latest submitted record; Fail = Out of Service), the daily
# due / overdue alert to Quality (QA-CAL-DUE), and the Calibration Gate that stops a QC Inspection whose reading was
# taken with an instrument out of calibration.
# Runs on 0.63.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below, including the
# System Parameters changes it makes, is undone at the end. Afterwards look at the screens in the browser (see chat).
VERSION = "0.63.0"
PARAMS = "PEPL System Parameters"
INSTRUMENT = "PEPL Instrument"
RECORD = "PEPL Calibration Record"
QI = "Quality Inspection"
PR = "Purchase Receipt"
CAL = "pepl_os.pepl_quality.calibration"
DUE_RULE = "QA-CAL-DUE"
GATE_RULE = "QA-CAL-GATE"
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
company = (
	frappe.db.get_single_value("Global Defaults", "default_company")
	or frappe.get_all("Company", pluck="name", limit=1)[0]
)


def set_params(values):
	doc = frappe.get_doc(PARAMS)
	for field in values:
		doc.set(field, values[field])
	doc.save()


def instrument(code, frequency, status):
	return (
		frappe.get_doc(
			{
				"doctype": INSTRUMENT,
				"instrument_id": code + "-" + RUN,
				"instrument_name": "CHK63 " + code + " " + RUN,
				"instrument_type": "Vernier Caliper",
				"status": status,
				"calibration_frequency_days": frequency,
				"measuring_range": "0 - 150 mm",
				"least_count": "0.01 mm",
			}
		)
		.insert()
		.name
	)


def record(name, days_ago, result, certificate_no, errors):
	doc = frappe.get_doc(
		{
			"doctype": RECORD,
			"instrument": name,
			"calibration_date": frappe.utils.add_days(today, -days_ago),
			"result": result,
			"certificate_no": certificate_no,
			"errors_found": errors,
			"agency": "CHK63 NABL Lab",
		}
	).insert()
	doc.submit()
	return doc


def todo(name):
	rows = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": INSTRUMENT,
			"reference_name": name,
			"status": "Open",
			"description": ["like", "%" + DUE_RULE + "%"],
		},
		fields=["priority", "description", "allocated_to"],
	)
	return rows[0] if rows else None


def inst(name):
	return frappe.db.get_value(
		INSTRUMENT,
		name,
		[
			"status",
			"calibration_state",
			"days_to_due",
			"last_calibrated_on",
			"calibration_due_on",
			"last_certificate_no",
			"last_calibration_record",
		],
		as_dict=True,
	)


# ---------------- 1. installed ----------------
apps = {
	a.app_name: a.app_version
	for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])
}
check(
	version_parts(apps.get("pepl_os")) >= version_parts(VERSION),
	"1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")",
)
check(
	bool(frappe.db.exists("DocType", INSTRUMENT)) and bool(frappe.db.exists("DocType", RECORD)),
	"1. PEPL Instrument and PEPL Calibration Record exist",
)
pmeta = frappe.get_meta(PARAMS)
check(
	bool(pmeta.get_field("custom_calibration_alert_days"))
	and bool(pmeta.get_field("custom_calibration_gate_mode")),
	"1. System Parameters > Quality: Calibration: Alert Days ("
	+ str(frappe.db.get_single_value(PARAMS, "custom_calibration_alert_days"))
	+ ") and Calibration Gate ("
	+ str(frappe.db.get_single_value(PARAMS, "custom_calibration_gate_mode"))
	+ ")",
)
check(
	bool(frappe.get_meta("Quality Inspection Reading").get_field("custom_instrument")),
	"1. every QC Inspection reading has an 'Instrument' column",
)
check(
	CAL + ".daily_calibration_alerts" in (frappe.get_hooks("scheduler_events").get("daily") or []),
	"1. the daily calibration alert job is scheduled",
)

# ---------------- 2. settings for this run ----------------
values = {
	"custom_calibration_alert_days": 15,
	"custom_calibration_gate_mode": "Hard Block",
	"enable_operational_todos": 1,
	"custom_enforce_override_reason": 1,
	"custom_incoming_qc_gate_mode": "Advisory",
}
if not frappe.db.get_single_value(PARAMS, "custom_quality_notification_owner"):
	values["custom_quality_notification_owner"] = "Administrator"
set_params(values)
OWNER = frappe.db.get_single_value(PARAMS, "custom_quality_notification_owner")
refused(
	"2. Alert Days 400 is refused",
	lambda: set_params({"custom_calibration_alert_days": 400}),
	"Calibration: Alert Days",
)
refused(
	"2. a frequency of 0 days is refused",
	lambda: instrument("CHK63-ZERO", 0, "Active"),
	"Calibration Frequency",
)

# ---------------- 3. a new instrument: never calibrated ----------------
NEW = instrument("CHK63-VC", 180, "Active")
i = inst(NEW)
t = todo(NEW)
check(i.calibration_state == "Never Calibrated", "3. new instrument " + NEW + " is 'Never Calibrated'")
check(
	bool(t) and t.priority == "High" and t.allocated_to == OWNER,
	"3. Quality ("
	+ str(OWNER)
	+ ") has a High ToDo: "
	+ (t.description.split("\n")[-1][:150] if t else "none"),
)

# ---------------- 4. a passed calibration ----------------
refused(
	"4. a passed calibration without a certificate is refused",
	lambda: record(NEW, 10, "Pass", None, None),
	"certificate",
)
refused("4. a calibration dated tomorrow is refused", lambda: record(NEW, -1, "Pass", "C-1", None), "future")
first = record(NEW, 10, "Pass", "NABL-CHK63-1", None)
i = inst(NEW)
print(
	"INFO  "
	+ first.name
	+ ": calibrated "
	+ str(i.last_calibrated_on)
	+ ", due "
	+ str(i.calibration_due_on)
	+ ", "
	+ str(i.days_to_due)
	+ " days, "
	+ str(i.calibration_state)
)
check(
	str(first.next_due_on) == str(frappe.utils.add_days(today, 170)),
	"4. next due = calibration date + 180 days = " + str(first.next_due_on),
)
check(
	i.calibration_state == "Valid"
	and i.days_to_due == 170
	and i.last_certificate_no == "NABL-CHK63-1"
	and i.last_calibration_record == first.name,
	"4. the instrument took the record's dates and certificate: Valid, 170 days to due",
)
check(not todo(NEW), "4. the Quality ToDo closed by itself")

# ---------------- 5. due soon, overdue, fail, cancel ----------------
SOON = instrument("CHK63-MIC", 30, "Active")
record(SOON, 20, "Pass", "NABL-CHK63-2", None)
LATE = instrument("CHK63-DIAL", 30, "Active")
record(LATE, 40, "Pass", "NABL-CHK63-3", None)
check(
	inst(SOON).calibration_state == "Due Soon" and bool(todo(SOON)) and todo(SOON).priority == "Medium",
	"5. due in 10 days (window 15) -> Due Soon, Medium ToDo",
)
check(
	inst(LATE).calibration_state == "Overdue"
	and inst(LATE).days_to_due == -10
	and bool(todo(LATE))
	and todo(LATE).priority == "High",
	"5. due 10 days ago -> Overdue (-10), High ToDo: "
	+ (todo(LATE).description.split("\n")[-1][:120] if todo(LATE) else "none"),
)
BAD = instrument("CHK63-BORE", 365, "Active")
refused(
	"5. a failed calibration without 'Errors Found' is refused",
	lambda: record(BAD, 2, "Fail", None, None),
	"Errors Found",
)
record(BAD, 2, "Fail", None, "Anvil worn, reads 0.03 mm high")
check(
	inst(BAD).status == "Out of Service" and inst(BAD).calibration_state == "Not in Use",
	"5. a Fail puts " + BAD + " Out of Service ('Not in Use')",
)
record(BAD, 1, "Pass after Adjustment", "NABL-CHK63-4", "Anvil lapped")
check(
	inst(BAD).status == "Active" and inst(BAD).calibration_state == "Valid",
	"5. a Pass after Adjustment brings it back to Active, Valid",
)
second = record(NEW, 1, "Pass", "NABL-CHK63-5", None)
frappe.get_doc(RECORD, second.name).cancel()
check(
	inst(NEW).last_calibration_record == first.name,
	"5. cancelling " + second.name + " goes back to " + first.name,
)
run = frappe.call(CAL + ".run_calibration_alerts_now") or {}
check(
	"instrument(s) due" in str(run.get("message")),
	"5. 'run now' of the daily check -> " + str(run.get("message")),
)

# ---------------- 6. the Calibration Gate on a QC Inspection ----------------
PARAM = "CHK63 Pin Diameter " + RUN
frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": PARAM}).insert()
PLAN = (
	frappe.get_doc(
		{
			"doctype": "Quality Inspection Template",
			"quality_inspection_template_name": "CHK63 Pin Plan " + RUN,
			"item_quality_inspection_parameter": [
				{"specification": PARAM, "numeric": 1, "min_value": 9.9, "max_value": 10.1}
			],
		}
	)
	.insert()
	.name
)
values = {
	"doctype": "Item",
	"item_code": "CHK63-PIN-" + RUN,
	"item_name": "CHK63 Pin " + RUN,
	"item_group": "Bought-Out Components",
	"stock_uom": "Nos",
	"is_stock_item": 1,
	"is_sales_item": 0,
	"is_purchase_item": 1,
	"valuation_rate": 10,
	"quality_inspection_template": PLAN,
}
if frappe.db.exists("DocType", "GST HSN Code"):
	codes = [
		c
		for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "7318%"]}, pluck="name", limit=20)
		if len(c) == 8
	]
	if codes:
		values["gst_hsn_code"] = codes[0]
PIN = frappe.get_doc(values).insert().name
frappe.db.set_value("Item", PIN, "inspection_required_before_purchase", 1)
SUPPLIER = frappe.get_doc({"doctype": "Supplier", "supplier_name": "CHK63 Pins " + RUN}).insert().name
frappe.db.set_value("Supplier", SUPPLIER, "custom_approval_state", "Approved")
STORE = frappe.db.get_value(
	"Warehouse", {"company": company, "warehouse_name": "Bought-Out Stores", "is_group": 0}, "name"
)


def inspection(instrument_name):
	pr = frappe.get_doc(
		{
			"doctype": PR,
			"supplier": SUPPLIER,
			"company": company,
			"posting_date": today,
			"items": [{"item_code": PIN, "qty": 10, "received_qty": 10, "rate": 10, "warehouse": STORE}],
		}
	).insert()
	qi = frappe.get_doc(QI, pr.items[0].quality_inspection)
	qi.readings[0].reading_1 = "10.0"
	qi.readings[0].custom_instrument = instrument_name
	qi.save()
	return qi.name


late_qi = inspection(LATE)
check(not frappe.call(CAL + ".calibration_gate_check", name=late_qi), "6. Hard Block never offers a reason")
refused(
	"6. Hard Block: a reading taken with the overdue " + LATE + " is refused",
	lambda: frappe.get_doc(QI, late_qi).submit(),
	"overdue for calibration",
)
set_params({"custom_calibration_gate_mode": "Soft Block"})
gate = frappe.call(CAL + ".calibration_gate_check", name=late_qi) or {}
check(
	gate.get("rule_code") == GATE_RULE,
	"6. Soft Block: the form asks for a reason -> " + str(gate.get("message"))[:160],
)
refused(
	"6. Soft Block: submit without a reason is refused",
	lambda: frappe.get_doc(QI, late_qi).submit(),
	GATE_RULE,
)
frappe.call(
	"pepl_os.common.overrides.record_override",
	rule_code=GATE_RULE,
	reference_doctype=QI,
	reference_name=late_qi,
	message=gate.get("message") or "",
	reason="Only bore gauge available on night shift, recheck tomorrow",
)
done = frappe.get_doc(QI, late_qi)
done.submit()
check(
	done.docstatus == 1
	and bool(frappe.db.exists("PEPL Override Log", {"rule_code": GATE_RULE, "reference_name": late_qi})),
	"6. with a reason it submits; the reason is in the Override Log (" + GATE_RULE + ")",
)
good_qi = inspection(NEW)
check(
	not frappe.call(CAL + ".calibration_gate_check", name=good_qi),
	"6. a reading taken with the calibrated " + NEW + " needs nothing",
)
ok = frappe.get_doc(QI, good_qi)
ok.submit()
check(
	ok.docstatus == 1 and ok.status == "Accepted",
	"6. that inspection submits: reading 10.0 in 9.9 - 10.1 -> Accepted",
)

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
