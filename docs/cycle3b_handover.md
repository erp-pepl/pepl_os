# Cycle 3b · Quality — handover

App `pepl_os`, module **PEPL Quality**. Works on ERPNext v16 (Quality Inspection) next to `pepl_sales` (which owns
PEPL System Parameters, the Product Master with its drawing revisions, the tender and the document letters).
Versions 0.60.0 – 0.78.0. The user guide is `docs/cycle3b_quality_manager_uat.md`; what changes per role is in
`docs/cycle3b_manuals_annex.md`; what PEPL fills in before go-live is in `docs/cycle3b_pepl_inputs.md`.

## How the chain runs

1. **Purchase Receipt saved** → one draft **QC Inspection** (ERPNext Quality Inspection, Incoming) per line of an
   item inspected on receipt (its stock class is listed in "Incoming QC: Stock Classes", or the item is ticked),
   with the item's **inspection plan** (Quality Inspection Template). No plan → Quality ToDo (QA-NO-QC-PLAN).
   The receipt's **Incoming QC Gate** (Advisory / Soft Block / Hard Block) stops a line whose inspection is not
   submitted, or is Rejected while quantity is accepted.
2. **QC Inspection**: one line per characteristic with its tolerance, the readings in / OUT, the **instrument** used
   and its calibration. The **Calibration Gate** refuses (Hard Block) a reading taken with an instrument that is
   overdue, never calibrated or not in use.
3. **Instruments**: PEPL Instrument + submitted **Calibration Records** (certificate for a Pass, what was wrong for a
   Fail; a Fail puts it Out of Service). Daily job: Quality ToDo for every instrument due soon, overdue or never
   calibrated (QA-CAL-DUE).
4. **NCR** (PEPL NCR) — raised by the system for a rejected inspection (QA-NCR-QI), a customer return
   (QA-NCR-RETURN), an item's rejection rate on a day's shift entries above the threshold (QA-NCR-RATE), a quantity
   rejected by the inspecting agency (QA-NCR-LOT); or by hand. Severity sign-off matrix (Minor / Major / Critical:
   the roles that must sign); closing needs the disposition and every signature; the Quality owner gets a ToDo for
   a system-raised NCR (QA-NCR-OPEN).
5. **CAPA** (PEPL CAPA) — raised by a Critical NCR, or by the repeat Major count within the window; later Major /
   Critical NCRs of the item join it. Containment, five-why, root cause, actions (Correction / Corrective /
   Preventive, who, due, done). Setting it to Closed checks the rules and puts it **Awaiting Verification**; on or
   after the check day (default 90 days) the Quality Manager presses **Verify Effectiveness**: Effective closes it
   (refused while a new Major / Critical NCR came in on the item), Not Effective sends it back to In Progress.
6. **Inspection lots** (PEPL Inspection Lot) for orders inspected by an outside agency: lot request → proof
   inspection → bulk lot offer → the agency's IC (accepted / rejected, IC number and date). The letters stay in the
   order's document tracker (pepl_sales).
7. **Delivery Note** → one draft final QC Inspection (Outgoing) per line of an item inspected before delivery. The
   **Dispatch Gate** stops a line whose final inspection is not Accepted, whose item has an open NCR, or — for an
   agency order — that would ship more than the ICs accepted.
8. **Drawing change**: a new current drawing revision on the Product Master flags every open Job Order of the item
   (PRD-DRAWING-REV); Production acknowledges on the Job Order what the job is made to from now.
9. **Vendor scorecard**: incoming lots accepted ÷ inspected per supplier (Vendor Score Period) and the composite with
   the delivery score (weights); shown on RFQ and Quotation Comparison.

## Panels (on the forms)

| Form | Panel |
| --- | --- |
| Purchase Receipt | Incoming QC: each line's inspection and the gate |
| QC Inspection | each characteristic: tolerance, readings, in / OUT, instrument and its calibration; result on submit |
| PEPL Instrument | fit to measure today, days left, last calibration, history, use, drafts the gate would stop |
| PEPL NCR | status and age, what / from, disposition and cost, signed / still to sign (Sign off), CAPA, dispatch hold |
| PEPL CAPA | target, NCRs, containment, five-why, open actions, effectiveness check (Verify Effectiveness) |
| PEPL Inspection Lot | the steps ✓, the order line (lots, IC accepted, delivered), what comes next |
| Delivery Note | Dispatch QC: final inspection, open NCRs, agency ICs left to ship |
| Job Order | Drawing: revision made to, the change to acknowledge |

