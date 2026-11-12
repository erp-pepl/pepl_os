# PEPL OS v0.61.0 - Check 61: CR1 - older Sales Orders and Sales Invoices with their real dates, negative stock,
# GST ledgers as in Tally, CGST + SGST / IGST on the order and the invoice.
# Runs on 0.61.0 or later. System Console, Type = Python. Leave "Commit" UNTICKED: everything below (Fiscal Years,
# Tally ledgers, addresses, orders, invoices, settings) is undone at the end. The real set-up is a separate script.
VERSION = "0.61.0"
PARAMS = "PEPL System Parameters"
HISTORIC = "pepl_os.pepl_accounts.historic"
TALLY = "pepl_os.pepl_accounts.tally_gst"
CUTOFF = "2026-04-01"
OLD_ORDER_DATE = "2023-06-15"
OLD_INVOICE_DATE = "2023-07-10"
passed = []
failed = []


def check(ok, label):
    if ok:
        passed.append(label)
        print("PASS  " + label)
    else:
        failed.append(label)
        print("FAIL  " + label)


def refused(label, action, words):
    try:
        action()
        check(False, label + " (it was accepted)")
    except Exception as e:
        text = frappe.utils.strip_html(str(e))
        check(words.lower() in text.lower(), label + " -> " + text[:220])


def version_parts(value):
    return [int(part) for part in str(value or "0").split(".")[:3]]


RUN = frappe.utils.now().replace("-", "").replace(":", "").replace(" ", "").replace(".", "")[8:14]
print("INFO  run " + RUN + " (all test names end with it)")
today = frappe.utils.today()
company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name", limit=1)[0]
abbr = frappe.db.get_value("Company", company, "abbr")
print("INFO  company " + company + " (" + abbr + ")")


def wh(store):
    return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": store, "is_group": 0}, "name")


def acc(name):
    return name + " - " + abbr


def set_params(values):
    doc = frappe.get_doc(PARAMS)
    for field in values:
        doc.set(field, values[field])
    doc.save()


def stock(item_code, store):
    return frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": wh(store)}, "actual_qty") or 0


# ---------------- 1. installed ----------------
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
check(version_parts(apps.get("pepl_os")) >= version_parts(VERSION), "1. pepl_os is " + VERSION + " or later (site has " + str(apps.get("pepl_os")) + ")")
check(bool(frappe.get_meta(PARAMS).get_field("custom_historic_booking_before")), "1. System Parameters > Accounts & GST > Historic Booking: Documents Dated Before")
check(bool(frappe.get_meta("Sales Order").get_field("custom_historic_booking")), "1. Sales Order has 'Historic Booking'")
simeta = frappe.get_meta("Sales Invoice")
check(bool(simeta.get_field("custom_tally_invoice_no")) and bool(simeta.get_field("custom_historic_booking")), "1. Sales Invoice has 'Tally Invoice No.' and 'Historic Booking'")
has_ic = "india_compliance" in apps
print("INFO  India Compliance " + ("installed " + str(apps.get("india_compliance")) if has_ic else "not installed (GST sections skipped)"))

set_params({"custom_historic_booking_before": CUTOFF, "enable_operational_todos": 1, "custom_production_notification_owner": frappe.session.user,
            "custom_job_order_from_sales_order": 1, "custom_ld_default_sectors": "Railways\nDefence"})
check(str(frappe.db.get_single_value(PARAMS, "custom_historic_booking_before")) == CUTOFF, "1. for this run: Historic Booking: Documents Dated Before = " + CUTOFF)

# ---------------- 2. Fiscal Years: dates before 01-04-2026 ----------------
covered = frappe.get_all("Fiscal Year", filters={"year_start_date": ["<=", OLD_ORDER_DATE], "year_end_date": [">=", OLD_ORDER_DATE]}, pluck="name")
if covered:
    print("INFO  " + OLD_ORDER_DATE + " is already in Fiscal Year " + covered[0])
else:
    probe = frappe.new_doc("Sales Order")
    probe.update({"customer": frappe.get_all("Customer", pluck="name", limit=1)[0], "company": company, "transaction_date": OLD_ORDER_DATE,
                  "delivery_date": OLD_ORDER_DATE, "custom_sector": "Private"})
    probe.append("items", {"item_code": frappe.get_all("Item", filters={"is_sales_item": 1, "disabled": 0}, pluck="name", limit=1)[0],
                           "qty": 1, "rate": 1, "delivery_date": OLD_ORDER_DATE})
    refused("2. before the set-up an order dated " + OLD_ORDER_DATE + " is refused", lambda: probe.insert(), "Fiscal Year")
