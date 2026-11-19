"""Cycle 3b health check (T1) - is the Quality chain set up and doing its job on live records?

Read-only. Each row is a finding with empty Owner and Fix columns in the download; rows in INFO_CHECKS report a
figure, not a problem. A healthy, fully set-up site gives zero findings on every sheet.

  1 Settings and people - what will not work as it is (a sign-off role nobody holds, no Quality owner, ERPNext QC
                          actions not on Warn); settings still at their default, to confirm with PEPL (information)
  2 Inspection          - draft QC Inspections older than 3 days; submitted receipts and deliveries with a line that
                          needed an inspection and has none; inspected items without an inspection plan; rejected
                          inspections without their NCR
  3 Instruments         - instruments in use overdue or never calibrated
  4 NCR and CAPA        - NCRs open longer than 30 days; Critical NCRs without a CAPA; costed dispositions without
                          a cost; CAPAs past their target; CAPAs whose effectiveness check is overdue
  5 Lots and dispatch   - lots offered more than 15 days ago without an IC; agency order lines delivered beyond what
                          their ICs accepted
  6 Drawing changes     - Job Orders with a drawing change not acknowledged after 2 days
  7 Scheduled jobs      - the Quality jobs and their last runs
  8 Usage               - how much of each Quality record there is since the date (information)

System Manager downloads it from PEPL System Health ("Download Cycle 3b health check").
"""

import frappe
from frappe.utils import add_days, flt, getdate, today

from pepl_os.pepl_quality import calibration, capa, config, dispatch, incoming_qc, inspection_lot, ncr

QI = "Quality Inspection"
DEFAULT_SINCE = "2026-07-01"
STALE_DRAFT_DAYS = 3
OPEN_NCR_DAYS = 30
OFFER_DAYS = 15
DRAWING_DAYS = 2
QUALITY_PREFIX = "pepl_os.pepl_quality."

SHEETS = (
	("1 Settings and people", ("check", "record", "detail")),
	("2 Inspection", ("check", "record", "detail")),
	("3 Instruments", ("check", "record", "detail")),
	("4 NCR and CAPA", ("check", "record", "detail")),
	("5 Lots and dispatch", ("check", "record", "detail")),
	("6 Drawing changes", ("check", "record", "detail")),
	("7 Scheduled jobs", ("check", "job", "detail")),
	("8 Usage", ("check", "record", "detail")),
)
INFO_CHECKS = ("Usage", "Setting at its default, to confirm with PEPL", "Job Waiting for First Run")


def _row(check, record="", detail=""):
	return {"check": check, "record": record, "detail": detail}


# 1 Settings and people ----------------------------------------------------------------------------------------
def _settings():
	rows = []
	for r in config.settings_rows():
		if r.colour == "red":
			rows.append(_row("Will not work as it is", r.setting, f"{r.value}: {r.status}"))
		elif r.status.startswith("Not set"):
			rows.append(_row("Quality Notification Owner not set", r.setting, r.status))
		elif r.status.startswith(("Default, to confirm", "Empty: to set")):
			rows.append(
				_row("Setting at its default, to confirm with PEPL", r.setting, f"{r.area}: {r.value}")
			)
	return rows


# 2 Inspection ------------------------------------------------------------------------------------------------
def _missing_inspections(doctype, child, flag, since):
	return frappe.db.sql(
		f"""select d.name, i.idx, i.item_code from `tab{child}` i join `tab{doctype}` d on d.name = i.parent
		join `tabItem` it on it.name = i.item_code
		where d.docstatus = 1 and d.posting_date >= %s and it.{flag} = 1
			and coalesce(i.quality_inspection, '') = ''{" and d.is_return = 0" if doctype == "Delivery Note" else ""}""",
		since,
		as_dict=True,
	)


