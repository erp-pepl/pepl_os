# PEPL OS v0.61.0 - CR1 set-up: get a site ready for PEPL's older Sales Orders and Sales Invoices.
# System Console, Type = Python, **Commit TICKED** (this one saves). Safe to run again: what is already there is kept.
# Run it on each site once 0.61.0 is installed there (bench first, then demo; live later).
#  1. Fiscal Years back to FROM_DATE (ERPNext accepts a date only inside a Fiscal Year).
#  2. System Parameters > Accounts & GST > Historic Booking: Documents Dated Before = CUTOFF.
#  3. The GST ledgers named and grouped as in PEPL's Tally (India Compliance accounts renamed, the rest created).
#  4. Stock Settings > Allow Negative Stock = ALLOW_NEGATIVE_STOCK (1 while PEPL books; set 0 again afterwards).
FROM_DATE = "2022-01-01"  # the oldest Sales Order PEPL will book (any day of that year is enough)
CUTOFF = "2026-04-01"  # documents dated before this are historic bookings
ALLOW_NEGATIVE_STOCK = 1
COMPANY = ""  # empty = the site's default company

company = COMPANY or frappe.db.get_single_value("Global Defaults", "default_company")
print("Company: " + str(company))
apps = {a.app_name: a.app_version for a in frappe.get_all("Installed Application", fields=["app_name", "app_version"])}
print("pepl_os " + str(apps.get("pepl_os")) + ", India Compliance " + str(apps.get("india_compliance")))

years = frappe.call("pepl_os.pepl_accounts.historic.create_fiscal_years", from_date=FROM_DATE)
print("1. Fiscal Years created: " + (", ".join(years.get("created")) or "none (already there)"))
for fy in frappe.get_all("Fiscal Year", fields=["name", "year_start_date", "year_end_date"], order_by="year_start_date asc"):
    print("     " + fy.name + "  " + str(fy.year_start_date) + " to " + str(fy.year_end_date))

params = frappe.get_doc("PEPL System Parameters")
params.custom_historic_booking_before = CUTOFF
params.save()
print("2. Historic Booking: Documents Dated Before = " + str(frappe.db.get_single_value("PEPL System Parameters", "custom_historic_booking_before")))

ledgers = frappe.call("pepl_os.pepl_accounts.tally_gst.setup_tally_gst_ledgers", company=company)
print("3. Tally GST ledgers: groups created " + str(len(ledgers.get("groups_created"))) + ", renamed " + str(len(ledgers.get("renamed")))
      + ", moved " + str(len(ledgers.get("moved"))) + ", created " + str(len(ledgers.get("created"))))
for line in ledgers.get("renamed"):
    print("     renamed " + line)
if "india_compliance" in apps:
    for r in frappe.get_doc("GST Settings").gst_accounts:
        if r.company == company:
            print("     GST Settings " + str(r.account_type) + ": " + str(r.cgst_account) + " | " + str(r.sgst_account) + " | " + str(r.igst_account))

stock_settings = frappe.get_doc("Stock Settings")
stock_settings.allow_negative_stock = ALLOW_NEGATIVE_STOCK
stock_settings.save()
print("4. Allow Negative Stock = " + str(frappe.db.get_single_value("Stock Settings", "allow_negative_stock")))
print("Done. Commit was ticked, so this is saved.")
