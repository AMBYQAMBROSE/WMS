# End-to-End Test Checklist: Receiving → Putaway → Shipping

Full functional test list for the core warehouse flow, plus the inventory, returns, PDA and cross-cutting checks the flow depends on. It is more detailed than [uat.md](uat.md): the UAT is what the customer signs off; this list is what the team runs before handing a build to UAT.

How to use:
- Run in a clean test environment seeded with the **Standard** preset (`presets/standard.json`). Turn feature flags on only in the sections that need them.
- Run **Part A** (the golden path) first. Its stock numbers are the reference for many later cases.
- Mark each case Pass / Fail. A failure in A, C, D or F (receiving, putaway, outbound, stock accuracy) blocks release.
- "Rejected" means the API returns an error, the UI shows the message, **and nothing changes**: no status change, no stock change, no ledger row.

---

## 0. Test data

| Kind | Code | Setup |
|---|---|---|
| Supplier | SUP01 | Active, supplier role |
| Supplier (inactive) | SUP99 | Inactive |
| Customer | CUS01 | Active, customer role |
| Customer (2nd) | CUS02 | Active, customer role |
| Item A | ITEM-A | Plain item; base UOM EA; conversion 1 CTN = 12 EA |
| Item B | ITEM-B | Batch managed + expiry managed; base UOM EA |
| Item C (inactive) | ITEM-C | Inactive |
| Warehouse | WH1 | Type WAREHOUSE |
| Receiving dock | DOCK-IN | Type DOCK, under WH1 |
| Staging dock | STAGE-01 | Type DOCK, under WH1 |
| Zone | Z1 | Type ZONE, under WH1 |
| Bins | BIN-A01, BIN-A02 | Type BIN, under Z1, pickable |
| Bin (non-pickable) | BIN-R01 | Type BIN, reserve / not pickable |
| Bin (locked) | BIN-L01 | Type BIN, locked |
| Users | admin, supervisor, clerk, viewer | One user per preset role |

---

## A. Golden path: worked scenario with expected numbers

Run these steps in order as **supervisor** (web) and **clerk** (PDA where noted). After each step, check the stock enquiry (on hand / allocated per location and batch) and the stock ledger.

| Step | Action | Expected document status | Expected stock afterwards |
|---|---|---|---|
| A-01 | Create PO for SUP01: ITEM-A 100 EA, ITEM-B 50 EA | PO = DRAFT, doc no. follows the numbering rule | No change |
| A-02 | Confirm PO | PO = CONFIRMED; event `purchase_order.confirmed` | No change |
| A-03 | GRN-1 from PO to DOCK-IN: A 60 EA; B 30 EA batch L1, expiry today+90 → post | GRN-1 = POSTED; PO = PARTIALLY_RECEIVED | DOCK-IN: A 60; B L1 30 |
| A-04 | GRN-2 (on the PDA): A **3 CTN + 4 EA**; B 20 EA batch L2, expiry today+30 → post | GRN-2 = POSTED; PO = RECEIVED | DOCK-IN: A 100 (3 CTN converted to 36 EA); B L1 30, L2 20 |
| A-05 | Putaway from GRN-1 + GRN-2: A 100 → BIN-A01; B L1 30 and B L2 20 → BIN-A02 → post | PUTAWAY = POSTED | DOCK-IN: 0; BIN-A01: A 100; BIN-A02: B L1 30, L2 20 |
| A-06 | Create SO for CUS01: A 70 EA, B 25 EA → confirm | SO = CONFIRMED | No change |
| A-07 | Allocate SO, staging STAGE-01 | Pick list PICK-1 = OPEN; lines sorted by bin code | Allocated: BIN-A01 A 70; BIN-A02 **B L2 20 (earlier expiry first), L1 5** |
| A-08 | PDA: pick PICK-1: A 70 OK; B L2 20 OK; B L1 **short-pick 2 of 5** → post | PICK-1 = POSTED; SO = IN_PROGRESS | BIN-A01: A 30; BIN-A02: B L1 28, L2 0; STAGE-01: A 70, B 22. Allocated all back to 0; SO line B shows 3 unallocated |
| A-09 | Create shipment for SO, enter vehicle plate, driver and seal no. → post | SHIP-1 = POSTED; SO = PARTIALLY_SHIPPED | STAGE-01: 0 |
| A-10 | Allocate again → PICK-2 (B L1 3) → pick 3 → post → shipment SHIP-2 → post | SO = SHIPPED; event `sales_order.shipped` | BIN-A02: B L1 25; STAGE-01: 0 |
| A-11 | **Reconcile**: for each item and location, the sum of the ledger = on hand in the stock enquiry | — | A: 100 in, 70 out, 30 left. B: 50 in, 25 out, 25 left. No negative balances; allocated = 0 everywhere |
| A-12 | Dashboard and turnover report for today | — | Receipts / shipments / stock totals match A-11 (at most 30 seconds delay) |
| A-13 | Audit log | — | Every create/confirm/post above is listed with user and time |