def _inspection(since):
	rows = []
	for q in frappe.get_all(
		QI,
		filters={"docstatus": 0, "creation": ["<", add_days(today(), -STALE_DRAFT_DAYS)]},
		fields=["name", "item_code", "reference_name", "inspection_type"],
	):
		rows.append(
			_row(
				f"Draft QC Inspection older than {STALE_DRAFT_DAYS} days",
				q.name,
				f"{q.inspection_type} {q.item_code} ({q.reference_name})",
			)
		)
	for r in _missing_inspections("Purchase Receipt", "Purchase Receipt Item", incoming_qc.FLAG, since):
		rows.append(_row("Receipt line without its QC Inspection", r.name, f"line {r.idx} {r.item_code}"))
	for r in _missing_inspections("Delivery Note", "Delivery Note Item", dispatch.FLAG, since):
		rows.append(_row("Delivery line without its final inspection", r.name, f"line {r.idx} {r.item_code}"))
	for flag, what in ((incoming_qc.FLAG, "on receipt"), (dispatch.FLAG, "before delivery")):
		for i in frappe.get_all(
			"Item",
			filters={flag: 1, "disabled": 0, "quality_inspection_template": ["is", "not set"]},
			pluck="name",
		):
			rows.append(_row(f"Item inspected {what} without an inspection plan", i))
	for q in frappe.get_all(
		QI,
		filters={"docstatus": 1, "status": "Rejected", "report_date": [">=", since]},
		fields=["name", "item_code"],
	):
		if not frappe.db.exists(ncr.NCR, {"quality_inspection": q.name, "status": ["!=", ncr.CANCELLED]}):
			rows.append(_row("Rejected QC Inspection without an NCR", q.name, q.item_code))
	return rows


# 3 Instruments -----------------------------------------------------------------------------------------------
def _instruments():
	rows = []
	for i in frappe.get_all(
		calibration.INSTRUMENT,
		filters={"status": calibration.ACTIVE},
		fields=["name", "instrument_name", "calibration_due_on"],
	):
		state = calibration.state_of(calibration.ACTIVE, i.calibration_due_on)[0]
		if state in (calibration.OVERDUE, calibration.NEVER):
			rows.append(
				_row(
					f"Instrument {state.lower()}",
					i.name,
					f"{i.instrument_name or ''} due {i.calibration_due_on or '-'}",
				)
			)
	return rows


# 4 NCR and CAPA ----------------------------------------------------------------------------------------------
def _ncr_capa():
	rows = []
	for n in frappe.get_all(
		ncr.NCR,
		filters={"status": ["in", (ncr.OPEN, ncr.UNDER_REVIEW)]},
		fields=["name", "severity", "item", "raised_on", "capa"],
	):
		if n.raised_on and getdate(n.raised_on) < getdate(add_days(today(), -OPEN_NCR_DAYS)):
			rows.append(
				_row(
					f"NCR open more than {OPEN_NCR_DAYS} days",
					n.name,
					f"{n.severity} {n.item} since {n.raised_on}",
				)
			)
		if n.severity == ncr.CRITICAL and not n.capa:
			rows.append(_row("Critical NCR without a CAPA", n.name, n.item))
	for n in frappe.get_all(
		ncr.NCR,
		filters={
			"status": ["!=", ncr.CANCELLED],
			"disposition": ["in", ("Rework", "Scrap", "Return to Supplier", "Regrade")],
		},
		fields=["name", "disposition", "estimated_cost", "item"],
	):
		if flt(n.estimated_cost) <= 0:
			rows.append(_row("NCR without its cost", n.name, f"{n.disposition} {n.item}"))
	for c in frappe.get_all(
		capa.CAPA,
		filters={"status": ["in", (capa.OPEN, capa.IN_PROGRESS)], "target_date": ["<", today()]},
		fields=["name", "item", "target_date"],
	):
		rows.append(_row("CAPA past its target", c.name, f"{c.item} target {c.target_date}"))
	for c in frappe.get_all(
		capa.CAPA,
		filters={"status": capa.AWAITING, "verification_due_on": ["<", today()]},
		fields=["name", "item", "verification_due_on"],
	):
		rows.append(_row("CAPA effectiveness check overdue", c.name, f"{c.item} due {c.verification_due_on}"))
	return rows


