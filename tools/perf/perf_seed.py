"""Load-test data generator: bulk-writes straight to the database (the API is too slow). Only for a dedicated load-test database; writes hundreds of thousands of documents!

Usage (run in the apps/backend venv; the database must be migrated and seeded first):
    python perf_seed.py "<ODBC connection string>" --confirm [--export data.json]
Example:
    python perf_seed.py "DRIVER={ODBC Driver 18 for SQL Server};SERVER=127.0.0.1,14333;DATABASE=wms;UID=sa;PWD=...;TrustServerCertificate=yes" --confirm

Volumes are the constants below (assuming a "large single warehouse"; adjust to the customer's SKU count and daily orders after signing);
stock balances are built last by summing the ledger, so ledger total == balance. --export writes the IDs the load scripts need (peak_load.py / load.js).
"""

import argparse
import json
import random
import sys
import time
import uuid
from datetime import date, datetime, timedelta

import pyodbc

parser = argparse.ArgumentParser(description="Generate load-test data")
parser.add_argument("conn", help="ODBC connection string")
parser.add_argument("--confirm", action="store_true", help="confirm this is a dedicated load-test database")
parser.add_argument("--export", help="write the IDs the load scripts need to this JSON file")
args = parser.parse_args()
if not args.confirm:
    sys.exit("This writes a large amount of test data; add --confirm once you are sure this is a dedicated load-test database")
CS = args.conn

N_ITEMS = 50_000
N_ZONES, BINS_PER_ZONE = 20, 1_000
N_SUPPLIERS, N_CUSTOMERS = 300, 3_000
STOCKED_RATIO = 0.8
DAYS = 90
GRN_PER_DAY, GRN_LINES = 120, 5
SO_PER_DAY, SO_LINES = 2_000, 4

random.seed(42)
conn = pyodbc.connect(CS, autocommit=False)
cur = conn.cursor()
cur.fast_executemany = True

tenant = str(cur.execute("SELECT id FROM tenant WHERE code='DEFAULT'").fetchval())
if cur.execute("SELECT COUNT(*) FROM document_header").fetchval() > 0:
    sys.exit("This database already has business documents; refusing to write load-test data (use a fresh load-test database)")
admin = str(cur.execute("SELECT id FROM [user] WHERE username='admin'").fetchval())
ea = str(cur.execute("SELECT id FROM uom WHERE code='EA'").fetchval())
NOW = datetime.utcnow().replace(microsecond=0)
TODAY = date.today()
uid = lambda: str(uuid.uuid4())


def audit(ts):
    # tenant_id, id, created_at, created_by, updated_at, updated_by, is_deleted, row_version
    return [tenant, uid(), ts, admin, ts, admin, 0, 0]


AUDIT_COLS = "tenant_id, id, created_at, created_by, updated_at, updated_by, is_deleted, row_version"
started = time.time()


def bulk(table, cols, rows, chunk=20_000):
    sql = f"INSERT INTO {table} ({cols}, {AUDIT_COLS}) VALUES ({', '.join('?' * (cols.count(',') + 1 + 8))})"
    for i in range(0, len(rows), chunk):
        cur.executemany(sql, rows[i:i + chunk])
    conn.commit()
    print(f"  {table}: +{len(rows):,}  ({time.time() - started:.0f}s)", flush=True)


# ---------------------------------------------------------------- Master data
print("Master data")
partners = []
suppliers, customers = [], []
for i in range(1, N_SUPPLIERS + 1):
    a = audit(NOW)
    suppliers.append(a[1])
    partners.append([f"PS{i:04d}", f"Perf supplier {i:04d}", "supplier", None, None, None, 1, *a])
for i in range(1, N_CUSTOMERS + 1):
    a = audit(NOW)
    customers.append(a[1])
    partners.append([f"PC{i:05d}", f"Perf store {i:05d}", "customer", None, None, None, 1, *a])
bulk("business_partner", "code, name, partner_type, contact_name, contact_phone, address, is_active", partners)

items, barcodes = [], []
item_ids, expiry_items = [], set()
for i in range(1, N_ITEMS + 1):
    managed = i % 10 < 3
    a = audit(NOW)
    item_ids.append(a[1])
    if managed:
        expiry_items.add(a[1])
    code = f"P{i:06d}"
    items.append([code, f"69{i:011d}", f"Perf item {i:06d}", f"Category {i % 50:02d}", ea, int(managed), int(managed), 0, 365 if managed else None, 1, *a])
    barcodes.append([a[1], f"69{i:011d}", ea, *audit(NOW)])
