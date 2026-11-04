"""Business-peak load test (runs directly on the host so the Docker Desktop port-forwarding proxy is not the bottleneck).
Scenarios match the peak profile in load.js:
  Outbound 25 orders per minute (create -> confirm -> allocate -> confirm picks -> post pick -> create shipment -> post shipment), about 1500 orders/hour
  Receiving 4 orders per minute (create PO -> confirm -> receive -> post)
  PDA 25 users, one scan every 2-4 s (item stock / location stock lookup)
  Office 5 users, viewing lists, dashboard and reports every 2-5 s
Usage: python peak_load.py <data.json> [minutes, default 5] [backend address such as http://10.0.0.8:80 or a port number, default 8001]
Adjust OUTBOUND_PER_MINUTE / RECEIVING_PER_MINUTE below to the customer's real peak arrival rates.
"""

import http.client
import json
import random
import statistics
import sys
import threading
import time
import urllib.parse
from collections import defaultdict

DATA = json.load(open(sys.argv[1]))
MINUTES = float(sys.argv[2]) if len(sys.argv) > 2 else 5
TARGET = sys.argv[3] if len(sys.argv) > 3 else "8001"
if TARGET.isdigit():
    HOST, PORT = "127.0.0.1", int(TARGET)
else:
    _url = urllib.parse.urlparse(TARGET)
    HOST, PORT = _url.hostname, _url.port or 80
PREFIX = "/api/v1"
OUTBOUND_PER_MINUTE = 25
RECEIVING_PER_MINUTE = 4
END = time.time() + MINUTES * 60

lat = defaultdict(list)  # name -> [ms]
errors = defaultdict(int)
lock = threading.Lock()


