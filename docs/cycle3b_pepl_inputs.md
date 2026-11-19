# Cycle 3b · What PEPL fills in before going live

Everything works with defaults on the demo site. For live use PEPL gives these values; the **Cycle 3b health check**
(PEPL System Health) lists what is still missing, and the report **Quality Settings** lists every setting still at its
default and every sign-off role that nobody holds.

| # | Input | Where it goes | Who |
| --- | --- | --- | --- |
| 1 | Stock classes inspected on receipt (e.g. Raw Material, Bought-Out Components) | System Parameters → Quality → Incoming QC: Stock Classes | Quality Manager |
| 2 | Items inspected before delivery | Item → Quality → Inspection Required before Delivery | Quality Manager |
| 3 | Inspection plan per inspected item: characteristics, tolerances, acceptance values | Quality Inspection Template; Item → Quality Inspection Template | Quality Manager |
| 4 | Instrument list: ID, type, range, least count, frequency, location, agency | PEPL Instrument | Quality Manager |
| 5 | Last calibration of each instrument with its certificate | PEPL Calibration Record | Quality Manager |
| 6 | Gate modes: incoming QC, calibration, dispatch (Advisory / Soft Block / Hard Block) | System Parameters → Quality | Quality Manager / Management |
| 7 | Calibration alert days | System Parameters → Quality | Quality Manager |
| 8 | Severity sign-off matrix: the roles that sign Minor, Major, Critical NCRs; who holds each role | System Parameters → Quality; User roles | Management |
| 9 | Severity of system-raised NCRs; NCR on customer return (yes / no) | System Parameters → Quality | Quality Manager |
| 10 | Rejection-rate threshold % and minimum pieces | System Parameters → Quality | Quality / Production Manager |
| 11 | CAPA repeat count and window, whys required, target days, verification after days | System Parameters → Quality | Quality Manager |
| 12 | Vendor score weights (delivery / quality, total 100) | System Parameters → Quality | Purchase / Quality |
| 13 | Quality Notification Owner (gets every Quality ToDo) | System Parameters → first tab | System Manager |
| 14 | Inspection agencies per sector (RITES, RDSO, DGQA / AHQ, consignee) and the tender's Inspection Required | PEPL Tender (pepl_sales); Inspection Lot | Sales / Quality |
| 15 | Product Master drawing revisions with the drawing file and what changed | PEPL Product Master (pepl_sales) | Engineering |
| 16 | Valuation rate of every manufactured item (Cost of Quality) | Item → Valuation Rate / stock | Accounts |