---

## B. Purchase orders

| ID | Test | Steps | Expected |
|---|---|---|---|
| B-01 | Create PO | Supplier, expected date, several lines with different UOMs | Saved as DRAFT; doc no. generated |
| B-02 | Required fields | Save without supplier / without lines / with qty 0 or negative | Rejected with a field message |
| B-03 | Inactive supplier | Use SUP99 | Rejected: "Supplier SUP99 is inactive" |
| B-04 | Partner is not a supplier | Use CUS01 as supplier | Rejected: "... is not a supplier" |
| B-05 | Inactive item | Add ITEM-C | Rejected: "Item ITEM-C is inactive" |
| B-06 | Unit without conversion | Use a UOM the item has no packing unit for | Not offered in the unit dropdown; via the API: rejected "has no conversion from this unit to its base unit" |
| B-07 | Edit draft | Change qty and add/remove lines on a DRAFT | Saved |
| B-08 | Edit after confirm | Edit a CONFIRMED PO | Rejected: "is CONFIRMED; cannot edit" |
| B-09 | Confirm | Confirm a DRAFT | CONFIRMED; event pushed |
| B-10 | Cancel | Cancel a DRAFT / a CONFIRMED PO with no receipts | CANCELLED; cannot receive any more |
| B-11 | Close a partially received PO | Close a PARTIALLY_RECEIVED PO | CLOSED; no more receipts allowed; received stock stays |
| B-12 | Illegal transitions | Confirm a CANCELLED PO; cancel a RECEIVED PO | Rejected with the current status in the message |
| B-13 | List / filter / search | Filter by status, supplier, date; search doc no. | Correct results, pagination works |
| B-14 | PO receiving progress | Open the detail after A-03 | Shows ordered / received / remaining per line |

## C. Receiving (GRN)

| ID | Test | Steps | Expected |
|---|---|---|---|
| C-01 | Receive from a DRAFT PO | Create a GRN for an unconfirmed PO | Rejected: cannot receive |
| C-02 | Receive from a CLOSED / CANCELLED / RECEIVED PO | Create a GRN | Rejected |
| C-03 | Partial receipt | Receive part of a line | PO = PARTIALLY_RECEIVED; remaining qty correct |
| C-04 | Full receipt across several GRNs | Receive the rest in a second GRN | PO = RECEIVED |
| C-05 | Receipt in a larger UOM | Receive in CTN | Stock in base UOM (×12) |
| C-06 | Line from another PO | Send a line id that belongs to another PO (API) | Rejected: "Line n does not belong to purchase order ..." |
| C-07 | Over-receipt, flag off | Receive more than ordered (across GRNs as well) | Rejected with ordered / received / this receipt quantities |
| C-08 | Over-receipt, flag on | Enable `ALLOW_OVER_RECEIPT`, repeat C-07 | Accepted; PO = RECEIVED; received qty > ordered |
| C-09 | Batch required | Receive ITEM-B without batch | Rejected: "is batch managed; a batch number is required" |
| C-10 | Expiry required | Receive ITEM-B without expiry date | Rejected: "is expiry managed; an expiry date is required" |
| C-11 | Plain item with batch | Receive ITEM-A with a batch typed in | Batch ignored / normalized (not stored as a separate batch) |
| C-12 | Receive to a non-stock location | Target is a ZONE / WAREHOUSE | Rejected: only BIN/DOCK allowed |
| C-13 | Receive to a locked / inactive location | Target BIN-L01 | Rejected: "is locked" / "is inactive" |
| C-14 | Draft GRN has no stock effect | Save GRN, don't post | Stock unchanged; PO received qty unchanged |
| C-15 | Post | Post the draft | Stock + ledger rows (type RECEIVE); event `grn.posted` |
| C-16 | Post twice | Post the same GRN again (double click / second tab) | Second attempt rejected; stock added once only |
| C-17 | PO closed while GRN is draft | Draft GRN → close PO → post GRN | Rejected; no stock |
| C-18 | Cancel draft GRN | Cancel | CANCELLED; can't be posted |
| C-19 | Cancel posted GRN | Cancel a POSTED GRN | Rejected |
| C-20 | Photo on receipt | Attach a damage photo (JPEG/PNG/WebP) | Stored and visible on the GRN; a PDF / empty file is rejected |
| C-21 | Receive into a location being counted | Count in progress on DOCK-IN, then post a GRN to it | Rejected: "is being counted ...; stock movements are paused" |

