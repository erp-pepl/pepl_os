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
| Seven role profiles (A2) | Role Profile: PEPL Purchase Manager, PEPL Stores, PEPL Production Manager, PEPL Foreman, PEPL Quality Manager, PEPL Accounts, PEPL CEO |
| Delete restricted to System Manager (A2, A5) | Re-applied on every deploy; switch in PEPL System Parameters → PEPL OS → Audit Trail |
| Change and view tracking (A3) | Applied on every deploy (`pepl_os/setup/property_setters.py`) |
| One audit screen (A4) | Report **PEPL Audit Trail** |
| Log retention (A5) | PEPL System Parameters → Audit Log Retention (Days), default 1095 |
| User note for the manuals | `docs/wp_a_user_note.md` |

## Tests

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app pepl_os
```

## License

MIT
