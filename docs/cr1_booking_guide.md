# Booking older Sales Orders and Sales Invoices (CR1, pepl_os 0.61.0)

For PEPL's Sales and Accounts users. Book first on the demo site; the live site follows when the demo is accepted.
Your consultant has already prepared the site: earlier Fiscal Years, the historic-booking date (01-04-2026), the
GST ledgers with the same names as in Tally, and Allow Negative Stock switched on while you book.

## Before you start (once)

1. **Customers:** each customer has its GSTIN and its billing address with the right **State** and PIN code. The state
   decides the tax: West Bengal → CGST + SGST; any other state → IGST.
2. **Items:** each item has its **HSN/SAC code** and, if the old rate differs from today's, its tax rows
   (Item → Tax → Item Tax Template, with **Valid From**). Example: an item that was 12% until 21-09-2025 and is 5% from
   22-09-2025 has two rows: "GST 12%" valid from the old date, "GST 5%" valid from 22-09-2025.
3. **Items sold from stock that ERPNext has never received:** enter the **Valuation Rate** on the item (Item →
   Inventory → Valuation Rate = cost per unit as in Tally). Without it the invoice is refused and the item is named.

## A. Sales Order with its real date

1. Selling → Sales Order → New.
2. Customer, **Date = the order's real date** (e.g. 15-06-2023), Delivery Date, Sector, the items and rates.
3. Check the **Taxes** table: CGST + SGST (West Bengal) or IGST (other states), with the Tally ledger names.
4. Save, Submit. The order shows **Historic Booking** ticked. No Material Request or Job Order is made for it.
5. If part of an old order is still to be made: on the order, **Create → Work Order** for that quantity.

## B. Sales Invoice already raised in Tally

1. Open the Sales Order → **Create → Sales Invoice**.
2. Tick **Edit Posting Date and Time** and enter the **real invoice date**.
3. Enter the **Tally Invoice No.** (each number can be used once).
4. Keep only the lines and quantities on that Tally invoice.
5. Tick **Update Stock** so the stock goes out (it may show negative – that is expected for now).
6. Check the taxes match the Tally invoice. Save, Submit.
7. One invoice may cover one Sales Order only (PEPL's Payment Tracker rule).
8. If Tally shows the invoice as paid, record the receipt: Payment Entry against the invoice, with the Tally voucher
   number and date. Otherwise the invoice stays outstanding in ERPNext.

## C. When all orders and invoices are booked

1. Tell your consultant. Stores enters the stock of the material already sold (Stock Entry → Material Receipt, or the
   opening stock), which brings the negative balances back to zero.
2. Your consultant then switches **Allow Negative Stock** off again.

GST returns continue to be filed from Tally. These invoices appear in ERPNext's GST reports too, but are not
re-filed from ERPNext.

| Step | What to check | Pass / Fail |
| --- | --- | --- |
| A | An order dated 2023 saves and submits; Historic Booking ticked; taxes correct | |
| B | The invoice with its real date and Tally number submits; taxes match Tally | |
| C | After the stock entry, the items' stock is no longer negative | |
