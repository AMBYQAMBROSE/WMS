# User Guide (Training Material)

For warehouse operators, warehouse supervisors and system administrators. Everyone reads "General" first, then the section for their own role.

## 1. General

- **Sign in**: open the system URL in a browser and sign in with the account your administrator gave you. The menus you see depend on your permissions; ask the administrator for anything you cannot see.
- **Choosing items/locations/partners**: type a code, name or scan a barcode straight into the dropdown. The system searches the server and lists matches; press Enter to pick the first one. With a lot of data not everything is listed at once, so type a keyword.
- **Document status**: Draft → Posted (stock changes only when a document is posted). Drafts can be cancelled; posted documents cannot be changed, so correct mistakes with an adjustment.
- **Units**: orders use the order unit (e.g. carton); stock and reports always show the base unit (e.g. each).
- **Error messages**: the red message at the top of the page explains the cause (e.g. "insufficient stock", "allocated"). Act on it; if it is unclear, send a screenshot to your key user.
- **Pages update by themselves**: when a colleague or a PDA changes something, the list or dashboard you are looking at refreshes on its own. **Live** at the top right means this is working; **Offline** means it is reconnecting (pages still work, they just refresh when you reload).
- **Document lists**:
  - Filter by status, search by document number, source document, partner or remark, and pick a period (today, last 7 or 30 days, or custom dates).
  - **Views**: save the current filters under a name (e.g. "My drafts this week") and open them again with one click. The star opens a view automatically every time you open that list.
  - **Columns**: hide columns you do not need. Views and columns are personal and follow your account to any PC.
  - **Several documents at once**: tick documents and use the bar that appears (e.g. Post, Confirm, Cancel). Each document is checked exactly as if you did it on its own page; the summary lists any that failed, with the reason, and the rest are still done. Documents in the wrong status are skipped.

- **AI assistant** (Dashboard & reports > AI assistant, if your company switched it on): ask in plain language, e.g. "Where is SKU A100 and how much is free?" or "Which orders are short?". It looks the answer up in the WMS, shows which lookups it made, and can only read: to change anything, use the normal screens. Check important figures on the screens it mentions, since answers can be wrong.

## 2. PDA basics

- **Server URL**: entered at first sign-in (your administrator gives it to you, e.g. `http://192.168.1.10`) and remembered afterwards.
- **Master data**: items, locations and so on are downloaded after sign-in and used to recognize barcodes. The home screen shows when it was last updated; tap "Update master data" when items change.
- **Scanning**: the scanner sends Enter after each scan and the cursor always stays in the scan field, so there is no need to tap the screen.
- **Offline**: keep working when the signal is poor. Records go to the "Submit queue" and are submitted automatically once the signal returns, without duplicates (you can also tap "Sync now" in the queue). The home screen shows how many are pending; **make sure the queue is empty before the end of your shift**.
- **Shared PDAs**: records you made offline are only submitted while **you** are signed in, so they are recorded as your work. If you sign out with records still waiting, sign in on that PDA again later to send them. The queue shows other people's waiting records separately.
- **Failed records**: if the server refuses a record (e.g. the location was locked meanwhile), the queue shows what it contained and why. Fix the cause and tap **Retry**; delete it only if you redid the work another way.
- **Each scan counts 1**: for goods labelled per piece, switch this on in Receive or Count and scan every piece instead of typing the quantity.
- **Photos**: in Receive and Count, tap "Take photo" (add a note first if useful) to record damage or what you found. Photos are sent with the record, also when you were offline, and the office sees them on the document.
- **New work**: when new pick lists or counts arrive, the PDA vibrates and the home screen shows them (e.g. "Pick · 2 new") until you open that screen.

## 3. Receiving clerk

**Web**: Inbound → Purchase orders → open the order → Receive → enter received quantities (batch/expiry items need batch no. and expiry date) → Create → Post.

**PDA**: Receive → ① scan the PO number → ② scan the receiving location (receiving dock) → ③ scan the item barcode → enter the quantity (for batch items, scan/enter batch no. and expiry date) → OK.

Note: over-receipt is not allowed by default. After a partial receipt the PO shows "Partially received"; receive the rest next time.

## 4. Putaway operator

Posting a receipt into a dock creates a **putaway sheet** (status "To put away") at once. The success message offers to print it along with the receipt. The printed sheet has the sheet number as a barcode, and each line has the item barcode and the suggested bin as a barcode. The suggested bin is the bin that already holds most of that item; "Any bin" means the item is not in any bin yet.

**PDA (by sheet)**: Put away → ① scan the sheet number (or choose it from the list) → ② scan an item from the dock, in any order → ③ take it to the suggested bin, or any other bin, and scan that bin → ④ confirm the quantity. If the bin is full, enter what fits: the rest stays on the sheet and the PDA asks for the next bin. When everything is put away, tap "Finish putaway (post)". The stock moves into the bins only then, and the sheet cannot be posted while anything is left. This also works offline: puts are queued and sent without duplicates.

**PDA (without a sheet)**: Put away → "Put away without a sheet" → scan the dock → scan the item → quantity → scan the target bin; several lines, then "Submit putaway".

**Web**: open the sheet from the receipt (button "Putaway sheet …") or under Inbound → Putaways (filter "To put away"). The progress bar shows how much is still on the dock. "Put away…" on a line does the same as the PDA. A supervisor can cancel a sheet and do a free putaway instead.

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
- **Printing documents**: every document (purchase order, receipt, putaway, pick list, delivery order, adjustment, count sheet, returns, repack) has a **Print** button next to its number. It opens an A4 PDF with the document's details, lines, totals and signature boxes; the document number is printed as a barcode on every page. After posting, the success message offers "Print <document no.>" directly. Each print is recorded in the document's History.
  - Delivery order: customer, address, vehicle, driver and seal number, with signature boxes for the warehouse, the driver and the customer.
  - Pick list: sorted by bin so the picker walks the warehouse once; the "Picked" column stays empty until confirmed, to write on.
  - Count sheet: shows book quantities only to users allowed to see them (blind count otherwise).
  - Cancelled documents print with a "CANCELLED" watermark; draft orders and delivery orders with "DRAFT".
- **Labels**: every item and every bin should carry a barcode label, so operators scan instead of typing.
  - Item labels: Master data → Items → tick the items (the ticks stay while you search again) → "Print labels". The barcode is the item's barcode, or its SKU when it has none; the PDA reads both.
  - Location labels: Master data → Locations → "Print labels" → "Selected locations", or "Every bin and dock in an area" to label a whole zone, aisle or rack at once (printed in code order).
  - The label opens as a PDF in a new tab. Print it with scaling set to **"Actual size"**, not "Fit to page", or the labels will not line up with the label sheet.
  - On a partly used label sheet, enter how many positions are already used under "Skip label positions".

## 9. System administrator

| Task | Where | Notes |
|---|---|---|
| Users, roles | System → Users / Roles | Permission changes take effect immediately; do not give "post" permissions to regular operators |
| Feature flags | System → Feature flags | Enable returns, cross-docking, repacking, returnable assets and over-receipt as needed |
| Label layouts | System → Labels & printing | Set the label size and layout for item and location labels: a sheet of labels on an A4 office printer, or a roll on a thermal label printer. Start from common label stock, then "Test print": it outlines every label, so hold the print against a label sheet and adjust margins and gaps until they match. The default layout is used when nobody picks one; with none, a built-in A4 layout is used |
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
