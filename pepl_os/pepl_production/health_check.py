"""Cycle 3a health check (T1) - is the Production chain set up and doing its job on live records?

Read-only. Each row is a finding with empty Owner and Fix columns in the download; rows in INFO_CHECKS report a
figure, not a problem. A healthy, fully set-up site gives zero findings on every sheet.

  1 Shop-floor masters  - active shifts, downtime categories, machines without a machine group, machine groups
                          without a Machine-Hour Rate, active operators without PIN / skills / default shift, expired
                          skills, machine groups with fewer qualified operators than the minimum
  2 Shift entries       - drafts older than 2 days, submitted entries with minutes not explained above the limit,
                          tool changes without a photo when photos are required, machines that worked in the last
                          30 days without an entry in the last 7
  3 Job Orders          - open Job Orders past their delivery date, In Process Job Orders without a time log for 7
                          days, Sales Order lines of manufactured items with a BOM but no Job Order
  4 Daily results       - days with submitted entries but no Daily OEE; weeks with submitted entries but no Machine
                          Week
  5 Costing and scrap   - items made in the period without a CST estimate, without a weight per unit or without a
                          scrap item for rejections; rejections still waiting for Stores to weigh after 2 days
  6 LD                  - submitted open orders of an LD sector without an LD clause; LD running (information)
  7 Scheduled jobs      - the Production jobs and their last runs
  8 Settings            - Production settings still at their default, to be confirmed with PEPL (information)

System Manager downloads it from PEPL System Health ("Download Cycle 3a health check").
"""

import frappe
from frappe.utils import add_days, cint, flt, getdate, today

from pepl_os.common import params

SPR = "PEPL Shift Production Entry"
OPERATOR = "PEPL Operator"
DEFAULT_SINCE = "2026-07-01"
STALE_DRAFT_DAYS = 2
QUIET_DAYS = 7
ACTIVE_DAYS = 30
SCRAP_RULE = "PRD-REJECT-SCRAP"
PRODUCTION_PREFIX = "pepl_os.pepl_production."

SHEETS = (
	("1 Shop-floor masters", ("check", "record", "detail")),
	("2 Shift entries", ("check", "record", "detail")),
	("3 Job Orders", ("check", "record", "detail")),
	("4 Daily results", ("check", "record", "detail")),
	("5 Costing and scrap", ("check", "record", "detail")),
	("6 LD", ("check", "record", "detail")),
	("7 Scheduled jobs", ("check", "job", "detail")),
	("8 Settings", ("check", "record", "detail")),
)
INFO_CHECKS = (
	"Usage",
	"LD running",
	"Setting at its default, to confirm with PEPL",
	"Job Waiting for First Run",
)


def _row(check, record="", detail=""):
	return {"check": check, "record": record, "detail": detail}


# 1 Shop-floor masters ---------------------------------------------------------------------------------------
def _masters():
	from pepl_os.pepl_production import hr_lite, machine_hour_rates

	rows = []
	if not frappe.db.count("PEPL Shift", {"is_active": 1}):
		rows.append(_row("No active shift", "", "Add the shifts in PEPL Shift"))
	if not frappe.db.count("PEPL Downtime Category", {"is_active": 1}):
		rows.append(_row("No active downtime category"))
	machines = frappe.get_all("Workstation", filters={"disabled": 0}, fields=["name", "workstation_type"])
	for m in machines:
		if not m.workstation_type:
			rows.append(
				_row("Machine without a machine group", m.name, "Skill check, rates and the matrix need it")
			)
	for group in sorted({m.workstation_type for m in machines if m.workstation_type}):
		if machine_hour_rates.rate_for_group(group) is None:
			rows.append(
				_row(
					"Machine group without a Machine-Hour Rate",
					group,
					"System Parameters > Production Costing",
				)
			)
	for op in frappe.get_all(
		OPERATOR, filters={"status": "Active"}, fields=["name", "operator_name", "pin_set", "default_shift"]
	):
		if not cint(op.pin_set):
			rows.append(_row("Active operator without a PIN", op.name, op.operator_name))
		if not op.default_shift:
			rows.append(_row("Active operator without a default shift", op.name, op.operator_name))
		skills = frappe.get_all(
			"PEPL Operator Skill",
			filters={"parent": op.name, "parenttype": OPERATOR},
			fields=["workstation_type", "valid_until"],
		)
		if not skills:
			rows.append(_row("Active operator without skills", op.name, op.operator_name))
		for s in skills:
			if hr_lite.skill_state(s) == "expired":
				rows.append(_row("Expired skill", op.name, f"{s.workstation_type} until {s.valid_until}"))
	_groups, keys, _rows, cover, thin = hr_lite.matrix({"status": "Active"})
	for group in thin:
		rows.append(
			_row(
				"Machine group with too few qualified operators",
				group,
				f"{cover.get(keys[group])} qualified, minimum {hr_lite.min_cover()}",
			)
		)
	return rows


