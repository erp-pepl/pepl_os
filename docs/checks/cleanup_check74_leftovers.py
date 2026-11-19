# PEPL OS - one-off clean-up (19 Nov 2026): Check 74's test records that stayed on the bench (item CHK74-PIN-113121 and
# its 5 NCRs). System Console, Type = Python, "Commit" TICKED (this one is meant to save). Deletes only what it lists.
ITEM = "CHK74-PIN-113121"
names = frappe.get_all("PEPL NCR", filters={"item": ITEM}, pluck="name")
print("NCRs of " + ITEM + ": " + str(names))
for n in names:
    frappe.delete_doc("PEPL NCR", n, force=1, ignore_permissions=True)
if frappe.db.exists("Item", ITEM):
    frappe.delete_doc("Item", ITEM, force=1, ignore_permissions=True)
left = frappe.get_all("PEPL NCR", filters={"item": ["like", "%CHK7%"]}, pluck="name") + frappe.get_all("Item", filters={"name": ["like", "%CHK7%"]}, pluck="name")
print("Left with CHK7 in the name: " + str(left))
print("Done: tick Commit and Execute once; run again with Commit unticked and it should list nothing.")
