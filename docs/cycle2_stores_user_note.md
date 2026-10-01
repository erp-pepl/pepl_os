# Purchase & Stores: what changes for you (Cycle 2, part 1)

## Items and stores

Every stock item belongs to one stock class, taken from its Item Group:
Raw Material, Bought-Out Components, Consumables, Tools & Gauges, WIP / Semi-Finished,
Finished Goods, Scrap, Customer-Supplied Material, Capital Equipment.

- A new stock item must be in a group under one of these classes. The item then shows its
  **Stock Class** and its default store is filled in for you.
- Customer-supplied material (CSM) has no value in PEPL's books and lives only in the CSM
  stores. The software refuses to put CSM in a PEPL store, or PEPL material in a CSM store.
- Capital equipment (machines, instruments, vehicles) is never stock. Record it in the
  **Capital Equipment Register** instead.

## Suppliers

Each supplier now has a **Vendor Criticality** (Critical / Important / Routine), an
**Is MSME** tick with the Udyam number, and the **RM Groups** it supplies. Approval state and
scores are filled in automatically once supplier approval goes live.

## Capital Equipment Register

One record per machine or instrument, with the purchase invoice, manual and warranty or
guarantee certificate attached. A red line at the top shows what is missing. Stores receives
a ToDo when a warranty or AMC is within the alert days set in PEPL System Parameters.

## Material Requests from Sales Orders

When a Sales Order is submitted, a **draft** Material Request is created for Purchase with
the bought-out lines (full quantity) and any raw material the stores cannot cover
(stock + open orders + open requests). One per Sales Order. Purchase reviews and submits it.
The panel on the Material Request shows stock, orders already placed, other open requests and
how many approved suppliers exist for each line.

## Supplier approval

The list of documents a supplier must give is kept in **PEPL Supplier Document Requirement**
(mandatory or not, expiring or not). Each supplier has one **PEPL Supplier Approval** with
that checklist. Only the Purchase Manager can approve, and only when every mandatory document
is attached and in date. Expired documents make the supplier **Expired** automatically, and
Purchase gets a ToDo 30 days before a document expires. Sending an RFQ or Purchase Order to a
supplier who is not approved needs a typed reason, recorded in the Audit Trail.

## Requests for Quotation by RM group

On a submitted Material Request, press **RFQ by RM Group**. The lines are grouped by the RM
group of each item, and for each group the suppliers approved for it are already ticked, with
their delivery and quality scores. Untick any you do not want, or add another supplier (one
not approved for that group will need a reason when the RFQ is submitted). **Create RFQs**
makes one draft RFQ per group. Open each one, check it and submit it to e-mail the suppliers.
Lines already on an RFQ are not offered again.

## Quotation Comparison

When the Supplier Quotations for an RFQ are submitted, open the RFQ and press **Quotation
Comparison**. Every supplier's rate for every line is shown side by side, with lead time,
promised date, payment terms, the last three PO rates for that item from that supplier
(12 months) and the supplier's delivery and quality scores. The lowest rate of each line is
marked **L1** and gets the whole quantity. Change the **Awarded Qty** to split or move an
order; giving quantity to a supplier who is not L1 needs a reason in that row. Press **Send
for Approval**. The Purchase Manager checks the summary and presses **Submit**: one draft
Purchase Order is created per supplier, each line promised by today + the quoted lead time,
with the comparison PDF attached. An approved comparison cannot be changed.

## Purchase Order approval by value

Set **PO Approval Value (MD above)** and **MD / CEO** in PEPL System Parameters → Purchase &
Stores. A Purchase Order whose grand total is above that value is marked **Needs MD
Approval**; only the MD / CEO can submit it, and the MD gets a ToDo for it (closed
automatically once it is submitted). At or below the value, the Purchase Manager submits it.
The Purchase User prepares and saves Purchase Orders but does not submit them. Every PO line
needs a Required By (promised) date, not earlier than the PO date. With no value set, the
Purchase Manager submits every PO.

## Purchase Tracker

Every submitted Purchase Order gets one **PEPL Purchase Tracker** automatically. Each line
shows ordered, received and pending quantity, the **promised date** (taken once from the PO
line and never changed) and its status: Not Due, Due Soon (within the Delivery Alert Lead
Days), Due Today, **Overdue** (with days overdue, after the Late Delivery Grace Days), Part
Received, Received or Short-Closed (PO closed with quantity still pending). The tracker's
status is its worst line. It is recalculated when the PO is submitted, closed, cancelled or
changed, when goods are received, every morning, and when you press **Refresh now**. Enter
the vendor's revised date and your next follow-up date on the tracker; lateness is always
counted from the promised date.