## D. Putaway

| ID | Test | Steps | Expected |
|---|---|---|---|
| D-01 | Putaway from a GRN | Create from a POSTED GRN | Lines pre-filled from the receipt |
| D-02 | From an unposted GRN | Reference a DRAFT / CANCELLED GRN | Rejected: cannot put away |
| D-03 | Split across bins | One GRN line to two bins | Both bins increase; dock decreases by the total |
| D-04 | Target must be a BIN | Target STAGE-01 (DOCK) or Z1 (ZONE) | Rejected |
| D-05 | Same source and target | From = to | Rejected: "Source and target locations cannot be the same" |
| D-06 | More than available on the dock | Put away more than DOCK-IN holds | Rejected: "Insufficient stock ..." with the quantities |
| D-07 | Wrong batch | Put away B with a batch not on the dock | Rejected: insufficient stock for that batch |
| D-08 | Locked / counted target | Target BIN-L01, or a bin with a count in progress | Rejected |
| D-09 | Post | Post | Ledger PUTAWAY_OUT (dock) + PUTAWAY_IN (bin) in one transaction; event `putaway.posted` |
| D-10 | Cancel draft / posted | Cancel each | Draft → CANCELLED; posted → rejected |
| D-11 | PDA putaway | Scan source → item → target bin → qty | Same result as on the web |
| D-12 | Putaway without a GRN | Free putaway from a dock | Allowed; no reference document |

## E. In-warehouse inventory (between putaway and shipping)

| ID | Test | Steps | Expected |
|---|---|---|---|
| E-01 | Stock enquiry by item / location / batch | Query | On hand, allocated, available, batch, expiry are correct |
| E-02 | Stock ledger | Filter by item and date | Every movement with type, doc no., user; running totals add up |
| E-03 | Move bin → bin | Move A 10 BIN-A01 → BIN-A02 | Both bins change; ledger MOVE_OUT / MOVE_IN |
| E-04 | Move allocated stock | Move stock that is allocated but not picked | Rejected: insufficient stock (allocated shown) |
| E-05 | Move to the same bin | From = to | Rejected |
| E-06 | Adjustment in / out | Reason DAMAGE, −5; reason FOUND, +3 | Stock changes; ledger ADJUST_OUT / ADJUST_IN with the reason |
| E-07 | Adjustment qty 0 | Line qty 0 | Rejected: "adjustment quantity cannot be 0" |
| E-08 | Adjustment below zero / below allocated | Adjust out more than available | Rejected |
| E-09 | Adjustment without reason / inactive reason | Save | Rejected |
| E-10 | Clerk cannot post adjustment | Clerk creates; tries to post | Create OK; post rejected (no `adjustment.post`); supervisor posts OK |
| E-11 | Cycle count: start | Count BIN-A01, BIN-A02 | COUNTING; those bins block receive / putaway / move / pick posting / allocation |
| E-12 | Count a non-stock location | Include Z1 | Rejected: does not hold stock |
| E-13 | Count overlap | Start a second count with BIN-A01 | Rejected: already in another count |
| E-14 | Count with open picks | Bin has stock reserved by an OPEN pick list | Rejected: finish or cancel the picks first |
| E-15 | Blind count | User without `cycle_count.view_expected` | Book quantities hidden on web and PDA |
| E-16 | Post with uncounted lines | Leave a line empty | Rejected: lines not counted yet |
| E-17 | Book stock not counted | On-book stock with no entry | Rejected: enter it (0 if nothing is there) |
| E-18 | Recount | Request recount on a counted line | New round; un-counted line → "no recount needed" |
| E-19 | Post with differences | Count A 98 (book 100); count unknown batch found | Ledger COUNT_LOSS 2 / COUNT_GAIN; bins unblocked; event `cycle_count.posted` |
| E-20 | Cancel count | Cancel a count in progress | Bins unblocked; no stock change |
| E-21 | Location lock | Lock BIN-A01 | No movements in or out; not allocated from |

