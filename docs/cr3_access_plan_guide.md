# CR3 – Who gets which access: what changed and how to test it

From version **0.79.0**, PEPL OS follows the answers PEPL gave in the **Access Planning Pack** (24 Nov 2026).
Each person gets one login and one job profile. Some people also get a second profile, or a small add-on for one
named right. Tender data is still open only to ankit@, sudam@ and aviral@parasramkagroup.com (CR2, unchanged).

## What changed

| PEPL decision | What the software now does |
| --- | --- |
| 1 – Who makes new Items | Only people with the add-on **PEPL Item Master**. The Purchase Manager no longer makes Items. |
| 2 – Who adds Suppliers | The **PEPL Purchase Manager** profile, and people with the add-on **PEPL Supplier Master**. |
| 3 – Who corrects stock after a count | New profile **PEPL Stores Manager** (the Stores HOD). Store keepers (PEPL Stores) cannot. |
| 4 – Who cancels | Only the head of the department (Purchase / Stores / Production / Quality / Sales / Accounts Manager) and the System Manager. Accounts staff get the new profile **PEPL Accountant** (books but does not cancel); **PEPL Accounts** is for the Accounts HOD. A **summary of every cancellation** is e-mailed each morning (or each Monday). |
| 5 – MD approval of POs | Set at Rs 1,00,000 in System Parameters → Purchase & Stores → PO Approval Value. The PO total **including GST** is compared. |
| 6 – CEO | Sees everything, changes nothing, approves POs above the Decision 5 value. |
| 7 – BOMs | Only the **PEPL Production Manager** makes or changes BOMs. The Foreman can open them. |
| 8 – Quality and stock | Quality **sees** stock, receipts and deliveries but does not post them. Stores posts them. |
| 9 – Export to Excel | Only the **CEO** (and the System Manager). Blank import templates can still be downloaded. Tender data: only the three tender users. |
| 11 – Sales Invoices | The **PEPL Accounts** profile, and people with the add-on **PEPL Sales Invoicing**. That add-on cannot cancel an invoice. |
| "Need as Exec" | New profile **PEPL Quality Executive**: inspects and raises NCRs, never signs off, closes or cancels. |
| "View only" | New profile **PEPL Production & Quality Viewer**: opens production, quality and stock records, changes nothing. |

The switches are in **PEPL System Parameters → Access**. A right given by hand that breaks a rule is taken away again
at the next update.

## Test steps for PEPL (demo site)

Write Pass or Fail in the last column.

| # | Who logs in | What to do | What should happen | Pass / Fail |
| --- | --- | --- | --- | --- |
| 1 | A store keeper (PEPL Stores) | Open a submitted Purchase Receipt | There is no **Cancel** button | |
| 2 | The Stores HOD (PEPL Stores Manager) | Same receipt | **Cancel** is offered | |
| 3 | The store keeper | New **Stock Reconciliation** | Not allowed | |
| 4 | The Stores HOD | New **Stock Reconciliation** | Allowed | |
| 5 | A Foreman | Open a BOM, try to change a quantity | The BOM opens read-only; **New BOM** is not offered | |
| 6 | The Production Manager | New BOM | Allowed | |
| 7 | A Quality Manager | Open a Purchase Receipt and the Stock Balance report | Both open; there is no **New** or **Submit** on receipts | |
| 8 | A Quality Executive | Open a draft QC Inspection, enter readings, Submit | Submitted | |
| 9 | The Quality Executive | Open a submitted QC Inspection | No **Cancel** button | |
| 10 | The Production & Quality Viewer | Open a Job Order and an NCR | Both open; nothing can be changed | |
| 11 | An accountant (PEPL Accountant) | Any list (e.g. Sales Invoice) → menu → **Export** | Export is not offered | |
| 11a | The accountant | Open a submitted Payment Entry | No **Cancel** button; the Accounts HOD (PEPL Accounts) has it | |
| 12 | The CEO | Same list → **Export** | The Excel file downloads | |
| 13 | Anyone | Data Import → Download Template → **Blank Template** | The template downloads | |
| 14 | The Purchase Manager | New **Item** | Not allowed: ask a PEPL Item Master holder | |
| 15 | A PEPL Item Master holder | New **Item** | Allowed | |
| 16 | A PEPL Sales Invoicing holder | Make and submit a Sales Invoice from a Sales Order | Submitted; no **Cancel** afterwards | |
| 17 | The CEO (next morning) | Look at the e-mail | "PEPL OS cancellations – …" lists yesterday's cancellations (only if something was cancelled) | |
| 18 | Ankit, Sudam, Aviral | Repeat CR2 tests 1–5 | Unchanged: the three see tenders, nobody else does | |

## For the consultant: order of work

1. **Deploy 0.79.0** (bench, CI, demo, then live), as usual. On the first migrate, Export is taken from every role
   except the CEO on every DocType. That takes a minute and leaves a Permission Log row for each change.
2. **Check 79** (System Console, Commit unticked): every line PASS.
3. **Decision 5:** System Parameters → Purchase & Stores → PO Approval Value = 100000.
   MD / CEO = aviral@parasramkagroup.com.
4. **Logins:** `docs/checks/setup_cr3_logins.py` with the signed people list pasted in. Use the consultant's filled
   copy, which is kept outside the repository. Run it with DRY_RUN = 1 until it prints READY, then DRY_RUN = 0 with
   Commit ticked. Then run CR2's `setup_cr2.py` and **Check 62** (the three tender logins now exist).
5. **Passwords:** when PEPL is ready, from the User list select the new logins → Actions → **Send password reset
   instructions** (needs the outgoing e-mail account).
6. **Two-factor login for System Managers (Decision 10):** set up your own authenticator app first. Then:
   System Settings → Login → **Enable Two Factor Auth**, method **OTP App**; Role **System Manager** → tick
   **Two Factor Authentication**. The Administrator login also has the System Manager role, so it needs the code too.
   Keep its authenticator with the directors.
7. **Shared logins (Decision 12):** one week after the named logins are live, disable each shared login PEPL listed
   in "Login used today" (User → Enabled off; never delete, so the Audit Trail keeps the name).
