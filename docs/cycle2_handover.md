# Cycle 2 · Purchase & Stores — handover

App `pepl_os`, modules **PEPL Purchase** and **PEPL Stores**. Works on ERPNext v16 next to
`pepl_sales` (which owns PEPL System Parameters, PEPL RM Group and the letterhead file).
The user-facing guide is `docs/cycle2_stores_user_note.md`; the feature map is in `README.md`.

## How the chain runs

1. **Sales Order submitted** → one draft Material Request (bought-out lines and raw-material shortfall).
2. **Material Request** → **RFQ by RM Group** (approved suppliers ticked) → RFQ submitted.
3. Supplier Quotations → **Quotation Comparison** (L1 per line; non-L1 award needs a reason)
   → approval creates one draft **Purchase Order** per supplier, comparison attached.
4. PO above the **PO Approval Value** waits for the MD / CEO; every line needs a promised date.
5. PO submitted → **Purchase Tracker** (per line: promised, received, pending, days to due / overdue),
   recomputed every morning → **Chase List**, chase letter, PUR-CHASE ToDos.
6. **Purchase Receipt**: heat number + test certificate gate, Split by heat, Batch = heat →
   **Receipt Log** row per line; late or short receipts → **Delivery Letdown** → supplier delivery score.
7. **Purchase Invoice**: MSME pay-by date → **Vendor Payment Priority** (MSME → critical overdue → ageing)
   → weekly **Payment Run** → paid in Tally → **Mark paid** creates the Payment Entry.
8. Stores: **Scrap Weighment / Sale**, **Reorder Review**, **Cycle Count**, **Consumables Issued**,
   CSM balance per Sales Order, Capital Equipment Register.

## Scheduled jobs (all recorded in PEPL Job Run; status on PEPL System Health)

| Job | When | Does |
| --- | --- | --- |
| `pepl_stores.capital_equipment.daily_equipment_alerts` | daily | warranty / AMC ToDos (STO-CAP-EXPIRY) |
| `pepl_purchase.supplier_approval.daily_supplier_approvals` | daily | document expiry, approval state, SUP-DOC-EXPIRY ToDos |
| `pepl_purchase.tracker.refresh_open_purchase_trackers` | daily | recomputes every open tracker; PUR-CHASE ToDos |
| `pepl_purchase.letdown.daily_delivery_scores` | daily | supplier delivery score |
| `pepl_purchase.payments.daily_msme_payments` | daily | MSME days left; PUR-MSME-DUE ToDos |
| `pepl_stores.reorder.daily_reorder_alerts` | daily | items below reorder level (STO-REORDER) |
| `pepl_stores.reorder.monthly_reorder_review` | monthly | draft Reorder Review for the Stores HOD |
| `pepl_stores.cycle_count.monthly_classify_abc` | monthly | A / B / C class by 12-month consumption value |

## Rule codes (ToDos and the override Audit Trail)

| Code | Meaning |
| --- | --- |
| SUP-NOT-APPROVED | RFQ / PO to a supplier not approved for the group (reason needed) |
| SUP-DOC-EXPIRY | supplier approval document expiring or expired |
| PUR-NON-L1-AWARD | comparison awarded to a supplier that is not L1 (reason needed) |
| PUR-PO-MD-APPROVAL | PO waiting for the MD |
| PUR-CHASE | delivery due soon or overdue |
| PUR-LETDOWN-EXCUSE | letdown excused (reason needed) |
| PUR-MSME-DUE / PUR-MSME-SKIP | MSME bill due within 7 days / MSME bill left out of a payment run (reason needed) |
| PUR-PAY-RUN | approved bills in a payment run still to pay |
| PUR-MR-DRAFT-FAILED | the SO's draft Material Request could not be made |
| STO-HEAT-MISSING | receipt without heat number / test certificate (when the gate is Reason Required) |
| STO-REORDER / STO-REORDER-REVIEW | item below reorder level / reorder review waiting |
| STO-COUNT-APPROVAL | stock count variance above the limit, waiting for the Stores HOD |
| STO-CAP-EXPIRY | machine warranty / AMC expiring |

## Settings PEPL owns

All in **PEPL System Parameters → Purchase & Stores**: PO approval value, MSME days and clock basis,
delivery alert lead days, late grace days, receipt short tolerance, score look-back, document expiry
alert days, heat number gate, reorder look-back and safety days, ABC %, count frequencies, count
variance approval %, machine-hour rates, overhead %, vendor payment bank / mode / TDS ledger, and the
ToDo owners (purchase, accounts, MD approver). Changing a value after sign-off is a change request.

## Checks

- Automated tests: `bench --site <test site> run-tests --app pepl_os` (one file per deliverable,
  `tests/test_c2*.py`). Acceptance = all green.
- System Console checks 6 – 22 (one per deliverable; Check 22 runs the whole chain end to end).
- **Cycle 2 health check** (PEPL System Health): live data against the automation; zero findings
  expected after go-live data repair.

## Known limits (by decision)

- Payments execute in Tally; ERPNext prioritises and records them.
- Estimated-vs-actual costing and SPR rejections → scrap are Cycle 3a.
- Quality score on suppliers arrives with Cycle 3b.