## F. Sales orders and allocation

| ID | Test | Steps | Expected |
|---|---|---|---|
| F-01 | Create SO | Customer, lines, expected date | DRAFT |
| F-02 | Invalid partner / item | Inactive customer, supplier as customer, inactive item | Rejected |
| F-03 | Edit after confirm | Edit a CONFIRMED SO | Rejected |
| F-04 | Allocate a DRAFT SO | Allocate before confirm | Rejected |
| F-05 | FEFO order | Two batches, different expiry | Earlier expiry allocated first; no-expiry stock last |
| F-06 | Pickable bins first | Same item in BIN-A01 (pickable) and BIN-R01 (reserve) | Pickable bin used first |
| F-07 | FIFO tiebreak | Same expiry, received on different days | Older stock first |
| F-08 | Expired stock excluded | Batch with expiry before today | Never allocated |
| F-09 | Excluded locations | Stock only in locked / inactive / counted bins, or on a dock | Not allocated (normal allocation uses BIN only) |
| F-10 | Partial allocation | Order more than available | What exists is allocated; the rest is in the shortage list and shortage report |
| F-11 | Nothing available | No stock at all | Rejected: "Insufficient stock, nothing could be allocated" |
| F-12 | Nothing left to allocate | Allocate a fully allocated SO again | Rejected: "has nothing left to allocate" |
| F-13 | Staging must be a DOCK | Staging = a BIN | Rejected |
| F-14 | Allocated stock is reserved | After allocation, try to move / adjust / return-to-supplier it | Rejected |
| F-15 | Concurrent allocation | Two users allocate two orders for the same last 10 EA at the same time | Total allocated ≤ 10; no negative available |
| F-16 | Shortage report | Open after F-10 | Lists order, item, short qty, sorted by expected date |

## G. Picking

| ID | Test | Steps | Expected |
|---|---|---|---|
| G-01 | Pick list content | Open the pick list | From bin, item, batch, expiry, qty; sorted by bin code |
| G-02 | Confirm a line | Confirm at the full qty | Line confirmed with user and time |
| G-03 | Short pick | Confirm less than planned | Accepted; on post the shortfall goes back to unallocated on the SO |
| G-04 | Over pick | Confirm more than planned | Rejected: "can pick at most ..." |
| G-05 | Pick zero | Confirm 0 | Accepted; full line goes back to unallocated |
| G-06 | Confirm all (web) | "Confirm all" | Every unconfirmed line set to its planned qty |
| G-07 | Post with unconfirmed lines | Post | Rejected: "n lines not confirmed yet" with the list |
| G-08 | Post | Post | Bin −picked and its allocation released in full, staging +picked (reserved for the order until shipped); ledger PICK_OUT / in; event `pick.posted` |
| G-09 | Source bin locked or counted before post | Lock the bin after allocation, then post | Rejected |
| G-10 | Cancel open pick list | Cancel | Allocation released; SO qty back to unallocated |
| G-11 | Act on a posted pick | Confirm / cancel after post | Rejected |
| G-12 | PDA guided pick | Scan bin → item → qty; wrong bin or wrong item scanned | Wrong scans are refused with a message; correct flow confirms the line |
| G-13 | Picker KPI | Report after G-08 | Lines / qty / time per picker match |
| G-14 | Return picked goods to stock | On a posted pick list whose goods have not shipped: Return goods to stock | Pick list = REVERSED; goods back in their bins, staging emptied; SO qty back to unallocated; ledger UNPICK_OUT / UNPICK_IN; event `pick.reversed` |
| G-15 | Return to stock after shipping or while loading | Same, after the shipment posted / with a draft shipment | Rejected: "already shipped" / "being loaded" |
| G-16 | Same item on two order lines | Order 5 + 5 of an item with 6 in stock, allocate | Pick list totals 6, shortage 4; the bin's allocated = 6 (never above on hand) |

