# Cycle 3a · Annex to the training manuals — what changes for each role

## Operator

- Your shift is entered on the **tablet beside your machine**: your employee code and your PIN (never share it).
  Pick today or yesterday and your shift, add a row for each block of work (Job Card, from – to, good, rejected
  and why), each stop (what stopped the machine, from – to) and each tool change (with a photo from the tablet).
- **Save** keeps a draft you can come back to; **Submit** when the shift is complete. After Submit only the foreman
  can change it.
- The help on the right tells you what is not yet covered, how much of the Job Card is left and how fast you ran
  against the standard. Five wrong PINs lock your code for 15 minutes.

## Foreman

- `/foreman`: every machine of the shift — Submitted, Draft or **Missing**, good, rejected, minutes not explained.
  Chase the missing ones before the end of the day; the morning stand-up lists them.
- You correct a submitted entry in the Desk (cancel and amend). Rejected pieces go to the Scrap Register by
  themselves when the item has a weight and a scrap item; otherwise Stores is told to weigh them.

## Production Manager

- A submitted Sales Order drafts its **Job Orders**; you check and submit them. Items without a BOM come to you as a
  ToDo.
- Plan with the **load view** on the Production Plan; the double-booking rule follows the mode set in System
  Parameters.
- Every morning at 07:45 the **stand-up** e-mail lists only what needs attention. The **Production Command Centre**
  and its reports (Downtime by Cause, Estimate vs Actual Cost, Skill Matrix, Bottleneck, LD Exposure, Job-Work
  Reconciliation) are your daily tools.
- You keep the operators, their skills (with validity), their eligible shifts and their link to the Employee; the
  **Skill Matrix** shows where one absence would stop a machine group.
- You approve merging look-alike downtime categories (Downtime Category Review) and confirm every Production
  setting with PEPL management (report Production Settings).

## Stores

- Rejected pieces arrive as **Scrap Weighments** (source Rejection) posted into Scrap Yard. When an item has no
  weight per unit or scrap item, or a scrap item has no rate, you get a ToDo (**PRD-REJECT-SCRAP**): weigh the pieces
  and enter the weighment yourself, then fill in the missing master data.
- Job work: material at job workers is followed by store; overdue material comes as a ToDo (**PRD-JW-OVERDUE**).
- Customer-supplied material is issued automatically when the order is delivered; a failure comes as a ToDo.

## Accounts and management (CEO)

- **Estimate vs Actual Cost**: what each Job Order really cost a piece against the CST, red above the variance
  warning. **LD Exposure**: LD running on open orders and what the next days will add if nothing more is
  delivered. Both read only; nothing is posted to the books.
- Machine-hour rates, overhead %, LD defaults and the variance warning are in PEPL System Parameters; changing them
  after sign-off is a change request.

## System Manager

- One **kiosk login** per tablet (Role Profile PEPL Kiosk); it opens the kiosk by itself.
- PEPL System Health: the Production jobs must show OK; download the **Cycle 3a health check** monthly and give
  each finding an owner.
