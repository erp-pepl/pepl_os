# Cycle 3b UAT · Quality Manager

**Who:** the Quality Manager, with the consultant; the Production Manager for the Major sign-off (F) and the drawing
change (I). **Where:** the demo site, Desk. **How long:** about 2½ hours. Write **Pass** or **Fail** in the last
column. For a Fail, write what you saw.
The consultant first runs `docs/checks/setup_c3b_uat.py` on the demo site (System Console, Commit ticked). It makes
the Quality Manager's login (Role Profile **PEPL Quality Manager**) and a CEO login, the plans **UAT Pin Plan**
(diameter 9.9 – 10.1) and **UAT Shaft Final Plan** (19.9 – 20.1), the items **UAT-QC-PIN** (inspected on receipt) and
**UAT-QC-SHAFT** (inspected before delivery, 40 in FG Stores), the supplier **UAT QC Supplier**, the instruments
**UAT-VC-01** (calibrated 10 days ago) and **UAT-VC-02** (overdue), the customer **UAT QC Railway** with a submitted
order for 30 UAT-QC-SHAFT, and sets the Quality Notification Owner to the Quality Manager.

## A. Settings

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| A1 | Open the report **PEPL Quality Settings** | every Quality setting with value, default and a coloured status | |
| A2 | Look at "Sign-off matrix in practice" | each role with the users who hold it; none red | |
| A3 | Agree each orange "Default, to confirm" row with the consultant | the agreed values entered on System Parameters → Quality turn green | |

## B. Incoming inspection

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| B1 | Purchase Receipt from UAT QC Supplier, 20 UAT-QC-PIN into Bought-Out Stores, Save | the Incoming QC panel: one draft QC Inspection for the line | |
| B2 | Open the inspection, type 10.0 and 10.05, Instrument UAT-VC-01, Save | the line green "in tolerance", the gauge "calibrated until …", "Result on submit: Accepted" | |
| B3 | Change the instrument to UAT-VC-02 and Submit | refused: UAT-VC-02 is overdue (Calibration Gate) | |
| B4 | Back to UAT-VC-01, Submit; Submit the receipt | both go through | |
| B5 | A second receipt of 10; reading 10.4; Submit the inspection | Rejected; an **NCR** is raised (Major, Incoming, the supplier and receipt) and you get its ToDo | |

## C. Instruments

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| C1 | Open UAT-VC-02 | the Calibration panel red "overdue … n day(s) overdue" and "Next: stop using it" | |
| C2 | **New Calibration Record**: today, Pass, certificate UAT-CERT-2, Submit | the instrument "calibrated until …" green | |

## D. NCR

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| D1 | Open the NCR from B5 | the NCR panel: Major, Open, What, From (inspection, receipt, supplier), "Still to sign" | |
| D2 | Disposition Return to Supplier, Save | "cost not entered yet (about … at the item's valuation rate)" | |
| D3 | Enter the cost, Save; press **Sign off** | your signature; "Still to sign: Manufacturing Manager" | |
| D4 | Set Status Closed | refused until the Production Manager signs (section F) | |

## E. CAPA

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| E1 | A third receipt of 10, reading 9.6, Submit | a second Major NCR; with the first it raises a **CAPA** (Repeat Major) | |
| E2 | Open the CAPA | target, both NCRs, "Containment: not recorded", "Five-why: 0 of 5", "Actions: none yet" | |
| E3 | Fill containment, the whys, the root cause, a Corrective Action with Done On; Status Closed | **Awaiting Verification**, "Effectiveness check …: 90 day(s) left"; a ToDo for that day | |
| E4 | **Verify Effectiveness** → Effective | refused: not before the check day | |
| E5 | Verify Effectiveness → Not Effective, with what you saw | back to In Progress, "Found not effective 1 time(s)" | |

## F. Sign-off by severity (Production Manager logs in)

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| F1 | As the Production Manager, open the NCR from B5, **Sign off** | all signed; "Ready to close" | |
| F2 | As the Quality Manager, Status Closed | Closed on … by you; the dispatch hold line gone | |

## G. Dispatch

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| G1 | Delivery Note for 5 UAT-QC-SHAFT to UAT QC Railway, Save | Dispatch QC: a draft final inspection "to be inspected" | |
| G2 | Inspect 20.6, Submit the inspection; Submit the delivery | Rejected → NCR (Dispatch); the delivery asks for a reason (Soft Block) | |
| G3 | New delivery of 5; inspect 20.0; Submit | still held: the shaft's NCR is open | |
| G4 | Close that NCR (disposition, cost, signatures), Submit the delivery | it goes | |

## H. Inspection lot (agency)

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| H1 | On the UAT order: **Create → Inspection Lot**, lot size 20, agency RITES, Save | the lot panel "Next: request the lot number" | |
| H2 | Lot Number Requested On, lot number; Offered On, 20 offered; PEPL Final Inspection | Offered | |
| H3 | Inspected On, accepted 18, rejected 2, IC number and date | Inspected; NCR for the 2 rejected | |
| H4 | Delivery Note of 20 against the order | the gate: "ICs … accepted 18 … this delivery would make 20" | |

## I. Drawing change (Production Manager)

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| I1 | A Product Master for UAT-QC-SHAFT with revision A (drawing file attached); a Job Order for it | Job Order Drawing panel "Made to drawing Rev A" | |
| I2 | Add revision B as current, with what changed | the Job Order red "Drawing changed from Rev A to Rev B …"; a ToDo | |
| I3 | **Acknowledge Drawing Change**: work to B, what was checked | green; the ToDo closed | |

## J. Command Centre and reports

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| J1 | Open the **Quality Command Centre** | the six cards with today's figures; clicking each opens its list or report | |
| J2 | Open **PEPL Cost of Quality**, this month | the NCR costs entered today under NCR other / NCR rework; total | |
| J3 | PEPL System Health → **Download Cycle 3b health check** | an Excel file, one sheet per area | |

**Signed off by** (Quality Manager) ____________________ **Date** __________
