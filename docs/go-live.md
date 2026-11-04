# Go-Live Cutover Runbook

For project managers, implementation engineers, and the customer's warehouse supervisors and IT. It describes the standard steps from contract signing to go-live and through the two weeks after go-live. For technical installation see [deployment.md](deployment.md), for acceptance test cases see [uat.md](uat.md), and for training material see [user-guide.md](user-guide.md).

## 1. Roles

| Role | Who | Responsibilities |
|---|---|---|
| Project manager | Vendor | Plan, coordinate, convene the Go/No-Go meeting |
| Implementation engineer | Vendor | Install, configure, import data, train, on-site go-live support |
| Customer project lead | Customer (usually the warehouse manager) | Business decisions, Go/No-Go sign-off |
| Key users | Customer (1–2 per role) | Run UAT, train colleagues, first-line support after go-live |
| Customer IT | Customer | Servers, network, PDA devices, database (when using their own SQL Server), backups |

## 2. Timeline (go-live day = T0)

| When | Activity | Output / checkpoint |
|---|---|---|
| T-30 | Site survey: processes, documents, roles, SKU count and daily order volume, network and servers | Survey notes; industry preset chosen; extension modules to enable confirmed |
| T-25 | Customer IT prepares servers, network and PDAs (see deployment.md section 2) | Remote login to the server works; PDAs reach the internal network |
| T-21 | Install the test environment (`--project wmstest`) and the production environment | Sign-in works on both; `status.sh` is healthy |
| T-21 | Rerun the load test in the test environment with the customer's real volumes (performance.md section 6) | Acceptance reference values met |
| T-20 | Configure feature flags, role permissions, numbering rules and users | Key user accounts usable |
| T-18 | The customer prepares master data from the templates (locations, business partners, items) | Three Excel files |
| T-14 | Import master data into the **test environment**; key users review it | Data review signed off |
| T-14 to T-7 | UAT: key users run every case in uat.md | UAT result sheet; zero open severe issues |
| T-7 to T-3 | Training: key users first, then key users train their colleagues (vendor present) | Everyone has run their role's full process at least once |
| T-5 | Import master data into the **production environment** | Matches the test environment |
| T-3 | Go-live rehearsal: run the T-1 and T0 steps end to end in the test environment, timed | Rehearsal notes and step durations |
| T-2 | Go/No-Go meeting (section 4) | Sign-off |
| T-1 | Old process cut off, full stock count, opening stock import (section 3) | Opening adjustment posted and reconciled with the count sheets |
| T0 | Go-live; implementation engineer on site all day | All of the day's documents done in the new system |
| T+1 to T+14 | Support period (section 6) | Daily check records |
| T+14 | Support period retrospective, handover to routine operations | Open issue list, operations handover |

## 3. Data preparation and opening stock

**Import order** (System → Data import; for each type, "Validate" first and "Confirm import" only when it is clean):

1. **Units of measure**: the system already has EA/CTN/PLT and others. Add any missing units in the UI; they are not imported.
2. **Locations**: parent locations can be in the same file. Mark bins as "Pickable", or allocation ranks them last.
3. **Business partners**
4. **Items**: the base unit must already exist in the system. Batch/expiry management must match reality, because changing it once there is stock is painful.
5. **Opening stock**: **import after the full stock count on the day before go-live**.

**Opening stock steps (T-1)**

1. Agree a cut-off time (e.g. 18:00), after which nothing is received or shipped. Unload vehicles in transit that day.
2. Run a full stock count and put the results in the opening stock template by "SKU, location, quantity, batch, expiry date".
3. **Check before importing**:
   - The count sheets' total quantity equals the template's total quantity.
   - Batch and expiry date are filled in for every batch/expiry item.
4. Import. This creates a posted stock adjustment (reason: opening stock).
5. **Check after importing**:
   - The total in stock enquiry matches the count sheets.
   - Spot-check 20 locations: physical goods match the system.
6. If anything is wrong, correct it with a stock adjustment. Do not import opening stock again.

**Open documents**: purchase orders ordered but not yet received, and customer orders not yet shipped, before go-live:
- Re-enter them in the new system, or add them on T-1 through the API or import.
- Put the old document number in the remark for traceability.

## 4. Go/No-Go checklist

Go live only if every item is "Yes". If any item is "No", the customer project lead decides whether to postpone or go live with conditions.

| # | Check | Yes/No |
|---|---|---|
| 1 | No open severe UAT issues (affecting receiving, shipping or stock accuracy) | |
| 2 | Key users and their colleagues are trained and have done the work hands-on | |
| 3 | Production master data is imported and reviewed | |
| 4 | Every PDA works: can sign in, recognizes barcodes, offline submits are sent once back online | |
| 5 | Printing, network and servers tested on site in the warehouse | |
| 6 | Scheduled backups configured, and a restore drill has been done | |
| 7 | The admin's initial password has been changed; accounts and permissions assigned for each role | |
| 8 | Rollback plan (section 5) confirmed, with the decision maker and deadline agreed | |
| 9 | On-site staff scheduled for go-live day and the support period | |
| 10 | External systems to integrate (e.g. ERP) tested end to end in the test environment (skip if none) | |

## 5. Rollback plan

| Situation | Action |
|---|---|
| Problem found right after a system upgrade | `scripts/rollback.sh` returns to the pre-upgrade state (see deployment.md section 7) |
| On go-live day the system cannot support operations (e.g. widespread inability to receive or ship) | The customer project lead decides on a **business fallback**: go back to paper / the old process for the day and record every receipt and shipment. Once the issue is fixed, enter them in the new system and reconcile stock again |
| A problem in one function | Use a workaround first (e.g. the web console when the PDA is unavailable); no full fallback |

We recommend noon on go-live day as the fallback decision deadline. If a morning problem is still unresolved at noon and affects shipping, fall back, so the day's dispatches are not affected.

## 6. Post-go-live support (T+1 to T+14)

**Morning check (implementation engineer + key users, about 15 minutes)**

| Check | Where |
|---|---|
| Server status, disk space | `bash scripts/status.sh --dir /opt/wms`, `df -h` |
| Did yesterday's backup succeed | `logs/backup.log` |
| Any failed pushes to external systems | System → Integrations → push log → status "Failed" |
| Unfinished documents (draft receipts, to pick, shipments awaiting posting) | Dashboard → pending backlog |
| Shortages | Outbound → Shortages |
| Any unsent records on PDAs | "Submit queue" on each PDA's home screen |

**Issue severity**

| Level | Definition | Response |
|---|---|---|
| Severe | Cannot receive/ship, stock data wrong | Handle immediately; start the rollback plan if needed |
| Normal | A function is unavailable but a workaround exists | Handle the same day |
| Suggestion | Work habits, UI improvements | Record; evaluate together after the support period |

**Metrics to watch in the first month**

- **Stock accuracy**: cycle count high-value and fast-moving items weekly. Target a difference rate below 0.5%.
- **On-time orders**: the share of orders shipped the same day they are received (order list + shipments).
- **PDA usage**: the share of receiving, putaway and picking done on PDAs. A low share points to training or device problems.