## Reports and the Command Centre

**Quality Command Centre** workspace: Open NCRs by Severity, CAPAs Overdue for Verification, Instruments Due Within
30 Days, First-Pass Yield (7 days), Customer Rejections (30 days), Cost of Quality (month); shortcuts for today's work.
Reports: **PEPL Cost of Quality** (rejection − scrap + NCR rework + NCR other + customer, by month or item) and
**PEPL Quality Settings** (every setting with value / default / status, the sign-off matrix in practice). Health:
**PEPL System Health → Download Cycle 3b health check**.

## Scheduled jobs (recorded in PEPL Job Run; status on PEPL System Health)

| Job | When | Does |
| --- | --- | --- |
| `pepl_quality.calibration.daily_calibration_alerts` | daily | instrument states; ToDos for due soon / overdue / never calibrated |
| `pepl_quality.scorecard.daily_vendor_scores` | daily | every supplier's quality score and composite score |

## Rule codes (ToDos and the override Audit Trail)

| Code | Meaning |
| --- | --- |
| QA-IN-QC | receipt line without an accepted inspection, allowed with a reason (Soft Block) |
| QA-NO-QC-PLAN | an item inspected on receipt has no inspection plan |
| QA-CAL-DUE | instrument due soon, overdue or never calibrated |
| QA-CAL-GATE | inspection with an instrument out of calibration, allowed with a reason (Soft Block) |
| QA-NCR-QI / RETURN / RATE / LOT | the NCR raise rules (rejected inspection, customer return, rejection rate, agency rejection) |
| QA-NCR-OPEN | a system-raised NCR to deal with |
| QA-CAPA-OPEN | a system-raised CAPA to work |
| QA-CAPA-VERIFY | a CAPA's effectiveness check day |
| QA-DISPATCH | dispatch with a quality gap, allowed with a reason (Soft Block) |
| PRD-DRAWING-REV | a Job Order's drawing changed: check and acknowledge |

## Settings PEPL owns

All in **PEPL System Parameters → Quality** (and the first tab for the Quality Notification Owner); the report
**Quality Settings** lists each with its value, default and status. Incoming QC stock classes and gate; calibration
alert days and gate; the severity sign-off matrix, the severity of system NCRs, NCR on customer return, rejection-rate
threshold and minimum pieces; CAPA repeat count and window, whys required, target days, verification after days;
dispatch gate; vendor score weights. Changing a value after sign-off is a change request.

## Checks

- Automated tests: GitHub → Actions → CI → Run workflow (fresh site; `tests/test_c3b_*.py`). Acceptance = all green.
- System Console checks 60 and 63 – 78 (one per deliverable; 77 and 78 roll back by themselves; Check 78 runs the
  whole chain end to end). Checks 61 and 62 are CR1 / CR2.
- **Check ALL** (`docs/checks/check_all_c3b.py`, built by `build_check_all.py … c3b`): runs 60 and 63 – 78 as a
  background job and writes the result to a Note "PEPL Check ALL <time>"; each check is undone after it runs.
- **UAT set-up** (`docs/checks/setup_c3b_uat.py`, demo site only, Commit ticked): the Quality Manager and CEO logins,
  plans, items, instruments, supplier, customer and order the UAT guide starts from.

## How releases reach the sites

Local bench → CI green → demo site (backup first, outside working hours) → live site (backup first, outside working
hours). No release reaches a site before its CI is green. Every bug fixed gets a regression test; every release gets
a CHANGELOG entry. After deploy: **Cycle 3b health check** — zero findings expected once PEPL's inputs are in
(information rows excepted).

## Known limits (by decision)

- SPC-lite, the ISO 9001 clause matrix and the FAI checklist are Work Package E (E3 – E5).
- First-Pass Yield is measured on the shop floor (good ÷ good + rejected on the shift entries); rework is not a
  shop-floor quantity, it is an NCR disposition.
- Cost of Quality prices a rejected piece at the item's valuation rate; items without one are listed as not priced.
- An order counts as agency-inspected when it has an inspection lot or its tender says Inspection Required = Yes.
- The verification check day is fixed when the CAPA's actions are complete; a later setting change does not move it.
