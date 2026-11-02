# Cycle 3a UAT · The shop-floor kiosk (operators and foreman)

**Who:** the foreman and two operators, with the Production Manager watching. **Where:** a tablet beside a machine,
on the shop-floor Wi-Fi, on the demo site. **How long:** about 45 minutes.
Write **Pass** or **Fail** in the last column. For a Fail, write what you saw.

## Before you start (the Production Manager or the consultant sets this up)

| What | Example |
| --- | --- |
| A kiosk login for the tablet (Role Profile **PEPL Kiosk**) | `tablet-mill01@pepl.example` |
| One machine with a machine group | **MILL-01** (group **MILL**) |
| One shift for today | **General Shift 08:00 – 16:30**, 30 minutes break |
| Two operators with a code, a PIN and a skill on the group | **OP-101** (PIN 1357, level 3), **OP-102** (PIN 2468, level 1) |
| A submitted Job Order with a Job Card on MILL-01 | 40 pieces, 6 minutes a piece |
| A downtime category for no work | **No Plan / No Load** (planned stop) |

## A. Signing in

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| A1 | Log in on the tablet with the kiosk login | the kiosk page opens by itself (no "Not Permitted") | |
| A2 | Open `/kiosk?machine=MILL-01` and bookmark it | machine MILL-01, today and yesterday, the shifts | |
| A3 | Choose today and General Shift; type OP-101 and a wrong PIN | "Employee code or PIN not recognised" | |
| A4 | Type a code that does not exist | the very same message (it never says which part was wrong) | |
| A5 | Type OP-101 with the right PIN | "OP-101 · new entry"; the Job Card is in the list | |

## B. Entering the shift

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| B1 | Production → Add: the Job Card, 08:00 to 12:00, Good 36, Rejected 4, reason **Undersize** → **Save** | "Saved."; the row still shows 08:00 and 12:00 | |
| B2 | Look at the help on the right | "1 gap(s) in the shift…", "Not covered: 12:00 – 16:30", Job Card target 40 – 4 left | |
| B3 | Stops → Add: No Plan / No Load, 12:00 to 16:30 → **Save** | "Every minute of the shift is covered by a row" | |
| B4 | Tool changes → Add: 10:00, "Insert CNMG", reason Worn out, take a photo with the tablet → **Save** | the small photo shows in the row | |
| B5 | **Sign out**, then sign in again as OP-101 | your draft comes back with all its rows | |
| B6 | **Submit** | "This shift is submitted. Thank you."; the fields turn grey | |
| B7 | Try to change a quantity | nothing can be changed; ask the foreman to change it | |

## C. Rules that protect the data

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| C1 | Sign in with a wrong PIN 5 times for OP-102 | "Too many wrong PINs. Try again in 15 minute(s), or ask the foreman." | |
| C2 | (after 15 minutes) OP-102 signs in and enters a block on MILL-01 | the help says OP-102 is below the skill level for MILL (what happens next depends on the Skill Check Mode) | |
| C3 | Leave the kiosk signed in and untouched for longer than the session minutes, then press Save | "Your kiosk session has ended. Sign in again with your code and PIN." | |

## D. The foreman's view

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| D1 | Foreman, on his own login: open `/foreman`, today, General Shift | MILL-01 **Submitted**, OP-101, good 36, rejected 4 | |
| D2 | A machine that ran this week but has no entry today | it shows **Missing** | |
| D3 | Click the entry | it opens in the Desk | |

## E. After the shift (Production Manager, in the Desk)

| # | Do this | You should see | Pass / Fail |
| --- | --- | --- | --- |
| E1 | Open the Shift Production Entry | the Shift panel: planned minutes, every minute explained, good 36 · rejected 4, where the rejected pieces went | |
| E2 | Open the Job Card | a time log 08:00 – 12:00, 36 done | |
| E3 | Open PEPL OEE Daily for MILL-01, today | A, P, Q and OEE for the shift | |
| E4 | Open PEPL Scrap Weighment | the rejected pieces as a weighment, source Rejection (if the item has a weight and a scrap item) — or a ToDo for Stores | |

**Signed off by** (foreman) ______________________ (Production Manager) ______________________ Date ____________