result = frappe.call(HISTORIC + ".create_fiscal_years", from_date="2022-01-01")
print("INFO  Fiscal Years created: " + (", ".join(result.get("created")) or "none (already there)"))
years = frappe.get_all("Fiscal Year", fields=["name", "year_start_date"], order_by="year_start_date asc")
check(str(years[0].year_start_date) <= "2021-04-01", "2. Fiscal Years now start " + str(years[0].year_start_date) + " (" + years[0].name + ") - 1 April 2021 covers January 2022")
check(frappe.call(HISTORIC + ".create_fiscal_years", from_date="2022-01-01").get("created") == [], "2. running it again creates nothing")

# ---------------- 3. GST ledgers as in Tally ----------------
setup = frappe.call(TALLY + ".setup_tally_gst_ledgers", company=company)
print("INFO  groups created " + str(len(setup.get("groups_created"))) + ", renamed " + str(len(setup.get("renamed")))
      + ", moved " + str(len(setup.get("moved"))) + ", created " + str(len(setup.get("created"))))
for line in setup.get("renamed"):
    print("INFO    renamed " + line)
tree = {
    "Output - GST": ["CGST", "IGST", "SGST"],
    "Intermediate ITC": ["Intermediate ITC - IGST", "Intermediate ITC - WB CGST", "Intermediate ITC - WB SGST"],
    "Intermediate ITC - RCM": ["Intermediate ITC - CGST RCM", "Intermediate ITC - IGST RCM", "Intermediate ITC - SGST RCM"],
    "Payable Under RCM": ["Payable Under RCM - CGST", "Payable Under RCM - IGST", "Payable Under RCM -SGST"],
    "Cash Credit Ledgers": ["CGST Cash Credit", "IGST Cash Crdit", "SGST Cash Credit"],
    "Electronic Credit Ledgers": ["CGST - Electronic Credit Ledger", "IGST - Electronic Credit Ledger", "SGST - Electrinic Credit Ledger"],
    "Ineligible ITC-GST": ["Ineligible - IGST", "Ineligible ITC- WB CGST", "Ineligible ITC- WB SGST"],
    "Receivable ITC": ["Receivable ITC - IGST", "Receivable ITC -WB CGST", "Receivable ITC - WB SGST"],
    "TDS From GST": ["TDS on GST - CGST", "TDS on GST - SGST", "TDS on IGST"],
}
duties = frappe.db.get_value("Account", {"company": company, "account_name": "Duties and Taxes", "is_group": 1}, "name")
wrong = []
count = 0
for group in tree:
    for ledger in tree[group]:
        count = count + 1
        if frappe.db.get_value("Account", acc(ledger), "parent_account") != acc(group):
            wrong.append(ledger)
check(not wrong, "3. all " + str(count) + " Tally ledgers are under their Tally groups" + (": wrong " + ", ".join(wrong) if wrong else ""))
tops = ["Cash Credit Ledgers", "Electronic Credit Ledgers", "Ineligible ITC-GST", "Input GST", "Output - GST", "Payable Under RCM", "Receivable ITC", "TDS From GST"]
check(all([frappe.db.get_value("Account", acc(g), "parent_account") == duties for g in tops]) and frappe.db.get_value("Account", acc("Intermediate ITC"), "parent_account") == acc("Input GST"),
      "3. the 8 Tally groups are under " + str(duties) + ", Intermediate ITC (and - RCM) inside Input GST")
check(not frappe.db.exists("Account", acc("Output Tax CGST")) and not frappe.db.exists("Account", acc("Input Tax CGST")),
      "3. India Compliance's Output Tax / Input Tax accounts became the Tally ledgers (no duplicates left)")