def login():
    c = http.client.HTTPConnection(HOST, PORT, timeout=60)
    c.request("POST", PREFIX + "/auth/login", urllib.parse.urlencode({"username": "admin", "password": "Admin@123"}),
              {"Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(c.getresponse().read())["access_token"]


TOKEN = login()


class Client:
    """One keep-alive connection per virtual user (reused like a browser/PDA)"""

    def __init__(self):
        self.conn = http.client.HTTPConnection(HOST, PORT, timeout=60)

    def call(self, method, path, body=None, name=None, kind="read"):
        headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
        data = json.dumps(body) if body is not None else None
        start = time.perf_counter()
        try:
            self.conn.request(method, PREFIX + path, data, headers)
            res = self.conn.getresponse()
            raw = res.read()
            ok = 200 <= res.status < 300
        except Exception:  # noqa: BLE001 - dropped connection etc.: count as failure and reconnect
            self.conn.close()
            self.conn = http.client.HTTPConnection(HOST, PORT, timeout=60)
            raw, ok = b"", False
        ms = (time.perf_counter() - start) * 1000
        with lock:
            lat[(kind, name)].append(ms)
            if not ok:
                errors[name] += 1
        return json.loads(raw) if ok and raw else None


def outbound(c: Client):
    lines = [{"item_id": random.choice(DATA["stocked"])["item_id"], "uom_id": DATA["ea"], "qty": random.randint(1, 3)} for _ in range(3)]
    so = c.call("POST", "/sales-orders", {"partner_id": random.choice(DATA["customers"]), "lines": lines}, "so_create", "write")
    if not so:
        return
    c.call("POST", f"/sales-orders/{so['id']}/confirm", None, "so_confirm", "write")
    alloc = c.call("POST", f"/sales-orders/{so['id']}/allocate", {"staging_location_id": random.choice(DATA["dock_out"])}, "so_allocate", "write")
    if not alloc:
        return
    c.call("POST", f"/picks/{alloc['pick']['id']}/confirm-all", None, "pick_confirm_all", "write")
    if not c.call("POST", f"/picks/{alloc['pick']['id']}/post", None, "pick_post", "write"):
        return
    ship = c.call("POST", "/shipments", {"so_id": so["id"]}, "ship_create", "write")
    if ship:
        c.call("POST", f"/shipments/{ship['id']}/post", None, "ship_post", "write")


def receiving(c: Client):
    lines = [{"item_id": random.choice(DATA["plain_items"]), "uom_id": DATA["ea"], "qty": random.randint(20, 100)} for _ in range(3)]
    po = c.call("POST", "/purchase-orders", {"partner_id": random.choice(DATA["suppliers"]), "lines": lines}, "po_create", "write")
    if not po:
        return
    c.call("POST", f"/purchase-orders/{po['id']}/confirm", None, "po_confirm", "write")
    grn = c.call("POST", "/grns", {"po_id": po["id"], "location_id": DATA["dock_in"],
                                   "lines": [{"po_line_id": l["id"], "qty": float(l["qty_planned"])} for l in po["lines"]]}, "grn_create", "write")
    if grn:
        c.call("POST", f"/grns/{grn['id']}/post", None, "grn_post", "write")


def arrival(fn, per_minute):
    """Fixed arrival rate: start orders on schedule without waiting for the previous one (one thread per order, like many people working at once)"""
    interval = 60 / per_minute
    nxt = time.time()
    while time.time() < END:
        threading.Thread(target=lambda: fn(Client()), daemon=True).start()
        nxt += interval
        time.sleep(max(0, nxt - time.time()))


def pda():
    c = Client()
    while time.time() < END:
        s = random.choice(DATA["stocked"])
        if random.random() < 0.5:
            c.call("GET", f"/stock/balances?item_id={s['item_id']}", None, "scan_item_stock", "scan")
        else:
            c.call("GET", f"/stock/balances?location_id={s['location_id']}", None, "scan_location_stock", "scan")
        time.sleep(2 + random.random() * 2)


def office():
    c = Client()
    while time.time() < END:
        r = random.random()
        if r < 0.25:
            c.call("GET", "/sales-orders?limit=50", None, "so_list")
        elif r < 0.45:
            c.call("GET", "/reports/dashboard", None, "dashboard")
        elif r < 0.6:
            c.call("GET", "/sales-orders/shortages", None, "shortages")
        elif r < 0.75:
            c.call("GET", f"/stock/ledger?item_id={random.choice(DATA['stocked'])['item_id']}&limit=100", None, "ledger_item")
        elif r < 0.85:
            c.call("GET", "/reports/turnover", None, "turnover_30d", "report")
        else:
            c.call("GET", f"/items?keyword=P{random.randint(1, 499):03d}&limit=50", None, "item_search")
        time.sleep(2 + random.random() * 3)


threads = [threading.Thread(target=arrival, args=(outbound, OUTBOUND_PER_MINUTE)),
           threading.Thread(target=arrival, args=(receiving, RECEIVING_PER_MINUTE))]
threads += [threading.Thread(target=pda) for _ in range(25)] + [threading.Thread(target=office) for _ in range(5)]
started = time.time()
for t in threads:
    t.start()
for t in threads:
    t.join()
time.sleep(5)  # Let the last started orders finish

def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p))]

total = sum(len(v) for v in lat.values())
fails = sum(errors.values())
print(f"Duration {MINUTES} min, requests {total}, failures {fails} ({fails / max(total, 1):.2%}), outbound orders completed {len(lat[('write', 'ship_post')])}")
print(f"{'Kind':6}{'Endpoint':22}{'Count':>6}{'p50':>9}{'p95':>9}{'p99':>9}{'max':>9}")
for kind in ("scan", "write", "read", "report"):
    rows = sorted((k, v) for k, v in lat.items() if k[0] == kind)
    allv = [x for _, v in rows for x in v]
    for (k, name), v in rows:
        print(f"{kind:6}{name:22}{len(v):>6}{statistics.median(v):>8.0f}ms{pct(v, .95):>7.0f}ms{pct(v, .99):>7.0f}ms{max(v):>7.0f}ms")
    if allv:
        print(f"{kind:6}{'== total':22}{len(allv):>6}{statistics.median(allv):>8.0f}ms{pct(allv, .95):>7.0f}ms{pct(allv, .99):>7.0f}ms{max(allv):>7.0f}ms")
for name, n in errors.items():
    print("failed", name, n)
