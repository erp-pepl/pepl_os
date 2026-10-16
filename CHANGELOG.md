# Changelog — pepl_os

Entries for the Master System Document. Newest first.

## 0.24.1 — from CI run #19 (325 tests, 2 errors)

- Tests only (no change to how the system works): the two tests that check a System Parameter's stored
  default read it straight from the Singles table. `frappe.db.get_value("Singles", …)` now sorts by a
  `creation` column that table does not have. New test helper `stored_single`.
- Check 24 rev 2 in `docs/checks/`: its test items are not sales items, so India Compliance (installed on the
  bench and demo, not on CI) does not ask for an HSN/SAC code.

## 0.24.0 — Shift Production Entry (C3a-X1)

- **PEPL Shift Production Entry (SPR)**: one entry per machine, shift, day and operator, with four tables:
  **Production** (time blocks against open Job Cards of that machine, good and rejected quantity, a reason
  for every rejection), **Downtime** (every stop by Downtime Category; stop type and breakdown copied in),
  **Tool Changes** (time, tool, reason, photo) and **Consumables** (item, quantity, store).
- Times are clock times inside the shift; in a night shift the early-morning times belong to the next day.
  Rows may start / end a little outside the shift (System Parameters). Refused: a row outside that window,
  To before From, two rows of one entry overlapping, an overlap with another entry on the same machine (any
  operator), a second entry for the same machine / shift / day / operator, a future date, an inactive shift,
  operator, machine or downtime category, a Job Card of another machine, more good quantity than the Job
  Card is for (ERPNext's over-production % allowed), a consumable that is not a Consumables stock item.
- **Submit** only when no more than the allowed minutes of the shift are unexplained, and every tool change
  has a photo (both in System Parameters). Submit adds the production blocks to the Job Cards as time logs
  (good quantity as completed quantity) and issues the consumables as one Material Issue against the machine
  group, so the C2-21 consumables report counts them. **Cancel** takes both back; refused once a Job Card is
  submitted.
- Panel: planned minutes, production / downtime minutes and what is not explained, good / rejected and
  rejection %, breakdown stops, missing photos, and after submit the Job Cards and the Stock Entry.
- System Parameters → Production: minutes allowed before / after the shift (30), minutes allowed
  unexplained (15), tool change needs a photo (on).
- Foreman (Manufacturing User) creates and submits; Production Manager also cancels and amends; only the
  System Manager deletes. In the Role Access Matrix.
- System Console Check 24; Check 23 rev 2 (console-safe) in `docs/checks/`.

## 0.23.0 — Cycle 3a starts: shop-floor masters (C3a-X2)

- **PEPL Shift**: start, end and breaks; planned production minutes worked out (a shift ending before it
  starts runs past midnight). Same start and end, negative breaks or breaks as long as the shift are refused.
- **PEPL Downtime Category**: Unplanned / Planned / PM-Calibration, and "Machine Breakdown" (counts for
  MTBF / MTTR; only for unplanned stops). Each category says in plain words what it does to OEE.
  16 starting categories are created once; PEPL may rename, disable or remove them.
- **PEPL Operator**: employee code, name, status, usual shift, optional ERPNext login (one login per
  operator), kiosk **PIN** (digits only, length from System Parameters, stored encrypted, never shown) and
  **machine skills** per machine group with level 1–4 and validity. Panel shows PIN state and every skill,
  red when expired. PINs are checked per operator (code + PIN), so two people may have the same PIN.
- System Parameters → new **Production** tab: Operator PIN Digits (4, allowed 4–6).
- Production Manager creates and edits these masters; Foreman reads them; only the System Manager deletes.
  Changes tracked; listed in the Role Access Matrix.
- System Console Check 23.

## 0.22.8 — demo site, second look

- Number cards Overdue Deliveries, POs Due This Week and Supplier Documents Expiring are counts and now
  show "0", not "Rs 0.00" (a currency on the card made Frappe show every value as money).

## 0.22.7 — from the first run on the demo site

- Command Centre: the six number cards and the "Purchase Tracker last refreshed" line now show on
  both workspaces. Frappe draws a workspace block only when its name equals the label of its row; the
  blocks named the Number Card itself, so they stayed blank. Test now checks Frappe's rule.
- Buyers Desk opens from the desk icon. The apostrophe in "Buyer's Desk" made the address
  "buyer's-desk", which Frappe could not find ("Page not found"). Name, title, sidebar and icon are
  now "Buyers Desk" (the heading on the page still reads Buyer's Desk).
- PEPL System Health: a new monthly job shows "Waiting for First Run" (blue, healthy) until its first
  1st of the month, instead of "Never Run"; the health check lists it as information.

## 0.22.6 — from CI run #15 (260 tests, 2 errors)

- CI only: the test site gets a local address for PDFs. wkhtmltopdf fetches the print stylesheet from
  the site's own address; on the CI machine "test_site" is not a real address (HostNotFoundError).
  A small local web server answers with stand-in files. No change to how the system works.

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