again = frappe.call(TALLY + ".setup_tally_gst_ledgers", company=company)
check(not (again.get("groups_created") or again.get("renamed") or again.get("moved") or again.get("created")), "3. running it again changes nothing")
if has_ic:
    rows = [r for r in frappe.get_doc("GST Settings").gst_accounts if r.company == company]
    for r in rows:
        print("INFO    GST Settings " + str(r.account_type) + ": " + str(r.cgst_account) + " | " + str(r.sgst_account) + " | " + str(r.igst_account))
    out = [r for r in rows if r.account_type == "Output"]
    check(bool(out) and out[0].cgst_account == acc("CGST") and out[0].sgst_account == acc("SGST") and out[0].igst_account == acc("IGST"),
          "3. GST Settings > Output = CGST / SGST / IGST (Tally names)")
    inp = [r for r in rows if r.account_type == "Input"]
    check(bool(inp) and inp[0].cgst_account == acc("Intermediate ITC - WB CGST"), "3. GST Settings > Input = Intermediate ITC - WB CGST / WB SGST / IGST")
    instate = frappe.get_all("Sales Taxes and Charges Template", filters={"company": company, "tax_category": "In-State", "disabled": 0}, pluck="name")
    trows = frappe.get_doc("Sales Taxes and Charges Template", instate[0]).taxes if instate else []
    check(sorted([r.account_head + " " + r.description for r in trows]) == sorted([acc("CGST") + " CGST", acc("SGST") + " SGST"]),
          "3. template " + (instate[0] if instate else "In-State (missing)") + " = " + "; ".join([r.account_head + " (" + r.description + ") " + str(r.rate) + "%" for r in trows]))

# ---------------- 4. masters for this run ----------------
hsn = ""
if frappe.db.exists("DocType", "GST HSN Code"):
    codes = [c for c in frappe.get_all("GST HSN Code", filters={"name": ["like", "8483%"]}, pluck="name", limit=20) if len(c) == 8]
    codes = codes or [c for c in frappe.get_all("GST HSN Code", pluck="name", limit=200) if len(c) == 8]
    hsn = codes[0] if codes else ""
print("INFO  HSN code for the test items: " + (hsn or "(none)"))


def item(code, group, rate=0):
    values = {"doctype": "Item", "item_code": code + "-" + RUN, "item_name": code + " " + RUN, "item_group": group, "stock_uom": "Nos",
              "is_stock_item": 1, "is_sales_item": 1 if hsn else 0}
    if hsn:
        values["gst_hsn_code"] = hsn
    if rate:
        values["valuation_rate"] = rate
    return frappe.get_doc(values).insert().name


SHAFT = item("CHK61-FG-SHAFT", "Finished Goods", 300)  # made in house, no BOM: a new order gives Production a PRD-NO-BOM ToDo
BEARING = item("CHK61-BO-BEARING", "Bought-Out Components")  # no stock, no rate: a new order drafts a Material Request
groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)


def customer(name, gstin):
    values = {"doctype": "Customer", "customer_name": name + " " + RUN, "customer_type": "Company",
              "customer_group": groups[0] if groups else None, "territory": territories[0] if territories else None}
    if has_ic:
        values["gst_category"] = "Registered Regular"
        values["gstin"] = gstin
    return frappe.get_doc(values).insert().name


def address(title, line, city, state, pincode, gstin, link_doctype, link_name, own):
    values = {"doctype": "Address", "address_title": title + " " + RUN, "address_type": "Billing", "address_line1": line, "city": city,
              "state": state, "pincode": pincode, "country": "India", "is_primary_address": 1,
              "links": [{"link_doctype": link_doctype, "link_name": link_name}]}
    if own:
        values["is_your_company_address"] = 1
    if has_ic:
        values["gstin"] = gstin
        values["gst_category"] = "Registered Regular"
    return frappe.get_doc(values).insert().name


# Test GSTINs (valid format and check digit, not real registrations): 19 = West Bengal, 27 = Maharashtra.
WB_CUSTOMER = customer("CHK61 Kolkata Customer", "19AABCT1111L1ZI")
MH_CUSTOMER = customer("CHK61 Pune Customer", "27AABCT2222M1ZD")
OWN_ADDRESS = address("CHK61 PEPL Works", "2 Tarpanghat Road", "Kolkata", "West Bengal", "700053", "19AAACP9999K1ZD", "Company", company, True)
WB_ADDRESS = address("CHK61 Kolkata", "1 Test Street", "Kolkata", "West Bengal", "700001", "19AABCT1111L1ZI", "Customer", WB_CUSTOMER, False)
MH_ADDRESS = address("CHK61 Pune", "1 Test Road", "Pune", "Maharashtra", "411001", "27AABCT2222M1ZD", "Customer", MH_CUSTOMER, False)
print("INFO  items " + SHAFT + " (valued 300), " + BEARING + " (no rate); customers " + WB_CUSTOMER + " (West Bengal), " + MH_CUSTOMER + " (Maharashtra)")