bulk("item", "sku_code, barcode, name, category, base_uom_id, is_batch_managed, is_expiry_managed, is_serial_managed, shelf_life_days, is_active", items)
bulk("item_barcode", "item_id, barcode, uom_id", barcodes)

locs = []
wh = audit(NOW)
locs.append(["PWH", "Perf main warehouse", "WAREHOUSE", None, "/PWH", 0, 0, None, 1, *wh])
bins = []
for z in range(1, N_ZONES + 1):
    za = audit(NOW)
    zcode = f"Z{z:02d}"
    locs.append([zcode, f"Zone {z}", "ZONE", wh[1], f"/PWH/{zcode}", 0, 0, None, 1, *za])
    for b in range(1, BINS_PER_ZONE + 1):
        ba = audit(NOW)
        code = f"{zcode}-{b:04d}"
        bins.append(ba[1])
        # The first 300 bins in each zone are pick faces
        locs.append([code, code, "BIN", za[1], f"/PWH/{zcode}/{code}", int(b <= 300), 0, None, 1, *ba])
docks = {}
for code in [f"IN{i:02d}" for i in range(1, 6)] + [f"OUT{i:02d}" for i in range(1, 11)]:
    da = audit(NOW)
    docks[code] = da[1]
    locs.append([code, code, "DOCK", wh[1], f"/PWH/{code}", 0, 0, None, 1, *da])
bulk("location", "code, name, location_type, parent_id, path, is_pickable, is_locked, capacity_qty, is_active", locs)

# ---------------------------------------------------------------- Opening stock
print("Opening stock")
ledger = []
keys = []  # (item, bin, batch, expiry)
remaining = {}
opening_at = datetime.combine(TODAY - timedelta(days=DAYS + 1), datetime.min.time())
for item in random.sample(item_ids, int(N_ITEMS * STOCKED_RATIO)):
    for _ in range(random.randint(1, 4)):
        if item in expiry_items:
            batch = f"L{random.randint(1, 999):03d}"
            expiry = TODAY + timedelta(days=random.randint(-15, 400))
        else:
            batch, expiry = None, None
        key = (item, random.choice(bins), batch, expiry)
        if key in remaining:
            continue
        qty = random.randint(200, 2_000)
        remaining[key] = qty
        keys.append(key)
        ledger.append([key[0], key[1], batch, expiry, qty, "ADJUST_IN", None, opening_at, *audit(opening_at)])
print(f"  opening balance rows {len(keys):,}")

# ---------------------------------------------------------------- Historical documents
print("Historical documents")
headers, lines = [], []
LEDGER_COLS = "item_id, location_id, batch_no, expiry_date, qty_change, movement_type, ref_document_line_id, occurred_at"
HEADER_COLS = "doc_type, doc_no, status, partner_id, ref_document_id, location_id, expected_date, posted_at, remark"
LINE_COLS = "document_id, line_no, item_id, uom_id, qty_planned, qty_actual, batch_no, expiry_date, from_location_id, to_location_id, ref_line_id, confirmed_at, confirmed_by"


def flush_history():
    bulk("document_header", HEADER_COLS, headers)
    bulk("document_line", LINE_COLS, lines)
    bulk("stock_ledger", LEDGER_COLS, ledger)
    headers.clear(), lines.clear(), ledger.clear()


