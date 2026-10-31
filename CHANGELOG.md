# Changelog — pepl_os

Entries for the Master System Document. Newest first.

## 0.48.0 — Daily Stand-up, exception-only (C3a-B7)

- The morning stand-up now lists **only what needs attention**, each part only when it has something, numbered as
  shown: machines below the OEE target (plus one line "n of m machines at or above the OEE target"); unplanned
  stops of at least **Stand-up: Minimum Stop Minutes** (default 30; breakdowns marked; planned stops never);
  machines without a shift entry; Job Orders at delivery risk; **orders running LD** and how many start LD within
  the look-ahead (C3a-B5); **work waiting** in front of a machine group longer than the bottleneck warning
  (C3a-B4); job work overdue; **rejected pieces waiting for Stores to weigh** (C3a-B6). Nothing to report:
  "All clear".
- The record keeps **Things Needing Attention** and **All Clear**; the e-mail subject says "n exception(s)" or
  "all clear". Each part is built on its own: one that fails is left out and logged, the stand-up still goes out.
- **Stand-up: Exception-Only** (System Parameters → Production, on): untick it for the full page as before.
- Check 48.

## 0.47.0 — Shift-entry rejections go to the Scrap Register (C3a-B6)

- When a Shift Production Entry is submitted, its rejected pieces become a **Scrap Weighment** (source Rejection),
  linked to the entry (new fields Shift Production Entry, Rejected Pieces): scrap item = the made item's new
  field **Scrap Item when Rejected** (Item, Inventory section), else System Parameters → **Rejection Scrap Item**;
  weight = rejected pieces x the item's Weight Per Unit (Kg or Gram); submitted at once at the scrap rate of the
  day into Scrap Yard. If the Job Order's BOM uses customer-supplied material, the CSM twin of the scrap item goes
  into CSM Scrap at zero against the Job Order's Sales Order.
- Scrap item, weight per unit or scrap rate missing: nothing is posted and Stores gets one ToDo on the entry
  (rule PRD-REJECT-SCRAP). A failure never stops the entry.
- Cancelling the entry cancels its weighments (and their scrap receipts) and closes the ToDo.
- The entry's Shift panel says where the rejected pieces went. New setting **Rejections to Scrap Register** (on).
- Check 47.

## 0.46.1 — LD Exposure: terms written as people write them (C3a-B5 fix)

- CI #52 (1 of 611): the LD Terms column read "0.5% per week, cap 10.0%"; it now reads "cap 10%" (rate and cap
  written without needless decimals, as everywhere else). Regression test. Check 46 unchanged.

## 0.46.0 — LD Exposure report (C3a-B5)

- **Report "PEPL LD Exposure"** (Production Command Centre → Reports): for every open Sales Order (submitted, not
  fully delivered) with an LD clause - late days x the contractual rate (per week or day, a part counted as a whole),
  capped as the clause says, using the order's own terms (C3a-X11). Columns: terms, days late, late lines, pending
  quantity, **LD so far**, **LD in N days** if nothing more is delivered, the LD added in that time, the cap and how
  much of it is used. Red = LD running; orange = LD starts within the look-ahead; green = on time; grey = no LD
  clause (only when "Only orders with LD terms" is unticked). "Show: Lines" gives each late or soon-due line.
- New setting **LD: Look-Ahead Days** (System Parameters → Production, default 7, 0-365).
- Bottleneck report: the summary now says "waiting in front of it now" (the count is for the bottleneck group).
- Check 46.

## 0.45.0 — Bottleneck report (C3a-B4)

- **Report "PEPL Bottleneck"** (Production Command Centre → Reports): how long work waits in front of each machine
  group between Job Order operations, from the Job Card time logs (where the shift entries post their blocks).
  Wait = this operation's first start - the previous operation's finish (complete: good quantity logged reaches the
  Job Card quantity, or the Job Card is submitted). Started before the previous one finished = "Overlapped" (no
  wait). Previous finished, this one not started, Job Order open = "Waiting now" with the hours so far. The first
  operation of a Job Order has no wait. Clock hours.