def order(cust, cust_address, lines, date, sector="Railways", submit=True):
    details = frappe.call("erpnext.accounts.party.get_party_details", party=cust, party_type="Customer", company=company, doctype="Sales Order",
                          posting_date=date, party_address=cust_address, company_address=OWN_ADDRESS)
    so = frappe.new_doc("Sales Order")
    so.update({"customer": cust, "company": company, "transaction_date": date, "delivery_date": frappe.utils.add_days(date, 30),
               "custom_sector": sector, "customer_address": cust_address, "company_address": OWN_ADDRESS,
               "taxes_and_charges": details.get("taxes_and_charges"), "tax_category": details.get("tax_category")})
    if details.get("place_of_supply"):
        so.place_of_supply = details.get("place_of_supply")
    for line in lines:
        so.append("items", {"item_code": line[0], "qty": line[1], "rate": line[2], "warehouse": wh(line[3]), "delivery_date": frappe.utils.add_days(date, 30)})
    so.set_missing_values()
    so.insert()
    if submit:
        so.submit()
    return so


def taxes_text(doc):
    return "; ".join([r.account_head + " " + str(r.rate) + "% = " + str(r.tax_amount) for r in doc.taxes]) or "no tax rows"


def heads(doc):
    return sorted([[r.account_head, frappe.utils.flt(r.tax_amount, 2)] for r in doc.taxes])


# ---------------- 5. historic orders: real date, GST, nothing drafted ----------------
wb = order(WB_CUSTOMER, WB_ADDRESS, [[SHAFT, 2, 500, "FG Stores"]], OLD_ORDER_DATE)
check(wb.docstatus == 1 and wb.custom_historic_booking == 1, "5. order " + wb.name + " dated " + OLD_ORDER_DATE + " is submitted and ticked Historic Booking")
check(not wb.custom_ld_applicable, "5. a historic Railways order gets no default LD clause")
check(not frappe.get_all("Work Order", filters={"sales_order": wb.name}), "5. no Job Order drafted")
check(not frappe.get_all("ToDo", filters={"reference_name": wb.name, "status": "Open", "description": ["like", "%PRD-NO-BOM%"]}), "5. no PRD-NO-BOM ToDo for Production (the work is long done)")
mh = order(MH_CUSTOMER, MH_ADDRESS, [[BEARING, 1, 1000, "Bought-Out Stores"]], OLD_ORDER_DATE)
check(not frappe.get_all("Material Request Item", filters={"sales_order": mh.name}), "5. order " + mh.name + ": no Material Request drafted for the bought-out line")
if has_ic:
    check(heads(wb) == sorted([[acc("CGST"), 90.0], [acc("SGST"), 90.0]]), "5. West Bengal customer -> CGST 9% + SGST 9% on 1,000: " + taxes_text(wb))
    check(heads(mh) == [[acc("IGST"), 180.0]], "5. Maharashtra customer -> IGST 18% on 1,000: " + taxes_text(mh))
new = order(WB_CUSTOMER, WB_ADDRESS, [[SHAFT, 1, 500, "FG Stores"], [BEARING, 1, 100, "Bought-Out Stores"]], today)
check(new.custom_historic_booking == 0 and new.custom_ld_applicable == 1, "5. control: an order dated today is new (not historic) and gets the Railways LD clause")
check(bool(frappe.get_all("Material Request Item", filters={"sales_order": new.name})), "5. control: the new order drafted its Material Request")
check(bool(frappe.get_all("ToDo", filters={"reference_name": new.name, "status": "Open", "description": ["like", "%PRD-NO-BOM%"]})), "5. control: the new order told Production its shaft has no BOM")

# ---------------- 6. historic invoices ----------------
def invoice(so, date, tally_no, update_stock):
    si = frappe.call("erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice", source_name=so.name)
    si.set_posting_time = 1
    si.posting_date = date
    si.due_date = date
    si.payment_schedule = []
    si.update_stock = update_stock
    si.custom_tally_invoice_no = tally_no
    si.insert()
    return si