## H. Shipping

| ID | Test | Steps | Expected |
|---|---|---|---|
| H-01 | Create shipment | For an SO with picked goods | Lines = everything picked but not yet shipped, from staging |
| H-02 | Nothing to ship | SO with no posted picks | Rejected: "has no picked goods waiting to ship" |
| H-03 | Second draft shipment | Create another while one is DRAFT | Rejected: "already has an unposted shipment" |
| H-04 | Vehicle details | Enter plate, driver, seal no. | Saved and printed on the delivery note |
| H-05 | Post | Post | Staging decreases; SO = PARTIALLY_SHIPPED or SHIPPED; event `shipment.posted` |
| H-06 | Cancel draft shipment | Cancel | Goods stay in staging; a new shipment can be created |
| H-07 | Cancel posted shipment | Cancel | Rejected |
| H-08 | Staging stock touched before post | Move staging stock away | Move rejected: the goods are reserved for the order until shipped |
| H-09 | Print delivery note / pick list | Print from the detail page | Correct content and layout |

## I. Order close and cancel

| ID | Test | Steps | Expected |
|---|---|---|---|
| I-01 | Cancel a confirmed SO with no activity | Cancel | CANCELLED |
| I-02 | Cancel with open pick list | Cancel | Rejected: "has open pick lists; cancel them first" |
| I-03 | Cancel with picks or shipments | Cancel after a posted pick | Rejected: "Return the picked goods to stock … or close the order" |
| I-04 | Close with open pick list | Close | Rejected |
| I-05 | Close with unposted shipment | Close | Rejected |
| I-06 | Close with goods in staging | Picked but not shipped | Rejected: "ship them, or return them to stock" |
| I-07 | Close a partially shipped SO | All shipments posted, rest not needed | CLOSED; remaining qty leaves the shortage report |
| I-08 | Cancel after returning picked goods | Posted pick, Return goods to stock, then Cancel the SO | CANCELLED |

## J. Extension modules (enable the flag first)

| ID | Flag | Test | Expected |
|---|---|---|---|
| J-01 | RETURNS | Customer return from a shipped SO: one line restocked to a bin, one scrapped | Restocked line adds stock; scrapped adds none; event `return_in.posted` |
| J-02 | RETURNS | Return more than shipped (across several returns) | Rejected: "exceeds the returnable quantity" |
| J-03 | RETURNS | Return for a different customer / item not on the order / restock without location | Each rejected with its message |
| J-04 | RETURNS | Return to supplier from a bin, linked to a PO | Stock decreases; supplier must match the PO |
| J-05 | RETURNS | Return to supplier using allocated stock | Rejected |
| J-06 | RETURNS | Flag off | Return menus hidden; API refuses |
| J-07 | CROSS_DOCK | Receive to DOCK-IN, allocate with source DOCK-IN | Pick list takes goods from DOCK-IN straight to staging; no putaway |
| J-08 | CROSS_DOCK | Source = staging | Rejected: cannot be the same location |
| J-09 | REPACK | Consume 1 CTN of A, produce 12 EA of a new item | One posting does both |
| J-10 | REPACK | Consume more than available | Rejected; nothing changes (atomic) |
| J-11 | RETURNABLE_ASSET | Lend 10 pallets to CUS01, receive 4 back | Outstanding 6 |
| J-12 | RETURNABLE_ASSET | Receive 7 back when 6 are outstanding | Rejected |