- Per machine group: waits, average / longest / total wait, overlaps, jobs waiting now and the oldest, run hours;
  ranked by average wait; the first is marked the bottleneck. "Show: Operations" lists each wait.
- New setting **Bottleneck: Wait Warning Hours** (System Parameters → Production → Bottleneck, default 8): a group
  waiting longer on average is red; a group with work waiting now is orange.
- Check 45.

## 0.44.1 — HR-lite: skill expiry read from any row (C3a-B3 fix)

- CI #49 (1 of 595): the skill-expiry rule read `row.valid_until`, which works on Frappe rows but not on a plain
  dict, so it failed in the unit test. It now reads `row.get("valid_until")`. The screens were not affected
  (Check 44 passed 22/0); the test is the regression test. Check 44 unchanged.

## 0.44.0 — HR-lite: operators, skill matrix, shift eligibility (C3a-B3)

- **Operator ↔ Employee:** new field **Employee** on PEPL Operator. When set, the operator's name, joining date and
  login come from the Employee, and an Employee who is Left / Inactive / Suspended makes the operator Inactive (no
  kiosk, no shift entry). Saving the Employee updates its operator. One Employee = one operator.
- **Eligible Shifts** on the operator (empty = any shift); the Default Shift must be one of them. New setting
  **Shift Eligibility Check** (System Parameters → Production → Operators (HR-lite), default Warn): Warn shows
  "not set to work the … shift" on the entry's Shift panel (Desk and kiosk); Block refuses the shift entry and the
  kiosk sign-in.
- **Report "PEPL Skill Matrix"** (Production Command Centre → Reports): every operator against every machine group -
  level 1-4, green at or above the Minimum Skill Level, orange below it or expiring, red expired; a last row with
  the qualified operators per group (red below **Minimum Qualified Operators per Machine Group**, default 2); a
  To Do column per operator (no PIN, no skills, no default shift, no Employee, skills expired / expiring).
- The operator panel adds the Employee, the eligible shifts and skills expiring within **Skill Expiry Warning
  Days** (default 30).
- No payroll. Check 44.

## 0.43.1 — Estimate vs Actual Cost: Manufacture entries on ERPNext v16 (C3a-B2 fix)

- CI #47: a Job Order with a Manufacture entry stopped the report with "Unknown column 'is_scrap_item'" - ERPNext
  v16 replaced that field with secondary items. Material is now told apart by warehouse only: rows taken from a
  store are consumed, rows put into a store that are not the finished item (scrap, by-products) are returned and
  taken off. Regression test added. Check 43 unchanged.

## 0.43.0 — Estimate vs Actual Cost report (C3a-B2)

- **Report "PEPL Estimate vs Actual Cost"** (Production Command Centre → Reports; Job Order → View → Cost vs
  Estimate): for each Job Order, the CST estimate a piece against what it really cost a piece, in four parts -
  material, machining, job work & other, overhead - with the variance and variance %. "Show: Item" adds the Job
  Orders of each item together.
- Estimate: the CST of the Sales Order's tender for that item; else the item's latest Approved / Used-in-Bid CST
  (Drafts never count). Added up exactly as the CST adds up its subtotals.
- Actual, the same way as the weekly CPC: material = what the Manufacture entries consumed less scrap returned
  (before the first Manufacture entry: BOM material x pieces worked, and the note says so); machining = run minutes
  on the submitted shift entries x Machine-Hour Rate + their consumables shared by run minutes; job work & other =
  the extra costs typed on the Manufacture entries (ERPNext's own operating-cost rows are left out); overhead =
  Overhead (%) on all of it; a piece = total ÷ pieces made (or good pieces reported, until finished goods are
  booked).
- New setting **Costing: Variance Warning %** (System Parameters → Production, default 10): above it the row is red.
- Check 43.

## 0.42.3 — Kiosk: morning times shown again (C3a-B1 fix)

- CI #45: a saved kiosk row starting at 08:00 came back to the page as "8:00:" (the database's time text cut at five
  characters), which the tablet's time box cannot show - a morning row looked blank after Save or sign-in, and the
  shift list read "8:00:-16:30". Times now always come back as HH:MM (08:00). Regression test added; Check 42 rev 3
  checks the times.

