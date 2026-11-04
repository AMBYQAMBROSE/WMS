# User Guide (Training Material)

For warehouse operators, warehouse supervisors and system administrators. Everyone reads "General" first, then the section for their own role.

## 1. General

- **Sign in**: open the system URL in a browser and sign in with the account your administrator gave you. The menus you see depend on your permissions; ask the administrator for anything you cannot see.
- **Choosing items/locations/partners**: type a code, name or scan a barcode straight into the dropdown. The system searches the server and lists matches; press Enter to pick the first one. With a lot of data not everything is listed at once, so type a keyword.
- **Document status**: Draft → Posted (stock changes only when a document is posted). Drafts can be cancelled; posted documents cannot be changed, so correct mistakes with an adjustment.
- **Units**: orders use the order unit (e.g. carton); stock and reports always show the base unit (e.g. each).
- **Error messages**: the red message at the top of the page explains the cause (e.g. "insufficient stock", "allocated"). Act on it; if it is unclear, send a screenshot to your key user.

## 2. PDA basics

- **Server URL**: entered at first sign-in (your administrator gives it to you, e.g. `http://192.168.1.10`) and remembered afterwards.
- **Master data**: items, locations and so on are downloaded after sign-in and used to recognize barcodes. The home screen shows when it was last updated; tap "Update master data" when items change.
- **Scanning**: the scanner sends Enter after each scan and the cursor always stays in the scan field, so there is no need to tap the screen.
- **Offline**: keep working when the signal is poor. Records go to the "Submit queue" and are submitted automatically once the signal returns, without duplicates (you can also tap "Sync now" in the queue). The home screen shows how many are pending; **make sure the queue is empty before the end of your shift**.

## 3. Receiving clerk

**Web**: Inbound → Purchase orders → open the order → Receive → enter received quantities (batch/expiry items need batch no. and expiry date) → Create → Post.

**PDA**: Receive → ① scan the PO number → ② scan the receiving location (receiving dock) → ③ scan the item barcode → enter the quantity (for batch items, scan/enter batch no. and expiry date) → OK.

Note: over-receipt is not allowed by default. After a partial receipt the PO shows "Partially received"; receive the rest next time.

## 4. Putaway operator

**PDA**: Put away → ① scan the source location (receiving dock) → ② scan the item barcode (choose a batch if there are several) → enter the quantity → scan the target bin. You can do several lines in a row, then tap "Submit putaway".

**Web**: Inbound → Goods receipts → Create putaway → choose a bin for each line → Post.

## 5. Picker (PDA)

Pick → choose a pick list → go to the bin shown → ① scan the bin → ② scan the item → ③ enter the picked quantity (0 if none).
- **Short pick**: if you find less than requested, confirm the actual quantity. The difference goes back to the order as "unallocated" and can be allocated again once stock is replenished.
- **Skip**: if you cannot find something right away, use "Skip this line, pick later".
- **Finish**: when everything is picked, tap "Finish picking (post)". This needs the pick-posting permission; without it, a supervisor posts the pick list on the web.

## 6. Shipping

Outbound → Sales orders → open the order → Ship → enter carrier, vehicle plate, driver and seal no. → create the shipment → post it once loading is done. The shipment automatically includes every picked but unshipped item for that order in staging.

## 7. Inventory operations

- **Move** (PDA or web): on the PDA it works like putaway: scan source location → item → quantity → target location. You can enter several lines and submit them together. Stock allocated to orders cannot be moved.
- **Stock adjustment** (web): Inventory → Stock adjustments → New; choose a reason and enter positive or negative quantities. Clerks can only create adjustments; **they take effect only after a supervisor posts them**.
- **Cycle count**:
  1. A supervisor starts the count on the web and chooses the locations. Nothing can be received into or shipped from those locations during the count.
  2. Counters use the PDA: Count → choose the count → scan location → scan item → enter the quantity. For a batch that is not on the book, tap "Other batch".
  3. The supervisor reviews the differences, requests a recount if needed, and finally posts.

## 8. Warehouse supervisor

- **Approvals**: supervisors post stock adjustments and cycle counts.
- **Dashboard**: today's receipts and shipments, pending backlog (click a number to open the matching list), bin utilization and expiring stock.
- **Reports**: stock turnover, picker performance, expiring stock and partner ledger. After choosing dates, use "Export CSV" to open the data in Excel. With large data sets the page shows only the first 1000 rows; export for the full data.
- **Shortages**: Outbound → Shortages. "Available warehouse-wide" greater than 0 means re-allocating after replenishment will cover the order.

## 9. System administrator

| Task | Where | Notes |
|---|---|---|
| Users, roles | System → Users / Roles | Permission changes take effect immediately; do not give "post" permissions to regular operators |
| Feature flags | System → Feature flags | Enable returns, cross-docking, repacking, returnable assets and over-receipt as needed |
| Reason codes | Master data → Reason codes | Adjustment reasons, return reasons |
| Data import | System → Data import | Download template → fill in → validate → confirm import; nothing is imported unless every row is valid |
| Integrations | System → Integrations | Configure pushes to ERP and other external systems; check failures and resend in the push log (see integration.md) |
| Backup, upgrade | On the server | See deployment.md |

## 10. FAQ

| Problem | What to do |
|---|---|
| An item is not in the dropdown | Type a more complete code or name. If it still does not show, the item may be inactive or not imported |
| "Insufficient stock" | In stock enquiry, check the location's "available" (on hand − allocated); stock allocated to orders cannot be touched |
| "Location is being counted" | Receiving and shipping resume after the count is posted or cancelled |
| The PDA does not react to scans | Make sure the cursor is in the scan field; tap "Update master data" on the home screen and retry; new items must be created in the system first |
| The PDA submit queue never empties | Check the network; open the queue to see why records failed (e.g. insufficient stock), fix the cause, then retry or delete the record |
| Document numbers have gaps | Normal: when a number is taken but saving fails, that number is skipped |
| Dashboard numbers do not match what you just did | The dashboard can lag by up to 30 seconds; refresh shortly |