## K. PDA (mobile app)

| ID | Test | Steps | Expected |
|---|---|---|---|
| K-01 | Sign in / sign out | Each role | Only permitted screens shown |
| K-02 | Master data cache | Sign in, go offline, scan known SKUs and bins | Items and locations resolve from the cache |
| K-03 | Scan input | Scanner wedge input into receive / putaway / pick / move / count | Field is focused, scan accepted without tapping |
| K-04 | Unknown barcode | Scan an unknown code | Clear message; nothing submitted |
| K-05 | Offline queue | Wi-Fi off, do a receipt and a putaway, Wi-Fi on | Queued, submitted automatically in order, **no duplicates** |
| K-06 | Business error in queue | Queue an over-receipt offline, reconnect | Item marked failed with the server message; not retried forever |
| K-07 | Session expired in queue | Expire the token, reconnect | Queue pauses until sign-in, then continues |
| K-08 | Retry after timeout | Server answers slowly; app retries the same request | Same request ID → one document only |
| K-09 | Photo offline | Take a damage photo offline | Uploaded with the queued action once online |
| K-10 | Restart while queued | Kill the app with items queued | Queue survives the restart |

## L. Cross-cutting

| ID | Area | Test | Expected |
|---|---|---|---|
| L-01 | Permissions | For each role, try every menu and action (UI and direct API) | Only granted actions work; others get 403 |
| L-02 | Permissions | Remove a permission from a signed-in user | Takes effect on next request / refresh |
| L-03 | Users | Deactivate a user; deactivate yourself; remove your own user-management right | Deactivated user locked out; the last two are rejected |
| L-04 | Roles | Edit / delete a system role; delete a role still in use | Rejected |
| L-05 | Idempotency | Send the same create with the same client request ID twice | Second returns the first document |
| L-06 | Idempotency | Reuse a request ID for different content | Rejected: "Request ID already used by document ..." |
| L-07 | Concurrency | 5+ users receive, put away, pick and ship at the same time | No errors except expected business rejections; A-11 style reconcile still matches |
| L-08 | Stock invariant | After any run | No balance with on hand < 0, allocated < 0 or allocated > on hand |
| L-09 | Doc numbering | Create documents across a day / month boundary | Numbers follow the rule, no gaps from failed saves leaking, no duplicates |
| L-10 | Integration events | Subscribe a webhook to all events; run Part A | One event per status change listed in `event_catalog.py`; signature verifies |
| L-11 | Integration failure | Endpoint down → post → redeliver after recovery | Log shows failure and reason; redeliver succeeds; disabled connector refuses retry |
| L-12 | Import | Import items / locations / partners (xlsx and UTF-8 csv) with 2 bad rows | Row numbers and reasons reported; nothing imported until fixed; non-UTF-8 csv rejected |
| L-13 | Reports | Dashboard, occupancy, turnover, partner ledger, expiry (30 days), picker KPI; CSV export | Numbers match documents; exports open in Excel; end date before start date rejected |
| L-14 | Audit log | Filter by user / document | All changes recorded with before/after |
| L-15 | Live updates | Two browsers on the same list; post in one | The other refreshes on its own |
| L-16 | Health / restart | Restart backend and worker | Services recover; PDAs reconnect and flush their queues |
| L-17 | Backup / restore | Backup → restore to test | Data identical; Part A reconcile still matches |
| L-18 | Upgrade | Upgrade from the previous version with data, then roll back | Migrations run cleanly both ways; no data loss |
| L-19 | Performance | ~50,000 SKUs: item search, stock enquiry, allocation of a 200-line order | Within the targets in [performance.md](performance.md) |
| L-20 | UI basics | Every list: filter, sort, pagination, empty state; every form: validation messages; phone-width layout | No broken layouts, no untranslated text |

---

**Exit criteria:** Part A passes end to end and reconciles; every case in B–I passes; K-05 and K-08 pass (no duplicates); L-07 and L-08 pass. Open issues outside these are listed and agreed before UAT.