# 2 Shift entries ----------------------------------------------------------------------------------------------
def _entries(since):
	from pepl_os.pepl_production import spr

	rows = []
	for e in frappe.get_all(
		SPR,
		filters={"docstatus": 0, "posting_date": ["between", [since, add_days(today(), -STALE_DRAFT_DAYS)]]},
		fields=["name", "workstation", "posting_date", "operator"],
	):
		rows.append(
			_row(
				"Shift entry not submitted after 2 days",
				e.name,
				f"{e.workstation}, {e.posting_date}, {e.operator}",
			)
		)
	limit = spr.unaccounted_limit()
	for e in frappe.get_all(
		SPR,
		filters={"docstatus": 1, "posting_date": [">=", since], "unaccounted_minutes": [">", limit]},
		fields=["name", "workstation", "posting_date", "unaccounted_minutes"],
	):
		rows.append(
			_row(
				"Submitted entry with minutes not explained",
				e.name,
				f"{e.workstation}, {e.posting_date}: {e.unaccounted_minutes} min (allowed {limit})",
			)
		)
	if spr.tool_photo_required():
		for t in frappe.db.sql(
			f"""select s.name, s.workstation, s.posting_date, t.idx from `tabPEPL SPR Tool Change` t
			join `tab{SPR}` s on s.name = t.parent
			where s.docstatus = 1 and s.posting_date >= %s and ifnull(t.photo, '') = ''""",
			since,
			as_dict=True,
		):
			rows.append(
				_row("Tool change without a photo", t.name, f"{t.workstation}, {t.posting_date}, row {t.idx}")
			)
	active = set(
		frappe.get_all(
			SPR,
			filters={"docstatus": 1, "posting_date": [">=", add_days(today(), -ACTIVE_DAYS)]},
			pluck="workstation",
			distinct=True,
		)
	)
	recent = set(
		frappe.get_all(
			SPR,
			filters={"docstatus": 1, "posting_date": [">=", add_days(today(), -QUIET_DAYS)]},
			pluck="workstation",
			distinct=True,
		)
	)
	for machine in sorted(active - recent):
		rows.append(_row("Machine worked in the last 30 days, no entry in the last 7", machine))
	count = frappe.db.count(SPR, {"docstatus": 1, "posting_date": [">=", since]})
	rows.append(_row("Usage", "", f"{count} submitted shift entries since {since}"))
	return rows


# 3 Job Orders --------------------------------------------------------------------------------------------------
def _job_orders(since):
	rows = []
	for wo in frappe.get_all(
		"Work Order",
		filters={
			"docstatus": 1,
			"status": ["in", ("Not Started", "In Process")],
			"expected_delivery_date": ["<", today()],
		},
		fields=["name", "production_item", "expected_delivery_date", "qty", "produced_qty"],
	):
		rows.append(
			_row(
				"Job Order past its delivery date",
				wo.name,
				f"{wo.production_item}: {flt(wo.produced_qty)} of {flt(wo.qty)}, due {wo.expected_delivery_date}",
			)
		)
	for wo in frappe.get_all("Work Order", filters={"docstatus": 1, "status": "In Process"}, pluck="name"):
		last = frappe.db.sql(
			"""select max(l.to_time) from `tabJob Card Time Log` l join `tabJob Card` c on c.name = l.parent
			where c.work_order = %s""",
			wo,
		)[0][0]
		if not last or getdate(last) < getdate(add_days(today(), -QUIET_DAYS)):
			rows.append(
				_row("Job Order In Process without a time log for 7 days", wo, f"last log {last or 'never'}")
			)
	for line in frappe.db.sql(
		"""select so.name, soi.name as line, soi.item_code from `tabSales Order Item` soi
		join `tabSales Order` so on so.name = soi.parent
		join `tabBOM` b on b.item = soi.item_code and b.is_default = 1 and b.docstatus = 1
		left join `tabWork Order` wo on wo.sales_order_item = soi.name and wo.docstatus < 2
		where so.docstatus = 1 and so.status not in ('Closed', 'Completed') and so.transaction_date >= %s
			and wo.name is null""",
		since,
		as_dict=True,
	):
		rows.append(_row("Sales Order line with a BOM but no Job Order", line.name, line.item_code))
	return rows