## 0.42.2 — Kiosk: a kiosk login opens the kiosk after logging in (C3a-B1)

- A kiosk login (role PEPL Kiosk, no Desk access) landed on "Not Permitted" at /desk after logging in. It now
  lands on the kiosk: the **PEPL Kiosk** role's home page is `kiosk`, and every kiosk login gets
  **Default App = pepl_os**, whose page (shown only to kiosk logins) is `/kiosk`. New kiosk logins are set when
  saved; kiosk logins made before are set on migrate. A Default App someone has already chosen is kept; Desk
  users are not touched. The tablet then picks its machine (or opens `/kiosk?machine=<machine>` once and is
  bookmarked).
- Tests added; Check 42 rev 2 (section 7).

## 0.42.1 — Kiosk: the entry's company (C3a-B1 fix)

- CI #43 (6 kiosk tests): a new kiosk entry was refused with "Value missing: Company". A kiosk login has no
  default company (the bench worked only because its site has one). A new entry now takes the company of the
  Job Card on its first row, else the site's default company, else the only company; with none of these it asks
  for a Job Card on the first row. Regression test added.

## 0.42.0 — Shift-entry kiosk and foreman view (C3a-B1)

- **Kiosk page** `/kiosk?machine=<machine>` (website, not the Desk) for a tablet beside each machine. The tablet is
  logged in once with a kiosk login (new Role Profile / role **PEPL Kiosk**, no Desk access). An operator signs in
  with **employee code + PIN**, picks today's or yesterday's shift, and enters his shift: production blocks against
  the machine's open Job Cards (good / rejected / reason), stops by downtime category, tool changes with a photo
  taken on the tablet (resized before sending). Save keeps a draft; the page shows the same help as the Desk form
  (gaps, Job Card left, speed, skill) and the Shift panel; **Submit** submits the same Shift Production Entry. A
  Soft Block skill shortfall asks the operator for a reason, logged in the Override Log with his code.
- Safety: wrong PINs lock the code after **Kiosk: Wrong PIN Tries** (5) for **Kiosk: Lock Minutes** (15); the
  message never says whether the code or the PIN was wrong; a kiosk session ends after **Kiosk: Session Minutes**
  (30) without saving; an operator sees only his own entry of that machine, shift and day; a submitted entry is
  read-only on the kiosk. Consumables stay with Stores in the Desk.
- **Foreman view** `/foreman`: for a day and shift, every machine that runs - Submitted / Draft / Missing,
  operators, good / rejected, minutes not explained, gaps - refreshing every two minutes; entries open in the Desk.
- The Shift panel rows are built once (spr.panel_rows) for the form and the kiosk.
- Check 42.

## 0.41.0 — Production Command Centre (C3a-CC)

- New workspace **Production Command Centre** (module PEPL Production, with its sidebar) for the Production Manager,
  foreman, Manufacturing users and the CEO. Built to the render rule found in Cycle 2: no apostrophe in the title
  (the address is made from it) and every block named by the label of its row, so Frappe draws it.
