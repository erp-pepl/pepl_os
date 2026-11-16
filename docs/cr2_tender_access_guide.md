# CR2 – Tender data for three people only: test steps for PEPL

From version 0.62.0, **tenders and Cost Sheets open only for three logins:**
ankit@parasramkagroup.com, sudam@parasramkagroup.com and aviral@parasramkagroup.com.
Nobody else sees them. That includes the CEO login and the System Manager logins.
**Only these three make a Sales Order from a tender** (button on the tender). After that, the Sales Order stays
open to everyone who works on it. Only the **Tender Reference** and
**NIT Number** on those orders are hidden.

Do these tests on the demo site. Write Pass or Fail in the last column.

| # | Who logs in | What to do | What should happen | Pass / Fail |
| --- | --- | --- | --- | --- |
| 1 | Ankit | Open **PEPL Tender** list | All tenders are listed | |
| 2 | Ankit | Open any tender, change a small thing, Save | It saves | |
| 3 | Ankit | Open **PEPL CST Cost Sheet** list | All Cost Sheets are listed | |
| 4 | Sudam | Repeat 1 and 3 | Same as Ankit | |
| 5 | Aviral | Repeat 1 and 3 | Same as Ankit | |
| 6 | A sales user (not one of the three) | Open **PEPL Tender** list | The list is empty (or the screen is not offered) | |
| 7 | The same sales user | Type a tender number (e.g. TND-2026-0003) in the search bar | The tender does not open: "not permitted" | |
| 8 | The CEO login | Repeat 6 and 7 | Same: no tender opens | |
| 9 | A System Manager login (not one of the three) | Repeat 6 and 7, and open **PEPL CST Cost Sheet** list | Nothing opens; both lists empty | |
| 9a | Ankit | Open a won tender and click **Create Sales Order** | The Sales Order is made, with the Tender Reference filled | |
| 9b | A sales user (not one of the three) | Make a new Sales Order and try to put a tender number in it (e.g. through Data Import) | Refused: "Only the Tender Access users can make a Sales Order from a tender" | |
| 10 | A sales user | Open a Sales Order made from a tender (e.g. SAL-ORD-2026-00006) | It opens; **Tender Reference** and **NIT Number** are not shown; everything else is | |
| 11 | Ankit | Open the same Sales Order | Tender Reference and NIT Number are shown | |
| 12 | A production / stores user | Create a Job Order or Delivery Note from that Sales Order | It works as before | |
| 13 | Ankit | On a tender, use **Assign To** and pick a person who is not one of the three | Refused: tender data is only for the three | |
| 14 | Ankit | On a tender, use **Share** with a person who is not one of the three | Refused | |
| 15 | An accounts user | Open report **PEPL Estimate vs Actual Cost** | Actual costs show; the estimate columns are empty with the note "CST estimate shown only to the Tender Access users" | |

## Good to know

- **Adding or removing one of the three** is a change to the site settings. It is made by the ERPNext consultant
  (Frappe Cloud dashboard). System Managers cannot change it from inside ERPNext. That is on purpose.
- A daily tender deadline reminder goes to Ankit when it would otherwise have gone to someone else.
- The Administrator login can still see everything. Keep its password with the directors only.