## Chase list, chase letter and Open PO Ageing

**PEPL Chase List** (report) shows every PO line that is Overdue, Due Today or Due Soon,
grouped by supplier, Critical suppliers first, then by days overdue, with the supplier's
phone and e-mail. Press **Chase** beside a supplier (or **Chase vendor** on a Purchase
Tracker) to e-mail that supplier one letter, on letterhead, listing all its pending lines;
the tracker then shows when it was last chased and how many times. **Preview chase letter**
shows the letter first. Every morning the Purchase owner gets one ToDo per overdue PO; it
closes itself when the PO is no longer overdue. **PEPL Open PO Ageing** (report) shows each
supplier's open PO value by age since the PO date and by days overdue since the promised
date, worked out live.

## Delivery letdowns and the vendor delivery score

Every late or short delivery is logged in **PEPL Delivery Letdown**: a receipt line received
after the promised date (plus the grace days) is logged as **Late** with the days late; a PO
closed with more than the Short Receipt Tolerance still missing is logged as **Short** (or
**Late + Short**). Cancelling the receipt, or re-opening the PO, removes the letdown again.
The Purchase Manager can **Excuse** a letdown with a reason (recorded in the Audit Trail); an
excused letdown does not count against the supplier. Every morning each supplier's
**Delivery Score** is worked out: PO lines received complete by their promised date, as a %
of the lines that fell due in the Vendor Score Period. It is shown on the Supplier, the
Purchase Tracker, the RFQ dialog and the Quotation Comparison.

## Heat numbers at the gate, Receipt Log and Heat Number Trace

New raw-material items are **Heat Number Tracked**. On the Purchase Receipt, type the
**Heat Number** and attach the **Test Certificate (MTC)** on each raw-material line; the
system makes (or reuses) the Batch for that supplier and heat, so later issues simply pick
the Batch. A delivery of several heats on one line: **Split by heat** turns it into one line
per heat (the quantities must add up; rate and PO link are kept). A raw-material receipt
without a heat number or MTC cannot be submitted (Heat Number Gate = Hard Block) or needs a
typed reason (Reason Required) - set in PEPL System Parameters. The panel at the top shows
which lines are complete. Every submitted receipt line is written to the **PEPL Receipt Log**
(never deleted; a cancelled receipt shows Cancelled). **PEPL Heat Number Trace** (report):
type a heat number to see its receipt, every issue, the Work Order and the dispatch.

## Customer-supplied material (CSM) against its Sales Order

Material the customer sends in (CSM items, in the Item Group Customer-Supplied Material) is
received with a **Material Request** of type **Customer Provided** - name the Sales Order on
it - and then **Create > Stock Entry**: a Material Receipt into **CSM Stores** at zero value,
so PEPL's stock value does not change. The heat number rules apply as for raw material: type
the **Heat Number** on each line. Every Stock Entry with a CSM line must name its **Sales
Order (CSM)** - receipts, issues to production, moves to **CSM Scrap** and returns. To give
material back to the customer use the Stock Entry Type **CSM Return to Customer**. Once an
order holds customer material, the Sales Order shows **CSM Scrap** (Hold / Return to
Customer / PEPL May Sell, default Hold) and a **View > CSM Balance** button. **PEPL CSM
Balance by Order** (report) shows, per order and CSM item, what was received, issued,
scrapped, returned, the balance still held and the scrap on hand.

## Vendor payments: priority worklist, Payment Entries from Tally, MSME 45-day