- Five cards:
  - **OEE Yesterday** - all machines, each Daily OEE weighted by its planned production time; opens yesterday's
    Daily OEE list;
  - **Jobs at Delivery Risk** - open, unfinished Job Orders due within "Stand-up: Days Ahead for Delivery Risk"
    or late (the stand-up's list); opens them;
  - **Open Job-Work Quantity Outside** - the Job-Work Reconciliation total; opens the report;
  - **Rejection % (7 days)** - rejected / (good + rejected) on the shift entries of the 7 days before today; opens
    them;
  - **Top Downtime Cause (7 days)** - the category with the most stopped minutes, its minutes and share (a name,
    so a card-sized block, not a number card); opens the new report **PEPL Downtime by Cause**.
- Today's work: shift entries to submit, Job Orders to release, Job Orders in process, days below OEE target, open
  Production Plans, Job-Work Reconciliation; link cards Production, Shop Floor, Results, Reports.
- Check 41.

## 0.40.0 — Production configuration (C3a-C1)

- Report **PEPL Production Settings**: every Production setting (System Parameters → Production, the pepl_sales
  production parameters on the first tab, the Manufacturing Settings PEPL OS relies on, the active downtime
  categories) with value, default and status ("Default, to confirm with PEPL" / "Changed from default") - the
  sheet confirmed with the Production HOD.
- **OEE thresholds**: new targets per factor - OEE: Availability Target % (90), Performance Target % (95),
  Quality Target % (99). The Daily OEE names the factors below their target ("Quality 95 % (target 99 %)") in a
  new field and in its headline.
- **Standard-time governance** (System Parameters → Production → Standard Times): look-back days (90), minimum
  runs before a suggestion (5), suggest from Median / Average, largest change per approval (20 %), approving role
  (empty = PEPL Production Manager). Read by the learning-standards workflow (Work Package E2); the band a run may
  differ from its standard is the pepl_sales "Cycle Deviation Threshold Low / High" (0.8 / 1.2).
- **One measure for slow / fast runs**: the shift entry aids (C3a-P5) now flag a row whose actual cycle is over
  standard x High ("slower than standard") or under standard x Low ("faster than standard: check the quantity");
  the v0.39.0 field "Shift Entry: Slow Below % of Standard Speed" is removed by a patch.
- **Downtime category cleanup**: report **PEPL Downtime Category Review** (use in the look-back days, in all, last
  used; look-alike names, never used, inactive but used); on the category form a "Use and cleanup" panel and, for
  the Production Manager, **Merge into another category** (same stop type and breakdown flag only): every
  shift-entry row moves, the old category is switched off with a note, the Daily OEE and Machine Weeks it touched
  are rebuilt.
- Check 40; Check 39 rev 2 (slow / fast by the cycle deviation band).

## 0.39.1 — Tests only: P4 test independent of Selling Settings

- CI #39 (whole suite on 0.36.0–0.39.0): the C3a-P4 test that puts the same part on two Sales Order lines was
  refused on the CI site, where Selling Settings "Allow Item to Be Added Multiple Times in a Transaction" is off
  (the bench has it on, so Check 38 passed). The test now switches the setting on for itself. No app change.
- Check 38 rev 2 does the same, so it runs on any site (demo / live).

## 0.39.0 — Entry aids on the Shift Production Entry (C3a-P5)

- A saved **Shift Production Entry** shows a panel **Entry aids** next to the Shift panel:
  - gaps: each stretch of the shift no row covers (this entry and the other entries of the same machine, shift
    and day), with the total and the shift's break; orange when more than the break + the minutes allowed
    unexplained. On a draft, **Add rows for the gaps** adds one downtime row per gap with the times filled in;
    the operator picks the category and saves;
  - Job Cards: target, done before (other entries' time logs), this entry's good quantity, what is left; red
    over the target, green when finished;
  - speed: per production row, pieces x the Job Card's standard minutes a piece against the minutes taken;
    below the new System Parameter **Shift Entry: Slow Below % of Standard Speed** (Production → Shop Floor,
    default 80) the row is orange - "check the time and the quantity";
  - open Job Cards on the machine that the entry does not use yet.
- Fix (C3a-X1): the Shift panel writes quantities as people do ("Good 6 · Rejected 1", it said "6.0"); regression
  test added.
- Check 39.

## 0.38.0 — Customer-supplied material panel on the Job Order (C3a-P4)

- A **Job Order** (draft or submitted) whose BOM uses customer-supplied material shows a panel **Customer-supplied
  material**, one line per CSM item: CSM a piece x pieces still to make = what this Job Order needs; what the
  Sales Order holds in the CSM stores and how many pieces that is enough for; what is already issued or consumed
  and what sits in CSM Scrap.
- Green when the order holds enough for everything the whole order still needs (its lines' BOMs less what is
  already issued or consumed); orange when it covers this Job Order but not the whole order ("the whole order
  still needs …"); red "short by …" when this Job Order cannot be finished from what is held. "CSM Reconciliation
  Tolerance (kg)" is allowed. Material already issued to the shop floor counts towards the Job Order.
- A Job Order using customer material without a Sales Order is red (customer material moves only against its
  order). Built on the C2-16 CSM balance and the C3a-X9 CSM-per-piece rule, so all three agree.
- Check 38.

## 0.37.0 — Job-Work outstanding panel (C3a-P3)

- **Supplier** form of a job worker (a Supplier named as "Job Worker" on a store): panel **Job work outstanding** -
  one line per item still outside: quantity, since when (first in, first out), and "due back by" (sent + Job-Work
  Return Days), "n days overdue", "GST one-year limit on …, n days left" or "GST one-year limit passed"; green /
  orange / red; the worst first. Headline: items outside, their value, how many are overdue or near the GST
  limit. Button **Job-Work Reconciliation** opens the report for this job worker. Ordinary suppliers get no panel.
- **Stock Entry** form that sends material to, or brings it back from, a job worker's store: what is outside there
  now for the items of the entry ("before" / "after this entry"); a draft bringing back more than is outside gets
  a red line.
- Built on the job-work reconciliation (C3a-X8), so panel and report always agree.
- Fix (C3a-X6): the double-booking message now names the end date of a booking that runs past midnight
  ("08-12-2026 09:00 - 09-12-2026 05:00"; it said "09:00 - 05:00"). Found in Check 36; regression test added.
- Check 37.

## 0.36.0 — Production Plan machine load (C3a-P2)

- A saved **Production Plan** shows a **Machine load** panel: for every machine the plan uses, over the days it
  uses it, the hours of this plan (rows not yet on a Job Order, laid out as the double-booking check lays them
  out, plus open Job Orders made from this plan) and the hours already booked on those days (other open Job
  Orders and other open plans) against the machine's available hours, with the load %.
- Available hours = hours a day (the machine's ERPNext Working Hours; when none, the planned hours of all active
  PEPL Shifts) x jobs it runs at once (Production Capacity) x working days (holidays of the machine's Holiday
  List, else the company's, left out; a half day counts half).
- Red above 100 %, orange from the new System Parameter **Load View: Warning at % of Machine Hours** (Production
  → Job Orders, default 85), green below; a machine with no hours anywhere shows its hours in grey. The headline
  names the busiest machine; double-bookings on the plan are pointed out.
- Check 36.

## 0.35.1 — Job Order panel: quantities without ".0" (C3a-P1 fix)

- The Job Order status panel now writes quantities as people do: "Made 0 of 10", "8 good, 2 rejected",
  "8 of 10" (it showed "0.0 of 10.0"); fractions keep up to three decimals (2.5, 0.125). Found by Check 35 on
  the bench; regression test added.
- Check 35 rev 2 (also checks that no quantity shows ".0").

## 0.35.0 — Job Order status panel (C3a-P1)

- A submitted **Job Order** (Work Order) shows a status panel at the top of the form:
  - quantity: made of the target (finished goods booked) and what the shop floor reported good / rejected on
    the Shift Production Entries of this Job Order;
  - routing: every step in order with its machine, done against the target (from its Job Card, including shift
    entries not yet submitted on the Job Card) and its state; the step being worked on is marked ▶;
  - delivery: due date with days left (orange within 3 days) or days late (red);
  - LD: when the Sales Order carries LD, the LD so far on this Sales Order line.
- Check 35.

## 0.34.0 — Machine-Hour Rates linked to the machine group (C3a-R1)

- System Parameters → Production Costing → **Machine-Hour Rates**: Machine Group is now a link to the machine
  group (ERPNext Workstation Type) instead of typed text, so a machine's rate is found from its group without
  spelling mistakes. A rate for a group that does not exist is refused; the same group twice is still refused.
- One-time move on every existing site (patch): each old row is pointed at the matching machine group in any
  upper / lower case; a typed group with no machine group yet gets one, so no rate is lost.
- The weekly machine cost (C3a-X4) finds the rate through the link (else the machine's own Hour Rate).
- Check 34 (and Check 29 again as the regression check).

## 0.33.0 — Contractual LD rate on the Sales Order (C3a-X11)

- New section **Liquidated Damages (LD)** on the Sales Order: LD Applies, LD Rate %, per Week / Day (of delay or
  part thereof), LD Cap %, Grace Days, Charged On (Value of Late Items / Whole Order Value) and the clause
  reference. Fixed once the order is submitted (amend to change).
- A new order of a sector listed in System Parameters → Production → **LD: Sectors with LD by Default**
  (Railways, Defence) starts with the default clause (**0.5 % per week, cap 10 %**); other orders start without
  LD. An LD clause with a missing or impossible rate or cap is refused.
- **LD for late delivery** as on any date: quantity delivered after the delivery date + grace days, and quantity
  still pending once that date has passed, each at value × rate × weeks (or days) late, capped per line at the
  cap % of the value delivered late (or, on Whole Order Value, at the cap % of the order). A submitted order with
  LD shows its terms and today's LD exposure in a panel. This is what the LD-exposure report (B5) builds on.
- Check 33; Check 32 rev 2 (the e-mail step follows the site's e-mail set-up).

## 0.32.0 — Daily Stand-up (C3a-X10)

- New record **PEPL Daily Standup** (Daily Stand-up), one per day, built by the system every morning at 07:45
  for the day before and e-mailed to the members of **Standup Email Group** (System Parameters, first tab).
- The page: (1) shop floor yesterday - each machine's Daily OEE, A / P / Q, good, rejected, breakdowns,
  lowest OEE first, below-target marked; (2) top stops by downtime category; (3) machines without a shift
  entry (worked in the last 30 days, nothing yesterday); (4) Job Orders at delivery risk - open, not finished,
  due within **Stand-up: Days Ahead for Delivery Risk** (System Parameters → Production, default 3) or late,
  overdue marked; (5) job work overdue.
- Headline numbers on the record (machines reported, average OEE, below target, good / rejected / rejection %,
  downtime minutes, top stop, breakdowns, machines without entry, Job Orders at risk / overdue, job work
  overdue) for the Command Centre. Building again updates the same day. The form has **Build again** and
  **E-mail now** for the Production Manager. Without an outgoing e-mail account the record says so and nothing
  breaks.
- Check 32.

## 0.31.0 — CSM consumed by the Delivery Note; Delivery Note material gate (C3a-X9)

- When a Delivery Note delivers parts made from customer-supplied material (CSM), it works out the material
  they used: for each Sales Order line, CSM per piece from the line's Job Order BOM (else the item's default
  BOM; multi-level BOMs flattened) × the quantity delivered on all Delivery Notes of the order, less what was
  already issued to production against the order. The draft shows it (**Customer Material Consumed**).
- On submit it posts one **Material Issue** per Sales Order from the CSM stores (zero value, linked to the
  Delivery Note, heat lots first in, first out, so the heat number follows the material). Cancelling the
  Delivery Note cancels it. CSM Balance by Order shows the material as consumed.
- **Material gate** (existing parameter "Delivery Note Material Gate Mode"): a delivery needing more customer
  material than the order still holds is refused at submit (Warn at Validate, Block at Submit - the draft is
  saved with a warning) or not saved at all (Hard Block); Off lets it go and consumes what there is.
  Differences within "CSM Reconciliation Tolerance (kg)" are ignored.
- If posting the issue fails, the delivery still goes and the Stores notification owner gets a ToDo
  (PRD-CSM-NOT-CONSUMED). Check 30 rev 3 is in this release.
- Check 31.

## 0.30.0 — Job-work reconciliation (C3a-X8)

- **Job worker's store**: a Warehouse with the new field **Job Worker** (a Supplier) holds PEPL's material at
  that job worker (plating, heat treatment ...). A "Send to Subcontractor" must go to such a store.
- **Job-Work Movement** on the Stock Entry: material moved into a job worker's store is marked **Sent to Job
  Worker** automatically; material coming out of it must say **Received after Processing** or **Returned
  Unprocessed** (a return entry is Returned Unprocessed by default). Sending and bringing back in one entry
  is refused. Subcontracting Receipts (ERPNext's own job-work flow) count as received.
- **PEPL Job-Work Reconciliation** (report): per job worker and item, as on any date - sent, received,
  returned, adjusted (e.g. a stock count correction at the job worker), balance at the job worker, value,
  oldest quantity outside (first in, first out), days outside and status: Clear / Outside / Overdue (beyond
  **Job-Work Return Days**, default 30) / GST limit near (within **Job-Work GST Warning Days**, default 30, of
  the one-year limit for inputs sent for job work, CGST section 143) / GST limit passed.
- Every morning one ToDo per job worker holding overdue material goes to the Production notification owner
  (rule PRD-JW-OVERDUE; High when a GST limit is near); it closes by itself once nothing is overdue. The
  Production Manager can run the check at any time.
- Check 30.

## 0.29.0 — Weekly MTBF, MTTR and CPC per machine (C3a-X4)

- New record **PEPL Machine Week** (Machine Week): one per machine and week (Monday to Sunday, by shift date),
  built by the system from the submitted Shift Production Entries and never typed in.
- **MTBF** = run hours ÷ breakdowns; **MTTR** = breakdown minutes ÷ breakdowns. A breakdown is a downtime row
  whose category is marked "Machine Breakdown". A week without a breakdown says so (no MTBF / MTTR).
- **CPC (cost per component)**: machine cost = run hours × the Machine-Hour Rate of the machine's group (System
  Parameters → Production Costing; else the machine's own Hour Rate; else a note asks for it); consumables =
  the value of the Material Issues posted by the week's entries; overhead = Overhead (%) on top. The machine's
  CPC is its conversion cost ÷ good pieces. **Items Made** shows each item: good and rejected pieces, run
  minutes, material (BOM raw-material cost a piece × pieces made), its share of machine and consumables by run
  minutes, overhead, total and **CPC per good piece**.
- Built at once when a shift entry is submitted or cancelled, and every Monday at 02:30 for the week before.
  Production Manager can rebuild the weeks of a date range (e.g. after a rate change). Never stops a shift
  entry; a failure goes to the Error Log. Accounts Manager can read the records.
- Check 29.

## 0.28.1 — from CI run #26: two operators sharing a shift (fix to C3a-X1)

- **Fix:** when two operators share one machine in one shift, each Shift Production Entry holds only part of
  the shift, so each was refused on submit ("240 minutes of the shift are not explained"). The minutes not
  explained are now counted for the shift as a whole: the production and downtime of the other entries
  (draft or submitted) of the same machine, shift and day count too. The usual way on the floor: both
  operators save their entry, then either submits. One entry for half a shift on its own is still refused.
- Regression tests for the shared shift; the two Daily OEE tests that share a shift now save both entries
  before submitting, as on the floor.
- Check 28 rev 2 (adds section 7: two operators share one shift).

## 0.28.0 — Daily OEE per machine (C3a-X3)

- New record **PEPL OEE Daily** (Daily OEE): one per machine and shift date, built by the system from the
  submitted Shift Production Entries and never typed in. It shows Availability, Performance, Quality and OEE
  with every minute behind them: planned minutes (each shift worked counted once, even with two operators),
  planned stops, PM / Calibration, planned production time, run time, unplanned stops, breakdowns (count and
  minutes, for MTBF / MTTR next), unexplained minutes, good and rejected quantity, standard minutes made.
- Availability = run time ÷ planned production time; Performance = pieces made × the Job Card's standard
  minutes a piece ÷ run time; Quality = good ÷ (good + rejected); OEE = A × P × Q. Performance above 100 %
  (a loose standard time) is shown as it is, used as 100 % in OEE and noted on the record.
- PM / Calibration follows the existing parameter "OEE: Exclude PM/Calibration from Planned Time" (on: left
  out of planned time; off: an unplanned stop). New **OEE Target %** (System Parameters → Production, default
  65): days below it are marked **Below Target**.
- Built at once when a shift entry is submitted or cancelled (the last entry cancelled removes the day), and
  every night for yesterday. Production Manager can rebuild a date range (up to 92 days). Building OEE never
  stops a shift entry; a failure goes to the Error Log.
- Check 28.

## 0.27.1 — from CI run #24 (1 error)

- Tests only (no change to how the system works): the Hard Block test logged an override reason of 8
  characters, which the Override Log rightly refuses (at least 10). The test now gives a full reason, so it
  checks what it is meant to check: that even a valid reason cannot unlock Hard Block.

## 0.27.0 — Production Plan machine double-booking block (C3a-X6)

- Saving a Production Plan lays out each row the way ERPNext lays out a Job Order: from the row's Planned
  Start, the BOM's operations one after another (same sequence number = together), quantity × BOM minutes,
  plus Manufacturing Settings → Time Between Operations. Each operation books its machine for that time.
- The bookings are compared with what already holds each machine: the plan's other rows, open Job Orders
  (submitted, Not Started / In Process; operations not completed; at the planned times ERPNext stored when
  capacity planning is on, otherwise laid out from the Job Order's Planned Start) and other open Production
  Plans' rows not yet on a Job Order. A machine is double-booked when more jobs overlap than its
  **Production Capacity** (Workstation; 1 = one job at a time). Back-to-back jobs do not clash.
- The clashes are listed on the plan (**Machine Double-Bookings**) and shown on save. A draft is always saved.
  On submit, **Machine Double-Booking Mode** (System Parameters → Production, default Soft Block) decides:
  **Advisory** – warning; **Soft Block** – a reason is asked, written to the Override Log as
  PRD-DOUBLE-BOOK (warning only when "Require a Reason for Every Override" is off); **Hard Block** – the plan
  cannot be submitted until the clash is resolved.
- Check 27.

## 0.26.0 — Job Orders drafted from the Sales Order (C3a-X5)

- Submitting a Sales Order drafts one **Job Order** (ERPNext Work Order) for each manufactured line (stock
  class Finished Goods or WIP / Semi-Finished) that has a default BOM: quantity not yet on a Job Order of that
  line, linked to the Sales Order line and project, finishing into the line's store through WIP Main Workshop,
  due on the line's delivery date, with the BOM's operations (submitting it makes the Job Cards). Production
  reviews and submits it. The Job Order shows **Drafted from the Sales Order**.
- A manufactured line without a default BOM gets no Job Order: a ToDo **PRD-NO-BOM** goes to the Production
  notification owner. Bought-out and raw material lines keep going to the Material Request (C2-07).
- Submitting again or a second run never doubles a Job Order. Cancelling the Sales Order deletes its draft Job
  Orders. If drafting fails the Sales Order is still submitted and Production gets a ToDo
  **PRD-JO-DRAFT-FAILED** (details in the Error Log).
- System Parameters → Production → **Draft Job Orders from Sales Orders** (on by default).
- Check 26.

## 0.25.0 — Operator skill check (C3a-X7)

- Shift Production Entry checks the operator against the machine: the operator's level on the machine's group
  (valid on the shift date) must reach **Minimum Skill Level to Run a Machine** (System Parameters →
  Production, default "3 - Runs independently"). The entry shows the level found and **Skill Check**:
  Qualified / Not qualified / Not checked (machine without a group – never blocked).
- What happens when the operator falls short follows **Operator Skill Check Mode** (System Parameters, first
  tab): **Advisory** – a warning; **Soft Block** – the entry saves, and submitting it asks for a reason, written
  to the Override Log as PRD-SKILL (warning only when "Enforce Override Reason" is off); **Hard Block** – the
  entry is refused.
- The panel shows the operator's skill line (green qualified, orange not qualified with the mode).
- Check 25; Check 24 rev 3 (its operators are skilled on the VMC group, so it passes in any mode).

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