# 5 Lots and dispatch -----------------------------------------------------------------------------------------
def _lots(since):
	rows = []
	for lot in frappe.get_all(
		inspection_lot.LOT,
		filters={"status": inspection_lot.OFFERED, "offered_on": ["<", add_days(today(), -OFFER_DAYS)]},
		fields=["name", "sales_order", "item", "offered_on", "inspection_agency"],
	):
		rows.append(
			_row(
				f"Lot offered more than {OFFER_DAYS} days ago, no IC",
				lot.name,
				f"{lot.item} on {lot.sales_order}, offered {lot.offered_on} to {lot.inspection_agency or '-'}",
			)
		)
	lines = frappe.db.sql(
		"""select distinct i.against_sales_order as so, i.item_code as item from `tabDelivery Note Item` i
		join `tabDelivery Note` d on d.name = i.parent
		where d.docstatus = 1 and d.is_return = 0 and d.posting_date >= %s and coalesce(i.against_sales_order, '') != ''""",
		since,
		as_dict=True,
	)
	for line in lines:
		if not inspection_lot.needs_agency_inspection(line.so, line.item):
			continue
		cleared = inspection_lot.ic_accepted(line.so, line.item)
		shipped = inspection_lot.delivered_before(line.so, line.item, None)
		if shipped > cleared + 1e-9:
			rows.append(
				_row(
					"Delivered beyond the agency's ICs",
					line.so,
					f"{line.item}: delivered {shipped:g}, ICs accepted {cleared:g}",
				)
			)
	return rows


# 6 Drawing changes -------------------------------------------------------------------------------------------
def _drawings():
	from pepl_os.pepl_quality import drawing

	return [
		_row("Drawing change not acknowledged", w.name, f"{w.production_item}: {w.get(drawing.ALERT)}")
		for w in frappe.get_all(
			drawing.WO,
			filters={
				drawing.ALERT: ["is", "set"],
				drawing.ACK_ON: ["is", "not set"],
				drawing.ALERT_ON: ["<", add_days(today(), -DRAWING_DAYS)],
				"docstatus": ["<", 2],
			},
			fields=["name", "production_item", drawing.ALERT],
		)
	]


# 7 Scheduled jobs --------------------------------------------------------------------------------------------
def _jobs():
	from pepl_os.pepl_governance.page.pepl_system_health.pepl_system_health import get_pepl_jobs, job_health

	rows = []
	for frequency, method in get_pepl_jobs():
		if not method.startswith(QUALITY_PREFIX):
			continue
		h = job_health(frequency, method)
		if h["status"] == "OK":
			continue
		rows.append(
			{
				"check": f"Job {h['status']}",
				"job": method,
				"detail": f"{frequency}; last success {h['last_success'] or 'never'}; last failure {h['last_failure'] or 'none'}",
			}
		)
	return rows


# 8 Usage -----------------------------------------------------------------------------------------------------
def _usage(since):
	figures = (
		("QC Inspections submitted", QI, {"docstatus": 1, "report_date": [">=", since]}),
		("NCRs raised", ncr.NCR, {"raised_on": [">=", since]}),
		("CAPAs raised", capa.CAPA, {"raised_on": [">=", since]}),
		("Calibration records", calibration.RECORD, {"docstatus": 1, "calibration_date": [">=", since]}),
		("Inspection lots", inspection_lot.LOT, {"creation": [">=", since]}),
	)
	return [_row("Usage", label, str(frappe.db.count(dt, filters))) for label, dt, filters in figures]


def build_health_check(since=DEFAULT_SINCE):
	"""{sheet title: [row dicts]}. Reads only."""
	since = getdate(since)
	data = [
		_settings(),
		_inspection(since),
		_instruments(),
		_ncr_capa(),
		_lots(since),
		_drawings(),
		_jobs(),
		_usage(since),
	]
	return {title: rows for (title, _cols), rows in zip(SHEETS, data, strict=True)}


def findings(check):
	"""{sheet: number of real findings}, information rows left out."""
	return {sheet: len([r for r in rows if r["check"] not in INFO_CHECKS]) for sheet, rows in check.items()}


@frappe.whitelist()
def run_health_check(since=DEFAULT_SINCE):
	"""For the System Console check: the findings per sheet, and the rows themselves."""
	frappe.only_for("System Manager")
	check = build_health_check(since)
	return {"findings": findings(check), "rows": check}


@frappe.whitelist()
def download_health_check(since=DEFAULT_SINCE):
	"""System Manager only. Streams the Cycle 3b health-check workbook; writes nothing."""
	from pepl_os.pepl_stores import audit

	frappe.only_for("System Manager")
	frappe.response["filename"] = f"PEPL Cycle 3b health check {today()}.xlsx"
	frappe.response["filecontent"] = audit.to_xlsx(build_health_check(since), SHEETS, INFO_CHECKS)
	frappe.response["type"] = "binary"
	return None