# ERPNext refuses an Update Stock invoice for stock never received unless Stock Settings > Allow Negative Stock is on
# (its refusal comes after the invoice is written, so this check does not try it: it would leave a half-submitted
# invoice in the run).
stock_settings = frappe.get_doc("Stock Settings")
stock_settings.allow_negative_stock = 1
stock_settings.save()
check(frappe.db.get_single_value("Stock Settings", "allow_negative_stock") == 1, "6. Stock Settings > Allow Negative Stock on for this run")
si1 = invoice(wb, OLD_INVOICE_DATE, None, 1)
check(si1.custom_historic_booking == 1, "6. invoice " + si1.name + " dated " + OLD_INVOICE_DATE + " is ticked Historic Booking")
refused("6. without its Tally Invoice No. it is refused", lambda: si1.submit(), "Tally Invoice No")
si1 = frappe.get_doc("Sales Invoice", si1.name)
si1.custom_tally_invoice_no = "CHK61/23-24/" + RUN
si1.save()
si1 = frappe.get_doc("Sales Invoice", si1.name)
si1.submit()
check(si1.docstatus == 1, "6. with its Tally Invoice No. the invoice submits, though the shaft was never received")
check(stock(SHAFT, "FG Stores") == -2, "6. FG Stores shows the shaft at " + str(stock(SHAFT, "FG Stores")) + " (negative until PEPL enters the stock)")
if has_ic:
    check(heads(si1) == sorted([[acc("CGST"), 90.0], [acc("SGST"), 90.0]]), "6. the invoice carries the order's GST: " + taxes_text(si1))
    check(si1.get("einvoice_status") == "Not Applicable" and si1.get("e_waybill_status") == "Not Applicable",
          "6. e-Invoice " + str(si1.get("einvoice_status")) + ", e-Waybill " + str(si1.get("e_waybill_status")) + " (none made for an old invoice)")
gl = frappe.get_all("GL Entry", filters={"voucher_no": si1.name, "is_cancelled": 0}, fields=["account", "posting_date", "debit", "credit"])
check(bool(gl) and all([str(g.posting_date) == OLD_INVOICE_DATE for g in gl]), "6. its ledger entries are dated " + OLD_INVOICE_DATE + " (" + str(len(gl)) + " lines)")
check(bool(frappe.db.exists("PEPL Payment Tracker", {"linked_sales_invoice": si1.name})), "6. its Payment Tracker is made (outstanding until the Tally receipt is recorded)")
refused("6. the same Tally Invoice No. on another invoice is refused", lambda: invoice(mh, OLD_INVOICE_DATE, "CHK61/23-24/" + RUN, 0), "already on Sales Invoice")
si2 = invoice(mh, OLD_INVOICE_DATE, "CHK61/23-24/B" + RUN, 1)
refused("6. an item with no stock history and no rate is named in plain words", lambda: si2.submit(), BEARING)
frappe.db.set_value("Item", BEARING, "valuation_rate", 600)
si2 = frappe.get_doc("Sales Invoice", si2.name)
si2.submit()
check(si2.docstatus == 1 and stock(BEARING, "Bought-Out Stores") == -1, "6. after the item's Valuation Rate is entered the invoice submits (stock -1)")
if has_ic:
    check(heads(si2) == [[acc("IGST"), 180.0]], "6. Maharashtra invoice: " + taxes_text(si2))

# ---------------- 7. PEPL enters the stock already sold: negative back to zero ----------------
receipt = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
                          "items": [{"item_code": SHAFT, "qty": 2, "t_warehouse": wh("FG Stores"), "basic_rate": 300},
                                    {"item_code": BEARING, "qty": 1, "t_warehouse": wh("Bought-Out Stores"), "basic_rate": 600}]}).insert()
receipt.submit()
check(stock(SHAFT, "FG Stores") == 0 and stock(BEARING, "Bought-Out Stores") == 0, "7. after the Material Receipt both items are back to 0")

# ---------------- 8. rule off ----------------
set_params({"custom_historic_booking_before": None})
off = order(WB_CUSTOMER, WB_ADDRESS, [[SHAFT, 1, 500, "FG Stores"]], OLD_ORDER_DATE, submit=False)
check(off.custom_historic_booking == 0 and off.custom_ld_applicable == 1, "8. with the date empty an order of " + OLD_ORDER_DATE + " is treated as new (LD default applies)")

print("")
print("RESULT: " + str(len(passed)) + " passed, " + str(len(failed)) + " failed")
print("Commit was left unticked, so nothing above was saved.")
