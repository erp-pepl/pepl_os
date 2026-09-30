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
