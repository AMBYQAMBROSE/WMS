// k6 load test: docker run --rm -v <perf dir>:/perf grafana/k6 run /perf/load.js
import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

const BASE = __ENV.BASE || "http://host.docker.internal:8001/api/v1";
const DURATION = __ENV.DURATION || "5m";
const data = JSON.parse(open(__ENV.DATA || "/perf/data.json"));
const stocked = new SharedArray("stocked", () => data.stocked); // [{item_id, location_id}]
const plain = new SharedArray("plain", () => data.plain_items); // non-batch items, used for receiving

// PROFILE=stress: saturate with no pauses to find peak throughput; PROFILE=peak: fixed arrival rate at business peak (default)
const PROFILE = __ENV.PROFILE || "peak";
// Business peak assumption: 5000 orders/day on average, peak x3 -> 1500 orders/hour (25 per minute), 4 receipts per minute
const peak = {
  receiving: { executor: "constant-arrival-rate", rate: 4, timeUnit: "1m", duration: DURATION, preAllocatedVUs: 5, maxVUs: 20, exec: "receiving" },
  outbound: { executor: "constant-arrival-rate", rate: 25, timeUnit: "1m", duration: DURATION, preAllocatedVUs: 10, maxVUs: 50, exec: "outbound" },
  pda: { executor: "constant-vus", vus: 25, duration: DURATION, exec: "pda" },
  office: { executor: "constant-vus", vus: 5, duration: DURATION, exec: "office" },
};
const stress = {
  receiving: { executor: "constant-vus", vus: 5, duration: DURATION, exec: "receiving" },
  outbound: { executor: "constant-vus", vus: 15, duration: DURATION, exec: "outbound" },
  pda: { executor: "constant-vus", vus: 25, duration: DURATION, exec: "pda" },
  office: { executor: "constant-vus", vus: 5, duration: DURATION, exec: "office" },
};

// ONLY=pda,office runs only the given scenarios (to isolate interference)
const chosen = PROFILE === "stress" ? stress : peak;
const only = __ENV.ONLY ? __ENV.ONLY.split(",") : Object.keys(chosen);

export const options = {
  scenarios: Object.fromEntries(Object.entries(chosen).filter(([k]) => only.includes(k))),
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{kind:read}": ["p(95)<500"],
    "http_req_duration{kind:scan}": ["p(95)<500"],
    "http_req_duration{kind:write}": ["p(95)<1500"],
    // List each endpoint's latency separately (thresholds only make k6 print per-endpoint stats)
    "http_req_duration{name:po_create}": ["p(95)<60000"],
    "http_req_duration{name:po_confirm}": ["p(95)<60000"],
    "http_req_duration{name:grn_create}": ["p(95)<60000"],
    "http_req_duration{name:grn_post}": ["p(95)<60000"],
    "http_req_duration{name:so_create}": ["p(95)<60000"],
    "http_req_duration{name:so_confirm}": ["p(95)<60000"],
    "http_req_duration{name:so_allocate}": ["p(95)<60000"],
    "http_req_duration{name:pick_confirm_all}": ["p(95)<60000"],
    "http_req_duration{name:pick_post}": ["p(95)<60000"],
    "http_req_duration{name:ship_create}": ["p(95)<60000"],
    "http_req_duration{name:ship_post}": ["p(95)<60000"],
    "http_req_duration{name:scan_item_stock}": ["p(95)<60000"],
    "http_req_duration{name:scan_location_stock}": ["p(95)<60000"],
    "http_req_duration{name:so_list}": ["p(95)<60000"],
    "http_req_duration{name:dashboard}": ["p(95)<60000"],
    "http_req_duration{name:shortages}": ["p(95)<60000"],
    "http_req_duration{name:ledger_item}": ["p(95)<60000"],
    "http_req_duration{name:turnover_30d}": ["p(95)<60000"],
    "http_req_duration{name:item_list}": ["p(95)<60000"],
  },
  summaryTrendStats: ["avg", "med", "p(95)", "p(99)", "max"],
};

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

