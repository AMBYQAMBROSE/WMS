# User Acceptance Test (UAT) Cases

For the customer's key users (who run the tests) and implementation engineers (who prepare data and record results). Run in the **test environment** and record "Pass/Fail" and a problem description for each case. All severe issues (affecting receiving, shipping or stock accuracy) must be closed before go-live.

Preparation: the test environment has the customer's real master data (or part of it) imported, and test accounts exist for each role. Run the PDA cases with the real on-site devices and barcodes.

| ID | Scenario | Steps | Expected result | Result | Notes |
|---|---|---|---|---|---|
| **Sign-in and permissions** |||||
| U-01 | Sign in | Each role signs in to the web console and the PDA | Only menus and buttons the role is permitted to use are visible | | |
| U-02 | Permissions take effect at once | The admin removes one of a user's permissions; the user refreshes the page | The menu/button disappears without signing in again | | |
| U-03 | Deactivate account | The admin deactivates an account | The account can no longer do anything, immediately | | |
| **Master data** |||||
| U-04 | Item search | Type a SKU, part of a name, or a barcode in the item dropdown | All are found; results within 1 second at around 50,000 SKUs | | |
| U-05 | New location | Add a bin under a zone and mark it pickable | The bin appears in the location tree | | |
| U-06 | Data import | Import 10 items from the template with 2 rows deliberately wrong | Validation reports the row numbers and reasons; nothing can be imported until fixed | | |
| **Inbound** |||||
| U-07 | Receive a PO | Create PO → confirm → receive (partial quantity) → post | The PO becomes "Partially received"; stock increases in the receiving dock | | |
| U-08 | Batch/expiry | Receive a batch/expiry item without a batch no. | Submission is refused with a required-field message | | |
| U-09 | Over-receipt control | Receive more than the ordered quantity | Rejected by default; allowed once "Allow over-receipt" is enabled | | |
| U-10 | Putaway | Create a putaway from a goods receipt, choose bins, post | Dock stock decreases, bin stock increases | | |
| U-11 | PDA receiving | On the PDA scan PO no. → scan item barcode → enter quantity → submit | The goods receipt appears on the web | | |
| U-12 | PDA offline | Disconnect the PDA's Wi-Fi, receive/put away, then reconnect | Offline records go to the submit queue and are submitted automatically once online, without duplicates | | |
| **Inventory** |||||
| U-13 | Stock enquiry | Query by item and by location | Quantity, batch, expiry date and allocated are correct | | |
| U-14 | Move | On the PDA scan source location → item → target location | Both locations change correctly | | |
| U-15 | Stock adjustment | A clerk creates an adjustment, a supervisor posts it | The clerk cannot post; after the supervisor posts, stock changes and the ledger shows the reason | | |
| U-16 | Cycle count | Start a count on a few locations, count on the PDA with differences, post | No receiving/shipping on those locations during the count; differences are written to stock on posting | | |
| U-17 | Blind count | Someone without the "view book quantity" permission counts | Book quantities are not shown | | |
| **Outbound** |||||
| U-18 | Order allocation | Create a sales order → confirm → allocate | Allocation is first-expiry-first-out with pickable bins first; a pick list is created | | |
| U-19 | Shortage | Order more than is in stock | What can be allocated is allocated; the rest shows in the shortage report | | |
| U-20 | PDA picking | Choose a pick list on the PDA, pick by guided bin scanning, short-pick one line | The short quantity goes back to "unallocated" and can be allocated again | | |
| U-21 | Shipping | Create a shipment, enter plate and seal no., post | Staging decreases; the order becomes "Shipped" or "Partially shipped" | | |
| U-22 | Allocated stock | Move or adjust down stock that is allocated but not picked | Rejected with an "allocated" message | | |
| **Extension modules (if enabled)** |||||
| U-23 | Customer return | Start a return from a shipped order, one line restocked, one scrapped | The restock line increases stock; cannot exceed the shipped quantity | | |
| U-24 | Return to supplier | Create and post a return to supplier | Stock decreases | | |
| U-25 | Cross-docking | Choose cross-docking and a receiving dock when allocating | Goods are picked directly from the receiving dock | | |
| U-26 | Repack | Consume A, produce B | One posting deducts A and adds B; if A is short, nothing takes effect | | |
| U-27 | Returnable assets | Lend 10 pallets, get 4 back | Outstanding balance is 6 | | |
| **Reports** |||||
| U-28 | Dashboard | Check after the day's receipts and shipments | Matches reality (at most 30 seconds delay) | | |
| U-29 | Stock turnover / partner ledger | Choose one month, spot-check 3 items and 2 partners | Matches a manual sum of the documents; exports open in Excel | | |
| U-30 | Expiring stock | Choose within 30 days | Lists batches and remaining days; expired ones are marked | | |
| **Integrations (if any)** |||||
| U-31 | Push | Post a goods receipt and a shipment | The other system receives them and the signature verifies | | |
| U-32 | Resend after failure | Post while the other system is down, resend after it recovers | The push log shows the failure and reason; the resend succeeds with no duplicate posting | | |
| **Operations and security** |||||
| U-33 | Backup/restore drill | Manual backup → restore in the test environment | Data after restore matches the backup | | |
| U-34 | Concurrency | 5+ people receive, pick and ship at the same time | No errors; stock quantities are correct | | |
| U-35 | Server restart | Restart the server | Services recover automatically; PDAs work normally after reconnecting | | |

**Sign-off**: all severe issues are closed; we agree to proceed to go-live preparation.

Customer project lead: __________  Date: __________      Implementation lead: __________  Date: __________
