# Cycle 3a · Production — handover

App `pepl_os`, module **PEPL Production** (with the scrap side in **PEPL Stores**). Works on ERPNext v16 next to
`pepl_sales` (which owns PEPL System Parameters, the CST Cost Sheet, the Product Master and the Skill Check Mode).
Versions 0.23.0 – 0.50.0. The user guides are `docs/cycle3a_kiosk_uat.md` (operators and foreman),
`docs/cycle3a_production_manager_uat.md` (Production Manager) and `docs/cycle3a_manuals_annex.md` (what changes per
role). What PEPL must fill in before go-live is in `docs/cycle3a_pepl_inputs.md`.

## How the chain runs

1. **Sales Order submitted** → one draft **Job Order** (ERPNext Work Order) per manufactured line with a default BOM,
   due on the line's date; lines without a BOM give Production a ToDo (PRD-NO-BOM). Railways / Defence orders carry
   the standard **LD clause** (rate per week or day, cap, grace days), fixed on submit.
2. **Production Plan / Job Order** → machine double-booking check (Advisory / Soft Block / Hard Block) and the
   **load view** (hours booked against each machine's hours). Submitting the Job Order makes the **Job Cards**.
3. **Shop floor**: the operator enters his shift on the **kiosk** beside the machine (`/kiosk?machine=…`, employee
   code + PIN) or the foreman in the Desk: a **Shift Production Entry** with production blocks per Job Card
   (good / rejected / reason), stops by **downtime category**, tool changes with a photo, consumables. Help on the
   form: gaps in the shift, Job Card quantity left, speed against standard, skill on the machine group, eligible
   shifts. Submitting it:
   - posts the time blocks to the Job Cards (Job Card time logs) and issues the consumables;
   - rebuilds that day's **Daily OEE** for the machine and that week's **Machine Week** (MTBF / MTTR / CPC);
   - puts the rejected pieces into the **Scrap Register** (Scrap Weighment, source Rejection) or gives Stores a ToDo.
4. **Foreman view** (`/foreman`): every machine of a shift — Submitted / Draft / Missing, good, rejected, minutes
   not explained.
5. **Job work**: material sent to job workers is tracked by store (sent / received / returned, age, GST 365-day
   limit) with a daily ToDo for overdue material (PRD-JW-OVERDUE).
6. **Delivery Note** of an order with customer-supplied material consumes that material automatically (heat FIFO)
   behind a material gate (Off / Warn-Block / Hard).
7. **Every morning 07:45**: the **exception-only Daily Stand-up** e-mailed to the Standup Email Group.

## Panels (on the forms)

| Form | Panel |
| --- | --- |
| Job Order | made vs target, shop-floor good / rejected, routing progress, due date and LD so far; customer material held vs needed; **View → Cost vs Estimate** |
| Production Plan | machine load per day (orange from the warning %, red above 100 %) |
| Supplier / Stock Entry | job work outstanding at that job worker |
| Shift Production Entry | gaps, Job Card left, speed, skill, eligible shift, where the rejected pieces went |
| PEPL Operator | PIN, skills with validity, Employee, eligible shifts, skills expiring soon |

## Reports and the Command Centre

**Production Command Centre** workspace: cards Yesterday's OEE, Jobs at Delivery Risk, Job Work Outside, Rejection %
(7 days), Top Downtime Cause (7 days). Reports: Downtime by Cause, Job-Work Reconciliation, Downtime Category Review
(merge look-alike categories), Production Settings, **Estimate vs Actual Cost**, **Skill Matrix**, **Bottleneck**,
**LD Exposure**. Health: **PEPL System Health → Download Cycle 3a health check**.

## Scheduled jobs (all recorded in PEPL Job Run; status on PEPL System Health)

| Job | When | Does |
| --- | --- | --- |
| `pepl_production.oee.daily_oee` | daily | yesterday's Daily OEE for every machine (safety net; entries rebuild their day at once) |
| `pepl_production.job_work.daily_job_work_alerts` | daily | one ToDo per job worker holding overdue material |
| `pepl_production.machine_week.weekly_machine_figures` | Monday 02:30 | last week's MTBF / MTTR / CPC per machine |
| `pepl_production.standup.daily_standup` | 07:45 daily | yesterday's stand-up, built and e-mailed |

## Rule codes (ToDos and the override Audit Trail)

| Code | Meaning |
| --- | --- |
| PRD-NO-BOM | Sales Order line of a manufactured item without a default BOM: no Job Order drafted |
| PRD-JO-DRAFT-FAILED | the Sales Order's draft Job Orders could not be made |
| PRD-DOUBLE-BOOK | machine double-booked, allowed with a reason (Soft Block) |
| PRD-SKILL | operator below the minimum skill level, submitted with a reason (Soft Block) |
| PRD-JW-OVERDUE | material at a job worker past the return days or near the GST limit |
| PRD-CSM-NOT-CONSUMED | a Delivery Note's customer material could not be issued automatically |
| PRD-REJECT-SCRAP | rejected pieces of a shift entry waiting for Stores to weigh (scrap item, weight or rate missing) |

## Settings PEPL owns

All in **PEPL System Parameters → Production** (and the first tab for Skill Check Mode and the Standup Email Group);
the report **Production Settings** lists each one with its value, default and whether it was changed. Shop floor
(PIN digits, minimum skill level, grace and unexplained minutes, tool photo required), machine double-booking mode,
Job Orders from Sales Orders, load warning %, OEE target and component targets, PM in planned time, standard-time
governance, job work days, CSM gate and tolerance, stand-up (days ahead, exception-only, minimum stop minutes), LD
defaults and look-ahead, kiosk (wrong PIN tries, lock and session minutes), costing (machine-hour rates, overhead %,
variance warning %), operators (shift eligibility check, skill expiry warning days, minimum qualified operators),
bottleneck wait warning hours, rejections to scrap (on / off, fallback scrap item). Changing a value after sign-off
is a change request.

## The kiosk device

One login per tablet with the Role Profile **PEPL Kiosk** (no Desk). It opens `/kiosk` after logging in; the
tablet is bookmarked on `/kiosk?machine=<machine>`. Operators sign in with employee code + PIN; wrong PINs lock the
code; a session ends after the session minutes without saving. The shop-floor Wi-Fi and the tablets are PEPL's.

## Checks

- Automated tests: GitHub → Actions → CI → Run workflow (fresh site; `tests/test_c3a_*.py`). Acceptance = all green.
- System Console checks 23 – 49 (one per deliverable, Commit unticked; Check 49 runs the whole chain end to end).
- **Cycle 3a health check** (PEPL System Health): set-up gaps and live data against the automation; zero findings
  expected once PEPL's inputs are in (information rows excepted).

## Known limits (by decision)

- No payroll in HR-lite; the Employee leads only name, joining date, login and working status.
- Learning standards (plan-vs-actual cycle time with suggest-and-HOD-approve) build on the standard-time governance
  settings and are Work Package E2.
- Bottleneck hours are clock hours (nights and holidays included).
- Actual job work and surface treatment cost comes from the extra costs typed on Manufacture entries.
- Quality (incoming inspection, NCR, CAPA, calibration) is Cycle 3b.