export function setup() {
  const res = http.post(`${BASE}/auth/login`, { username: "admin", password: "Admin@123" });
  return { token: res.json("access_token") };
}

function api(ctx, method, path, body, name, kind) {
  const params = {
    headers: { Authorization: `Bearer ${ctx.token}`, "Content-Type": "application/json" },
    tags: { name, kind },
    timeout: "60s",
  };
  const res = http.request(method, BASE + path, body === undefined ? null : JSON.stringify(body), params);
  const ok = check(res, { [`${name} ok`]: (r) => r.status >= 200 && r.status < 300 });
  if (!ok && __ENV.VERBOSE) console.error(`${name} ${res.status} ${res.body && res.body.slice(0, 200)}`);
  return ok ? (res.body ? res.json() : null) : null;
}

export function receiving(ctx) {
  const lines = [0, 1, 2].map(() => ({ item_id: pick(plain), uom_id: data.ea, qty: 20 + Math.floor(Math.random() * 80) }));
  const po = api(ctx, "POST", "/purchase-orders", { partner_id: pick(data.suppliers), lines }, "po_create", "write");
  if (!po) return;
  api(ctx, "POST", `/purchase-orders/${po.id}/confirm`, undefined, "po_confirm", "write");
  const grn = api(ctx, "POST", "/grns", {
    po_id: po.id,
    location_id: data.dock_in,
    lines: po.lines.map((l) => ({ po_line_id: l.id, qty: Number(l.qty_planned) })),
  }, "grn_create", "write");
  if (grn) api(ctx, "POST", `/grns/${grn.id}/post`, undefined, "grn_post", "write");
  sleep(1);
}

export function outbound(ctx) {
  const lines = [0, 1, 2].map(() => ({ item_id: pick(stocked).item_id, uom_id: data.ea, qty: 1 + Math.floor(Math.random() * 3) }));
  const so = api(ctx, "POST", "/sales-orders", { partner_id: pick(data.customers), lines }, "so_create", "write");
  if (!so) return;
  api(ctx, "POST", `/sales-orders/${so.id}/confirm`, undefined, "so_confirm", "write");
  const alloc = api(ctx, "POST", `/sales-orders/${so.id}/allocate`, { staging_location_id: pick(data.dock_out) }, "so_allocate", "write");
  if (!alloc) return;
  api(ctx, "POST", `/picks/${alloc.pick.id}/confirm-all`, undefined, "pick_confirm_all", "write");
  if (!api(ctx, "POST", `/picks/${alloc.pick.id}/post`, undefined, "pick_post", "write")) return;
  const ship = api(ctx, "POST", "/shipments", { so_id: so.id }, "ship_create", "write");
  if (ship) api(ctx, "POST", `/shipments/${ship.id}/post`, undefined, "ship_post", "write");
  sleep(1);
}

export function pda(ctx) {
  const s = pick(stocked);
  if (Math.random() < 0.5) api(ctx, "GET", `/stock/balances?item_id=${s.item_id}`, undefined, "scan_item_stock", "scan");
  else api(ctx, "GET", `/stock/balances?location_id=${s.location_id}`, undefined, "scan_location_stock", "scan");
  sleep(PROFILE === "stress" ? 0.5 + Math.random() : 2 + Math.random() * 2);
}

export function office(ctx) {
  const r = Math.random();
  if (r < 0.25) api(ctx, "GET", "/sales-orders?limit=50", undefined, "so_list", "read");
  else if (r < 0.45) api(ctx, "GET", "/reports/dashboard", undefined, "dashboard", "read");
  else if (r < 0.6) api(ctx, "GET", "/sales-orders/shortages", undefined, "shortages", "read");
  else if (r < 0.75) api(ctx, "GET", `/stock/ledger?item_id=${pick(stocked).item_id}&limit=100`, undefined, "ledger_item", "read");
  else if (r < 0.85) api(ctx, "GET", "/reports/turnover", undefined, "turnover_30d", "report");
  else api(ctx, "GET", "/items?limit=50", undefined, "item_list", "read");
  sleep(2 + Math.random() * 3);
}
