# PEPL OS

The PEPL Operating System for Parasramka Engineering Pvt. Ltd., built on ERPNext v16.
It covers Purchase & Stores, Production, Quality, HR, the Tally reconciliation mirror
and programme extensions.

`pepl_os` builds on `pepl_sales` (Cycle 1, Sales-to-Cash). Dependencies point one way:
`pepl_os` imports from `pepl_sales`, never the reverse.

## Modules

| Module | Scope |
| --- | --- |
| PEPL Governance | Audit trail and attribution (Work Package A), override log, job runs, System Health, change requests (E1) |
| PEPL Purchase | Supplier approval, RFQ, quotation comparison, Purchase Tracker, payment worklist (Cycle 2) |
| PEPL Stores | Stock classes, heat numbers and Receipt Log, scrap, reorder, cycle count (Cycle 2) |
| PEPL Production | Job Order, production plan, Shift Production Entry, kiosk, OEE (Cycle 3a) |
| PEPL Quality | Inspection, NCR, CAPA, calibration, lots, SPC-lite (Cycle 3b) |
| PEPL People | Employee, attendance, leave, statutory data (Cycle 4) |
| PEPL Tally Mirror | Tally voucher mirror and reconciliation (Work Package R) |

## Shared building blocks (`pepl_os/common`)

| Helper | Use it for |
| --- | --- |
| `params.get(field, default)` | Reading any threshold from PEPL System Parameters |
| `alerts.raise_todo(...)` / `alerts.close_resolved(...)` | The standard flag pattern: one open ToDo per rule per record |
| `overrides.log_override(...)` / `overrides.require_override(...)` | Human override with a mandatory reason, logged to PEPL Override Log |
| `jobs.tracked_job("name")` | Decorating every scheduled job, so each run is recorded in PEPL Job Run |
| `expiry.health(date, alert_days, as_of)` | Active / Expiring Soon / Expired for any expiry date |
| `pepl.ask_reason()`, `pepl.override()`, `pepl.panel()` (JS) | The reason dialog and one consistent helper panel on forms |

## Rules

- Custom Fields go in `pepl_os/setup/custom_fields.py`. They are applied on install and on every
  migrate. Patches are only for one-off data fixes, because Frappe marks patches as done without
  running them on a fresh install.