flush_history()  # Write the opening ledger entries first
for d in range(DAYS, 0, -1):
    day = TODAY - timedelta(days=d)
    base = datetime.combine(day, datetime.min.time())
    tag = day.strftime("%y%m%d")
    for n in range(GRN_PER_DAY):
        ts = base + timedelta(seconds=random.randint(3_600, 36_000))
        h = audit(ts)
        headers.append(["GRN", f"HGRN{tag}-{n:04d}", "POSTED", random.choice(suppliers), None, docks["IN01"], None, ts, None, *h])
        for ln in range(1, GRN_LINES + 1):
            key = random.choice(keys)
            qty = random.randint(10, 100)
            la = audit(ts)
            lines.append([h[1], ln, key[0], ea, qty, qty, key[2], key[3], None, key[1], None, None, None, *la])
            ledger.append([key[0], key[1], key[2], key[3], qty, "RECEIVE", la[1], ts, *audit(ts)])
            remaining[key] += qty
    for n in range(SO_PER_DAY):
        ts = base + timedelta(seconds=random.randint(3_600, 36_000))
        cust = random.choice(customers)
        so, pick, ship = audit(ts), audit(ts), audit(ts)
        headers.append(["SO", f"HSO{tag}-{n:05d}", "SHIPPED", cust, None, None, day, None, None, *so])
        headers.append(["PICK", f"HPK{tag}-{n:05d}", "POSTED", cust, so[1], docks["OUT01"], None, ts, None, *pick])
        headers.append(["SHIP", f"HDO{tag}-{n:05d}", "POSTED", cust, so[1], docks["OUT01"], None, ts, None, *ship])
        for ln in range(1, SO_LINES + 1):
            key = random.choice(keys)
            qty = min(random.randint(1, 20), remaining[key])
            if qty <= 0:
                continue
            remaining[key] -= qty
            sol, pkl, shl = audit(ts), audit(ts), audit(ts)
            lines.append([so[1], ln, key[0], ea, qty, qty, None, None, None, None, None, None, None, *sol])
            lines.append([pick[1], ln, key[0], ea, qty, qty, key[2], key[3], key[1], docks["OUT01"], sol[1], ts, admin, *pkl])
            lines.append([ship[1], ln, key[0], ea, qty, qty, key[2], key[3], key[1], None, sol[1], None, None, *shl])
            # Simplified history: shipments leave directly from bins (no in-warehouse pick transfer entries)
            ledger.append([key[0], key[1], key[2], key[3], -qty, "SHIP_OUT", shl[1], ts, *audit(ts)])
    if d % 10 == 0 or d == 1:
        print(f"  written up to {day}", flush=True)
        flush_history()
flush_history()

# ---------------------------------------------------------------- Balance = ledger sum
print("Stock balances")
cur.execute(f"""
INSERT INTO stock_balance (item_id, location_id, batch_no, expiry_date, qty_on_hand, qty_allocated, {AUDIT_COLS})
SELECT item_id, location_id, batch_no, expiry_date, SUM(qty_change), 0, ?, NEWID(), SYSUTCDATETIME(), ?, SYSUTCDATETIME(), ?, 0, 0
FROM stock_ledger WHERE tenant_id = ?
GROUP BY item_id, location_id, batch_no, expiry_date
HAVING SUM(qty_change) <> 0
""", tenant, admin, admin, tenant)
conn.commit()
for t in ["item", "location", "business_partner", "document_header", "document_line", "stock_ledger", "stock_balance"]:
    print(f"  {t:18} {cur.execute(f'SELECT COUNT_BIG(*) FROM {t}').fetchval():>12,}")
print("Updating statistics")
cur.execute("EXEC sp_updatestats")
conn.commit()
if args.export:
    q = lambda sql: [str(r[0]) for r in cur.execute(sql).fetchall()]
    data = {
        "ea": ea,
        "stocked": [{"item_id": str(a), "location_id": str(b)} for a, b in cur.execute(
            "SELECT TOP 5000 b.item_id, b.location_id FROM stock_balance b JOIN location l ON l.id = b.location_id "
            "WHERE l.is_pickable = 1 AND b.qty_on_hand >= 200 AND (b.expiry_date IS NULL OR b.expiry_date > DATEADD(day, 30, GETDATE())) "
            "ORDER BY NEWID()").fetchall()],
        "plain_items": q("SELECT TOP 5000 id FROM item WHERE is_batch_managed = 0 ORDER BY NEWID()"),
        "suppliers": q("SELECT TOP 200 id FROM business_partner WHERE partner_type = 'supplier' ORDER BY NEWID()"),
        "customers": q("SELECT TOP 500 id FROM business_partner WHERE partner_type = 'customer' ORDER BY NEWID()"),
        "dock_in": docks["IN01"],
        "dock_out": [docks[f"OUT{i:02d}"] for i in range(2, 11)],
    }
    with open(args.export, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"Load-test IDs written to {args.export}")
print(f"Done in {time.time() - started:.0f}s")