# 4 Daily results -----------------------------------------------------------------------------------------------
def _results(since):
	from pepl_os.pepl_production import machine_week, oee

	rows = []
	for day, machine in frappe.db.sql(
		f"""select distinct s.posting_date, s.workstation from `tab{SPR}` s
		left join `tab{oee.DOCTYPE}` o on o.oee_date = s.posting_date and o.workstation = s.workstation
		where s.docstatus = 1 and s.posting_date >= %s and o.name is null""",
		since,
	):
		rows.append(_row("Shift entries without a Daily OEE", machine, str(day)))
	weeks = set()
	for day, machine in frappe.db.sql(
		f"select distinct posting_date, workstation from `tab{SPR}` where docstatus = 1 and posting_date >= %s",
		since,
	):
		weeks.add((machine, machine_week.week_start(day)))
	for machine, monday in sorted(weeks):
		if getdate(monday) <= getdate(add_days(today(), -7)) and not machine_week.record_name(
			machine, monday
		):
			rows.append(_row("Shift entries without a Machine Week", machine, f"week of {monday}"))
	return rows


# 5 Costing and scrap -------------------------------------------------------------------------------------------
def _costing(since):
	from pepl_os.pepl_production import costing, rejection_scrap

	rows = []
	items = sorted(
		set(
			frappe.get_all(
				"Work Order",
				filters={"docstatus": 1, "planned_start_date": [">=", since]},
				pluck="production_item",
			)
		)
	)
	for item in items:
		if not costing.choose_sheet(item)[0]:
			rows.append(_row("Item made without an approved CST estimate", item))
		if not rejection_scrap.kg_per_piece(item):
			rows.append(_row("Item made without a weight per unit (rejections cannot be weighed)", item))
		if not (
			frappe.db.get_value("Item", item, rejection_scrap.ITEM_FIELD)
			or params.get(rejection_scrap.FALLBACK_FIELD)
		):
			rows.append(_row("Item made without a scrap item for rejections", item))
	for t in frappe.get_all(
		"ToDo",
		filters={
			"reference_type": SPR,
			"status": "Open",
			"description": ["like", f"%{SCRAP_RULE}%"],
			"creation": ["<", add_days(today(), -STALE_DRAFT_DAYS)],
		},
		fields=["reference_name", "creation"],
	):
		rows.append(
			_row(
				"Rejections waiting to be weighed for more than 2 days",
				t.reference_name,
				str(getdate(t.creation)),
			)
		)
	return rows


# 6 LD ----------------------------------------------------------------------------------------------------------
def _ld(since):
	from pepl_os.pepl_production import ld, ld_exposure

	rows = []
	sectors = ld.default_sectors()
	if frappe.db.has_column("Sales Order", "custom_sector") and sectors:
		for so in frappe.get_all(
			"Sales Order",
			filters={
				"docstatus": 1,
				"status": ["not in", ("Closed", "Completed")],
				"transaction_date": [">=", since],
				"custom_sector": ["in", list(sectors)],
				ld.APPLICABLE: 0,
			},
			fields=["name", "custom_sector", "customer"],
		):
			rows.append(
				_row(
					"Order of an LD sector without an LD clause",
					so.name,
					f"{so.custom_sector}, {so.customer}",
				)
			)
	orders, _lines = ld_exposure.order_rows({})
	running = [o for o in orders if flt(o["ld_now"]) > 0]
	if running:
		rows.append(
			_row(
				"LD running",
				"",
				f"{len(running)} order(s), {sum(flt(o['ld_now']) for o in running):.2f} so far",
			)
		)
	return rows


# 7 Scheduled jobs ----------------------------------------------------------------------------------------------
def _jobs():
	from pepl_os.pepl_governance.page.pepl_system_health.pepl_system_health import get_pepl_jobs, job_health

	rows = []
	for frequency, method in get_pepl_jobs():
		if not method.startswith(PRODUCTION_PREFIX):
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


# 8 Settings ----------------------------------------------------------------------------------------------------
def _settings():
	from pepl_os.pepl_production import config

	return [
		_row("Setting at its default, to confirm with PEPL", r.setting, f"{r.area}: {r.value}")
		for r in config.settings_rows()
		if r.status != "Changed from default" and r.area != "Production (first tab)"
	]


def build_health_check(since=DEFAULT_SINCE):
	"""{sheet title: [row dicts]}. Reads only."""
	since = getdate(since)
	data = [
		_masters(),
		_entries(since),
		_job_orders(since),
		_results(since),
		_costing(since),
		_ld(since),
		_jobs(),
		_settings(),
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
	"""System Manager only. Streams the Cycle 3a health-check workbook; writes nothing."""
	from pepl_os.pepl_stores import audit

	frappe.only_for("System Manager")
	frappe.response["filename"] = f"PEPL Cycle 3a health check {today()}.xlsx"
	frappe.response["filecontent"] = audit.to_xlsx(build_health_check(since), SHEETS, INFO_CHECKS)
	frappe.response["type"] = "binary"
	return None
