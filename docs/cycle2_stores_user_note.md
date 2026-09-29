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
