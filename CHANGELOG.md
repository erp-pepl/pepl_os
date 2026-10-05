# Changelog — pepl_os

Entries for the Master System Document. Newest first.

## 0.22.5 — from CI run #14

- Tests only: the bare CI site gets a default outgoing e-mail account (nothing is sent in tests), as
  the live site has, so the chase e-mail test can run.

## 0.22.4 — from CI run #13 (a fresh site with no setup wizard)

- Same item on several PO / receipt lines (needed by Split by heat) is switched on once in Buying
  Settings; a site set up without ERPNext's wizard had it off.
- PEPL CEO can select ledger accounts, so a CEO can submit a PO above the approval value.
- An alert with no owner set in System Parameters no longer stops the user's save; it is logged.
- An override reason can be logged before the record is first saved.
- Material Request default store is always a store of the same company.
- Chase e-mail still goes out (letter as HTML) if the PDF cannot be made; logged.
- Batch is under the delete restriction like the other core records.
- Tests: each test now rolls back on its own; CI installs the patched wkhtmltopdf.

## 0.22.3 — first full CI run

- Tests only (no change to how the system works): the scrap weighment test now checks the receipt's
  incoming rate instead of the yard's moving-average rate; the comparison-PDF test attaches a real PDF,
  which Frappe v16 requires.

## 0.22.2 — from the first end-to-end run (Check 22)

- Delivery Letdown: a PO line split over several receipt lines (Split by heat) is one late delivery,
  so one Late row, not one per heat; regression test added.

## 0.22.1 — fixes from the first audit run on the demo site

- C2-01 audit: "Stock value by warehouse" printed "<built-in method items>" instead of the item count
  (SQL alias clashed with dict.items); regression test added.
- Audit and health-check Summary sheets count only findings, not information rows.
- Health check: an unapproved supplier whose every PO carries an override reason is shown as
  information, not as a finding.

## 0.22.0 — Cycle 2 complete (Purchase & Stores)

- Cycle 2 health check (brief Phase 1 on live data): PO → tracker, receipt → Receipt Log, heat and
  test certificates, supplier approvals, comparison usage and override reasons, every scheduled job,
  valuation per stock class, Outstanding Vendor Bills against the supplier ledger, MSME flags and dates.
  PEPL System Health → Download Cycle 2 health check.
- Receipt Log heat panel (heat, test certificate, QC status, same heat elsewhere, Heat Number Trace).
- Handover note `docs/cycle2_handover.md`; README feature map for C2-01 to C2-24.
- System Console Check 22: the whole chain end to end.

## 0.21.0 – 0.21.2 — C2-24 print formats

- PO, RFQ cover letter, vendor chase letter, scrap weighment slip, gate pass, blind count sheet and CSM
  return challan on the official PEPL letterhead (PDF button, Print button, RFQ and chase e-mails).
- PEPL formats are the defaults; screen preview shows the letterhead bands.

## 0.20.0 — C2-23 Procurement Command Centre

- Workspaces Buyer's Desk and MD Stores Overview; six number cards; Procurement Funnel report.

## 0.19.0 — C2-22 form panels

- One panel style on every key purchase and stores form; several panels per form.

## 0.18.0 – 0.12.0 — C2-15 to C2-21

- Heat numbers and Receipt Log (C2-15), customer-supplied material (C2-16), vendor payments and MSME
  (C2-17), Scrap Register (C2-18), reorder engine (C2-19), cycle count with ABC (C2-20), consumables
  issued and % of sales (C2-21).

## 0.11.0 – 0.5.0 — C2-07 to C2-14

- Material Request from Sales Order, Supplier Approval gate, RFQ by RM group, Quotation Comparison,
  PO approval by value, Purchase Tracker, chase list and letter, delivery letdowns and score.

## 0.4.0 – 0.4.2 — C2-01 to C2-05

- Live audit, Purchase & Stores rulebook, supplier fields, seven-class stock tree and stores, Capital
  Equipment Register.

## 0.3.0 and earlier — Foundation and Work Package A

- pepl_os app, CI, shared helpers, Override Log, Job Run and System Health; access audit, role profiles
  and access matrix, delete restriction, change / view tracking, audit trail report, log retention.
