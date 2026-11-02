# Cycle 3a · What PEPL fills in before going live

Everything works with defaults on the demo site. For live use PEPL gives these values; the **Cycle 3a health check**
(PEPL System Health) lists what is still missing, and the report **Production Settings** lists every setting still at
its default.

| # | Input | Where it goes | Who |
| --- | --- | --- | --- |
| 1 | Shifts: names, start, end, break | PEPL Shift | Production Manager |
| 2 | Machines and their machine groups | Workstation (Machine Group = Workstation Type) | Production Manager |
| 3 | Machine-hour rate per machine group; overhead % | System Parameters → Production Costing | Accounts |
| 4 | Operators: code, name, PIN, Employee, default and eligible shifts | PEPL Operator | Production Manager / HR |
| 5 | Skills per operator and machine group, with validity | PEPL Operator → Skills | Production Manager |
| 6 | Skill Check Mode and minimum level; minimum qualified operators per group | System Parameters | Production Manager |
| 7 | Final downtime categories (planned / unplanned / PM, breakdown or not) | PEPL Downtime Category (review report) | Production Manager |
| 8 | OEE target and component targets | System Parameters → OEE | Production Manager |
| 9 | Machine double-booking mode; capacity planning on or off | System Parameters; Manufacturing Settings | Production Manager |
| 10 | LD sectors, default rate, period, cap; LD terms per order where different | System Parameters → LD; Sales Order | Sales / Management |
| 11 | Weight per unit and scrap item when rejected, per manufactured item | Item → Inventory | Production / Stores |
| 12 | Scrap rate per scrap item, kept current | PEPL Scrap Rate | Stores |
| 13 | Approved CST per manufactured item | PEPL CST Cost Sheet | Sales / Costing |
| 14 | Job work return days and GST warning days; job worker stores | System Parameters; Warehouse → Job Worker | Stores |
| 15 | Standup Email Group members; stand-up days ahead and minimum stop minutes | Email Group; System Parameters | Production Manager |
| 16 | Kiosk tablets, shop-floor Wi-Fi; one kiosk login per tablet | PEPL (hardware); User with Role Profile PEPL Kiosk | PEPL IT / System Manager |
| 17 | ToDo owners for Production and Stores | System Parameters → first tab | System Manager |