Payments are still made in Tally; ERPNext decides the order and keeps the record. **PEPL
Vendor Payment Priority** (report) lists every submitted Purchase Invoice with money still
owed, in this order: MSME bills by their MSME pay-by date (past it shows **Breach**), then
bills of Critical vendors that are past due (most overdue first), then everything else by
due date. The MSME pay-by date is the bill date (or the receipt date, if "MSME Clock Starts
From" is set to Receipt Date) plus the MSME Payment Days; it is shown on the bill and
refreshed every morning, and Accounts gets a ToDo once 7 days or fewer are left.

Each week the Purchase Manager creates a **PEPL Payment Run**, presses **Build from
worklist**, unticks any bill not to be paid this week (an MSME bill needs a reason, kept in
the Audit Trail) and submits; Accounts gets a ToDo with the list. After paying in Tally,
Accounts presses **Mark paid** on the bill's row in the priority report and types the date,
amount, Tally voucher number, UTR / cheque number and any TDS deducted: a Payment Entry is
submitted against the bill, its outstanding goes down (part payments are fine) and the run
row shows Paid / Part Paid. A Tally voucher number can be recorded only once. Set the
Mode of Payment, Bank Account and TDS Payable Account for vendor payments in PEPL System
Parameters. **PEPL MSME 45-Day Compliance** shows every MSME bill as Paid on time / Paid
late / Open / Breach. **PEPL Outstanding Vendor Bills** shows what is owed per supplier by
days overdue; its total equals ERPNext's Accounts Payable report for the same date.

## Scrap Register by metal

Scrap items sit under **Scrap > Brass / Steel / Copper / Aluminium Scrap** (UOM Kg); the
first set (Brass Turnings, Brass Solid, Steel Turnings, Copper Scrap, Aluminium Scrap) is
created for you, and Stores can add more. Customer-material scrap has its own items under
**CSM Scrap** (e.g. "CSM Brass Turnings"), because it never shares a store with PEPL's.
**PEPL Scrap Rate** holds the rate per kg from a date. On every **PEPL Scrap Weighment**
type the gross and tare kg (net is worked out and must be above zero), the source (Process /
Rejection / CSM) and the item; submit puts the net kg into **Scrap Yard** at the day's
scrap rate - or, for CSM scrap, into **CSM Scrap** at zero against its Sales Order. A
**PEPL Scrap Sale** (buyer from the customer group **Scrap Buyers**, vehicle number,
weighbridge slip, lines of kg and rate) takes the scrap out of stock on submit and prints a
**Gate Pass**. Customer-material scrap can be sold only when its Sales Order's **CSM Scrap**
is **PEPL May Sell** - there is no override. To return it, use a Stock Entry of type **CSM
Return to Customer** and print the **PEPL CSM Return Challan**. **PEPL Scrap Recovery**
(report) shows per month and metal: kg generated and sold, realised rate against the rate
master, value realised, closing kg and value, and scrap as a % of raw material issued.
If scrap is ever invoiced through an ERPNext Sales Invoice, Cycle 1's Payment Tracker hook
must first be told to skip the Scrap Buyers group.

## Reorder levels from actual consumption

For raw material (RM Stores) and consumables (Consumables Stores) the system works out
reorder levels from what was really used: everything issued, consumed in manufacture or
moved into a WIP store over the **Reorder: Usage Period** (store-to-store moves do not
count), divided by those days. The lead time is the median number of days from PO to
receipt for that item (else the Item's Lead Time). **Level = daily use x (lead time +
Reorder: Safety Stock days)**; **order qty = 30 days of use**, rounded up to the Item's
minimum order qty. Items used for under 30 days are marked "insufficient history" and are
not ticked. Each month the Stores HOD gets a draft **PEPL Reorder Review** (or creates one
and presses **Compute suggestions**), ticks Accept, may change the final level / qty, and
submits: the levels go into each Item's standard Reorder table. Every morning an item whose
projected stock is below its level gets a ToDo for Stores; the Item shows the level against
stock and a **Create Material Request** button. ERPNext's own automatic Material Request
(Stock Settings) stays off until the HOD asks for it.

## Cycle count by ABC class

Every month each stock item gets an **ABC Class** from what it consumed over the last 12
months by value: A = the items making up the top "Class A: Share of Value" %, B = the next
"Class B" %, C = the rest. A **PEPL Cycle Count** for a store: press **Generate count
sheet** and only the items that are due appear (never counted, or last counted at least
"Count Class A / B / C Every (Days)" ago), one line per heat batch for heat items. Print
the **Blind Count Sheet** - it shows no quantities, and the counter cannot see the book
qty on screen either. Type each counted qty (tick **Counted** for a qty of zero). Every
line that differs from the book needs a **Reason**. When the difference is above "Count
Variance Needing Approval" % of the book value, only the Stores HOD can submit (they get a
ToDo). On submit one standard Stock Reconciliation corrects only the lines that differed,
and every counted item gets **Last Counted On**. **PEPL Cycle Count Variance Log** shows
the differences by store, reason and month.

Note: when an Item has a reorder level, ERPNext shows "You have to enable auto re-order in
Stock Settings". PEPL keeps that setting off on purpose (Stores gets PEPL's own low-stock
ToDo instead), so the message can be ignored.
