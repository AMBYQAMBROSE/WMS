# Load Test Report (Phase 8)

For implementation teams and customer IT. It describes how the system performs at "large single warehouse" volumes, the problems found and fixed during load testing, and server sizing recommendations.

> **Summary**
>
> - Assumption: 5,000 orders/day on average, with a 3x peak (1,500 orders/hour).
> - Outbound end to end and receiving were stable. Write p95 was under 0.2 s and the error rate was 0.03%.
> - Read and scan medians were 20–70 ms. Under peak load, tail latency (p95 1–2 s) was limited by the test machine: the database, backend and load generator shared one laptop and the CPU was saturated.
> - **Before go-live, rerun the test on the customer's servers with the customer's data volumes** (tools in section 6).

## 1. Test environment and data volume

| Item | Setup |
|---|---|
| Machine | One Windows 11 laptop, 12 logical CPUs |
| Database | SQL Server 2022 container (Docker Desktop, 4GB memory limit) |
| Backend | 4 processes (uvicorn workers), on the same machine as the database and load generator |

| Data | Count | Notes |
|---|---|---|
| Item SKUs | 50,000 | 30% batch/expiry managed |
| Locations | 20,036 | 20 zones × 1,000 bins + docks |
| Business partners | 3,300 | 300 suppliers, 3,000 stores |
| Stock balance rows | 99,606 | |
| Documents | 550k headers / 2.21M lines | 90 days of history: 120 goods receipts and 2,000 sales orders (with picks and shipments) per day |
| Stock ledger | 870k rows | |

## 2. Test scenarios

| Scenario | Business peak (peak) | Saturation (stress) |
|---|---|---|
| Outbound (order → confirm → allocate → confirm picks → post pick → create shipment → post shipment) | 25 orders/minute (1,500/hour) | 15 users, no pauses |
| Receiving (create PO → confirm → receive → post) | 4 orders/minute | 5 users, no pauses |
| PDA scans (item stock / location stock lookup) | 25 users, one every 2–4 s | 25 users, one every 0.5–1.5 s |
| Office (order list, dashboard, shortages, ledger, turnover report, item search) | 5 users, one every 2–5 s | Same |

## 3. Problems found and fixed

Before the fixes, 3 minutes at saturation gave:
- **4.71% errors**.
- Only 7% of order confirmations and allocations succeeded.
- Read p95 was 11.4 s and write p95 was 17.3 s.

| # | Problem | Cause | Fix | Effect |
|---|---|---|---|---|
| 1 | Many **deadlocks** under concurrency; order confirm/allocate failed | SQL Server does not index foreign keys automatically. Looking up picks/shipments by source document scanned all 550k rows holding shared locks, which blocked inserts and vice versa | Added indexes (source document, list sort, line links, pick confirm time, stock by location). Enabled READ_COMMITTED_SNAPSHOT so plain queries take no shared locks | Errors 4.71% → 0.04%; confirm/allocate 100% successful |
| 2 | Document creation p95 reached 7 s | Taking a document number locked the numbering rule row until the whole business transaction ended, so documents of the same type queued | Numbers are taken in a separate short transaction | Create p95 7.2 s → 0.2 s (peak) |
| 3 | "Connection pool timeout" at peak | Each process had only 15 connections but 40 concurrent threads. Numbering needed a second connection, so requests waiting on each other used up the pool | Pool 20+20 (configurable); numbering uses its own small pool | No more connection timeouts |
| 4 | Stock turnover and partner ledger reports **failed outright** | Batch queries by item ID put 40,000 parameters in one statement, over SQL Server's 2,100 limit | Aggregation, joins, sorting and limiting all happen in the database. Pages show at most 1,000 rows; the server exports the full data as CSV | Turnover 4.6 s → 0.33 s; ledger 10 s → 1.1 s |
| 5 | The turnover report got slower as history grew | Opening = sum of all ledger entries before the start date | Opening/closing = "current balance − later ledger entries", so only the period's entries are scanned. Verified against the old algorithm for all 40,000 items | Peak p95 2.0 s → 0.66 s |
| 6 | Order list took 1.4 s | Sort column directions did not match the index, so 160,000 orders were sorted first | Sort direction matches the index | 0.25 s → 0.04 s |
| 7 | Dashboard over 1.5 s at peak | 23 aggregate queries per request | Cached 30 s per process (the page refreshes every minute) | Peak median 1.5 s → 15 ms |
| 8 | Dropdowns could only show the first 500 items/locations/partners | The dropdown fetched 500 rows at once and filtered in the browser | Typing a keyword searches the server; master data list pages got a search box | Search across 50,000 items in about 0.2 s |
| 9 | PDA master data was 19.9MB and took 6.3 s, and did not fit on Android | All master data was downloaded at once and stored whole in AsyncStorage (Android default: 6MB total, about 2MB per entry) | Added a compact format + gzip. The PDA stores it in a file, and scan lookup uses map indexes | 2.4 s, 3.6MB transferred |