- Thresholds live only in PEPL System Parameters.
- Every scheduled job uses `@tracked_job`.
- Every change arrives by pull request, and CI must be green before merging.

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/erp-pepl/pepl_os --branch main
bench --site <site> install-app pepl_os   # erpnext and pepl_sales must already be installed
```

Admin screens after install:

- `/desk/pepl-system-health` shows each PEPL job, its schedule and its last successful run.
- `/desk/pepl-override-log` lists every override with its reason.
- `/desk/pepl-job-run` holds one row per job run.

## Work Package A (audit trail and attribution)

| What | Where |
| --- | --- |
| Access audit of every login (A1) | Report **PEPL Access Audit** |
| Ten role profiles (A2) | Role Profile: PEPL Purchase Manager, PEPL Stores, PEPL Production Manager, PEPL Foreman, PEPL Quality Manager, PEPL Accounts, PEPL CEO, PEPL Sales & Tender Manager, PEPL Sales & Tender Executive, PEPL Engineering |
| What each profile can do (A2) | Report **PEPL Role Access Matrix** (live, exportable) |
| CEO sees every record, changes none (A2) | Applied on every deploy (`grant_ceo_view`) |
| Delete restricted to System Manager (A2, A5) | Re-applied on every deploy; switch in PEPL System Parameters → PEPL OS → Audit Trail |
| Change and view tracking (A3) | Applied on every deploy (`pepl_os/setup/property_setters.py`) |
| One audit screen (A4) | Report **PEPL Audit Trail** |
| Log retention (A5) | PEPL System Parameters → Audit Log Retention (Days), default 1095 |
| User note for the manuals | `docs/wp_a_user_note.md` |

## Cycle 2 · Purchase & Stores

| What | Where |
| --- | --- |
| C2-01 Live audit (read-only) | PEPL System Health → **Download Cycle 2 audit** (System Manager) |
| C2-02 Purchase & Stores rulebook | PEPL System Parameters → **Purchase & Stores** tab |
| C2-03 Supplier criticality, MSME, RM groups | Supplier → **PEPL** section; list coloured by approval state |
| C2-04 Stock classes, stores, CSM rule | Item Group tree, warehouses per company, Item → Stock Class |
| C2-05 Capital Equipment Register | **PEPL Capital Equipment**; daily warranty / AMC alerts |
| C2-07 Material Request from Sales Order | On SO submit: one draft MR for bought-out lines and raw-material shortfall; MR panel |
| C2-08 Supplier Approval gate | **PEPL Supplier Document Requirement** (the checklist), **PEPL Supplier Approval** per supplier; reason needed to submit an RFQ / PO to a non-approved supplier; daily expiry job |
| C2-09 RFQ by RM group | Material Request → **RFQ by RM Group**: one draft RFQ per group, approved suppliers ticked |
| C2-10 Quotation Comparison | RFQ → **Quotation Comparison**: L1 per line, non-L1 award needs a reason, approval creates one PO per supplier with the comparison attached |
| C2-11 PO approval by value | PO above the PO Approval Value: only the MD / CEO submits; promised date mandatory on every line |
| C2-12 Purchase Tracker | One per submitted PO; line-level promised vs received, days to due / overdue, recomputed daily |
| C2-13 Chase list and letter | **PEPL Chase List**, **Chase vendor** (letter on the letterhead), PUR-CHASE ToDos, **PEPL Open PO Ageing** |
| C2-14 Letdowns and delivery score | **PEPL Delivery Letdown** for every late / short receipt; supplier delivery score shown in RFQ and comparison |
| C2-15 Heat numbers | Receipt gate (heat + test certificate), **Split by heat**, Batch = heat, **PEPL Receipt Log**, **PEPL Heat Number Trace** |
| C2-16 Customer-supplied material | SO **Has CSM** and disposition; CSM receipts at zero value; **PEPL CSM Balance by Order**; return challan |
| C2-17 Vendor payments | MSME pay-by date, **PEPL Vendor Payment Priority** (MSME, critical overdue, ageing), **PEPL Payment Run**, **Mark paid** from Tally, **PEPL MSME 45-Day Compliance**, **PEPL Outstanding Vendor Bills** |
| C2-18 Scrap Register | **PEPL Scrap Rate**, **PEPL Scrap Weighment**, **PEPL Scrap Sale** (gate pass), **PEPL Scrap Recovery**; CSM scrap sold only when the SO allows it |
| C2-19 Reorder engine | **PEPL Reorder Review** (monthly, from consumption and lead time), Item reorder panel, STO-REORDER ToDos |
| C2-20 Cycle count | ABC class monthly, **PEPL Cycle Count** (blind sheet, reason per variance, HOD above the limit), **PEPL Cycle Count Variance Log** |
| C2-21 Consumables issued | **PEPL Consumables Issued** per day / week / month and % of sales |
| C2-22 Form panels | One panel style on every key purchase and stores form, including the Receipt Log heat panel |
| C2-23 Command Centre | Workspaces **Buyer's Desk** and **MD Stores Overview**, six number cards, **PEPL Procurement Funnel** |
| C2-24 Print formats | PO, RFQ cover letter, chase letter, weighment slip, gate pass, count sheet, CSM challan on the PEPL letterhead (PDF and Print button) |
| Cycle 2 health check | PEPL System Health → **Download Cycle 2 health check**: trackers, receipt logs, approvals, overrides, jobs, valuation and vendor-bill reports checked against live records |

## Tests

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app pepl_os
```

Before the suite, `pepl_os.tests.bootstrap.before_tests` builds ERPNext's standard
test data (`_Test Company`, suppliers, items) so stock tests have a company.

## License

MIT
