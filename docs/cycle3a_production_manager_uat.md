# Cycle 3a UAT · Production Manager

**Who:** the Production Manager (HOD), with the consultant. **Where:** the demo site, Desk. **How long:** about
2 hours. Write **Pass** or **Fail** in the last column. For a Fail, write what you saw.
Use one Railways customer order for 40 shafts (a finished item with a BOM, one operation on MILL-01, a weight per
unit and a scrap item when rejected, and an Approved CST). The kiosk UAT should be done first on the same order.

## A. From the order to the Job Order

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| A1 | Submit the Sales Order (Railways, due 2 days ago for the test) | the LD section filled: 0.5 % per week, cap 10 % | |
| A2 | Open Job Orders (Work Order list) | one **draft** Job Order for 40 shafts, "Drafted from Sales Order", due on the line's date | |
| A3 | A line whose item has no BOM | a ToDo **PRD-NO-BOM** for Production | |
| A4 | Submit the Job Order | its Job Card on MILL-01; the panel shows "Made 0 of 40", the routing and "LD so far" | |

## B. Planning

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| B1 | A Production Plan for this week | the machine load: hours booked against MILL-01's hours, orange near full, red above 100 % | |
| B2 | Book MILL-01 for two jobs at the same time | the double-booking message (Advisory / Soft Block with a reason / Hard Block as set) | |

## C. Results of the shift (after the kiosk UAT)

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| C1 | Production Command Centre | the cards: Yesterday's OEE, Jobs at Delivery Risk, Job Work Outside, Rejection % (7 days), Top Downtime Cause | |
| C2 | PEPL Machine Week for MILL-01 | run minutes, breakdowns, MTBF / MTTR, machine cost and CPC | |
| C3 | Report **Downtime by Cause** | the stops by category, biggest first | |
| C4 | Report **Estimate vs Actual Cost**, Job Order = this one | estimate a piece from the CST, actual a piece (material, machining, job work & other, overhead), variance %, red above the warning % | |
| C5 | Same report, Show = Item | the item's Job Orders added together | |
| C6 | Job Order → View → **Cost vs Estimate** | the report opens for this Job Order | |

## D. People and skills

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| D1 | Open an operator; link his **Employee** | name and joining date come from the Employee | |
| D2 | Set the Employee to **Left** | the operator becomes **Inactive**; the kiosk no longer accepts him | |
| D3 | Give an operator **Eligible Shifts** = Day only; enter an Evening shift for him | Warn: the Shift panel says he is not set for that shift (Block: refused) | |
| D4 | Report **Skill Matrix** | every operator against every machine group; red expired, orange expiring or below the level; the last row "Qualified operators", red below the minimum; the To Do column | |

## E. Flow, delivery and scrap

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| E1 | Report **Bottleneck** (last 30 days) | per machine group: waits, average and longest wait, work waiting now; the bottleneck marked | |
| E2 | Report **LD Exposure** | the test order: days late, LD so far, LD in 7 days, cap used; red | |
| E3 | Report **Job-Work Reconciliation** | material at each job worker: sent, received, returned, days, Overdue / GST limit | |
| E4 | PEPL Scrap Weighment list, filter Shift Production Entry | the rejected shafts of the kiosk entry, source Rejection | |

## F. The morning stand-up and the health check

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| F1 | PEPL Daily Standup → build for yesterday | only what needs attention: machines below target, long unplanned stops, missing entries, delivery risk, LD running, work waiting, job work overdue, rejections to weigh — or "All clear" | |
| F2 | The stand-up e-mail (Standup Email Group) | subject "… n exception(s)" or "… all clear" | |
| F3 | System Manager: PEPL System Health → **Download Cycle 3a health check** | an Excel file with 8 sheets; each row is something to fix | |
| F4 | Report **Production Settings** | every Production setting with its value and default; PEPL confirms each one | |

**Signed off by** (Production Manager) ______________________ (PEPL management) ______________________
Date ____________