## 4. Final results

### 4.1 Business peak (run directly on the host, 5 minutes)

3,671 requests with 1 failure (0.03%). 124 orders completed the full outbound flow (≈ 1,490 orders/hour).

| Kind | p50 | p95 | p99 |
|---|---|---|---|
| Writes (create, confirm, allocate, pick, ship, receive) | 86 ms | 169 ms | 274 ms |
| PDA stock lookups | 18 ms | 0.65–1.8 s (varies between runs) | 2–4 s |
| Office queries | 70 ms | 2.2 s | 4.4 s |
| Stock turnover report (30 days) | 560 ms | 0.7–2.9 s | |

### 4.2 Saturation (5 minutes)

10,941 requests with a 0.01% error rate. 565 outbound orders completed in 5 minutes (≈ 6,800/hour), about 4.5× the peak assumption. The test machine's CPU stayed at 99–100%.

### 4.3 Where the tail comes from

| Isolated test (1 minute each) | Scan p95 |
|---|---|
| Scans only | 42 ms |
| Scans + office queries | 98 ms |
| Scans from the host while outbound + receiving run | 35 ms |

Each kind of request is fast on its own. The tail appears when report queries run alongside heavy writes and every program shares one machine's CPU. With the database on its own server, with dedicated CPU and memory, production should be much better, but this must be confirmed in the customer environment.

## 5. Server sizing (for these volumes; adjust after measuring on site)

| Role | Recommendation | Notes |
|---|---|---|
| Application server (web + backend + worker) | 8 vCPU / 16GB / 100GB SSD | Set `WEB_CONCURRENCY=8` in `.env` (about the CPU core count) |
| Database server | 8 cores / 32GB / SSD (both data and tempdb on SSD) | For around 50,000 SKUs and 5,000 orders/day; add more for larger volumes based on measurements |
| SQL Server settings | `READ_COMMITTED_SNAPSHOT ON` (enabled automatically by the upgrade scripts). Recommended: `max degree of parallelism = 4`, `cost threshold for parallelism = 50`, `max server memory` leaving 4GB for the OS | RCSI keeps row versions in tempdb, so put tempdb on SSD |
| Connections | Up to 40 per backend process + 15 for numbering | Tunable via `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` |

Document numbers: to avoid queuing on document creation, numbers are taken in a separate transaction. If the business operation fails, that number is skipped, so **document numbers can have gaps** (as in most ERPs).

## 6. Rerunning in the customer environment

The tools are in `tools/perf/`:

```bash
# 1. Prepare a dedicated load-test database (fresh install; never the production database)
# 2. Generate data (run in the backend venv; change volumes in the constants at the top of perf_seed.py)
python tools/perf/perf_seed.py "DRIVER={ODBC Driver 18 for SQL Server};SERVER=loadtest-db;DATABASE=wms;UID=..;PWD=..;TrustServerCertificate=yes" --confirm --export data.json
# 3. Business-peak test (run on a machine that reaches the backend directly, not through Docker port forwarding)
python tools/perf/peak_load.py data.json 5 http://server:port
# 4. Optional: k6 saturation test
k6 run -e BASE=http://server:port/api/v1 -e DATA=data.json -e PROFILE=stress tools/perf/load.js
```

Adjust the arrival rates in `peak_load.py` (outbound/receiving orders per minute) to the customer's real peak.

Acceptance reference at business peak:
- Write p95 below 1.5 s
- Scan p95 below 0.5 s
- Error rate below 0.1%
