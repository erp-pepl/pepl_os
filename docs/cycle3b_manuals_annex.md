# Cycle 3b · Annex to the training manuals — what changes for each role

## Stores (receiving)

- A Purchase Receipt line of an item inspected on receipt gets its **QC Inspection** when you save the receipt.
  Quality inspects it; the receipt's Incoming QC panel shows which lines are inspected. Submitting a receipt whose
  inspections are not done asks for a reason (or is refused), as set in the Incoming QC Gate.
- A Delivery Note line of an item inspected before delivery gets its **final inspection** when you save it. The
  delivery goes once the inspection is Accepted, no NCR is open on the item and — for orders inspected by an outside
  agency — the agency's IC covers the quantity (Dispatch QC panel).

## Quality Inspector

- Open the QC Inspection, type each reading and choose the **instrument** you measured with. The panel shows each
  characteristic in tolerance or **OUT** and whether the instrument is calibrated. An overdue instrument cannot be
  used. Submit: Accepted or Rejected; a Rejected inspection raises its NCR by itself.
- Instruments: record every calibration on **New Calibration Record** with the certificate; a Fail takes the
  instrument out of service until a passed calibration.

## Quality Manager

- **NCRs**: from your ToDo list or the Command Centre. Choose the disposition, enter its cost, sign (**Sign off**);
  the panel says who still has to sign. Close when everyone has signed.
- **CAPAs**: raised by a Critical NCR or repeated Major NCRs. Fill containment, the whys, the root cause and the
  actions; set Closed when done. On the check day (ToDo) press **Verify Effectiveness**: Effective closes it, Not
  Effective reopens it.
- **Inspection lots**: for agency orders, record the lot request, the proof inspection, the offer and the IC on the
  lot (Sales Order → Create → Inspection Lot).
- **Quality Command Centre** every morning; **Cost of Quality** monthly; **Quality Settings** when a rule changes.

## Production Manager

- Sign Major NCRs (Manufacturing Manager).
- A Job Order whose drawing changed shows red; check the job and press **Acknowledge Drawing Change**. Shift entries
  on such a job warn until you do.

## CEO

- Sign Critical NCRs (PEPL CEO). The Quality Command Centre shows the open NCRs, overdue checks and the month's Cost
  of Quality.

## Purchase

- The **Quality score** (incoming lots accepted) and the **composite score** of each supplier appear on the RFQ and
  the Quotation Comparison next to the delivery score.
