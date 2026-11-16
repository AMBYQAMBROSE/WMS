import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";

import {
  AimOutlined,
  CaretRightOutlined,
  LockOutlined,
  PauseOutlined,
  SwapOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, DatePicker, Descriptions, Drawer, Empty, Segmented, Select, Skeleton, Slider, Table, Tooltip, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { Link, useSearchParams } from "react-router";

import { apiClient } from "@/api/client";
import { useLiveStore } from "@/api/live";
import { useCan } from "@/api/me";
import type { MapActivity, MapActivityPage, MapBinDetail, MapNode, StockBalance, WarehouseMap } from "@/api/types";
import { ItemSelect } from "@/components/selects";
import { ErrorState, PageHeader, Pill, formatQty } from "@/components/ui";
import { DOC_PATHS, DOC_TYPE_LABELS, LOCATION_TYPE_LABELS, MOVEMENT_TYPE_LABELS } from "@/constants/labels";
import { useUiStore } from "@/stores/uiStore";

/* ------------------------------------------------------------------ colours
 * Each metric is one ordinal ramp (or a few named states), with separate steps for dark mode so the emptiest step
 * still separates from the card. The fill ramp is the dashboard heatmap's validated blue; pick heat uses orange so
 * the two never read as the same measure. */
type Mode = "light" | "dark";
type Metric = "fill" | "picks" | "expiry" | "status";
const RAMPS: Record<"fill" | "picks", Record<Mode, string[]>> = {
  fill: { light: ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"], dark: ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"] },
  picks: { light: ["#f6c7a6", "#f19a63", "#e26a2c", "#b44a17", "#7a300c"], dark: ["#6a2c10", "#9a4119", "#d0602c", "#ee8653", "#f7b892"] },
};
const STATES: Record<Mode, Record<string, string>> = {
  light: { expired: "#c62f2f", soon: "#e8930c", later: "#e9cf62", fine: "#4caf6a", locked: "#5b6474", counting: "#7c5cd6", recalled: "#c62f2f", full: "#e8930c", stock: "#2a78d6" },
  dark: { expired: "#e5534b", soon: "#f0a531", later: "#c9b04a", fine: "#4fae6d", locked: "#8b93a3", counting: "#9b82f0", recalled: "#e5534b", full: "#f0a531", stock: "#3987e5" },
};
const LEGENDS: Record<Metric, { label: string; title: string; key: string }[]> = {
  fill: [
    { key: "0", label: "≤20%", title: "Holds stock, up to 20% of capacity" },
    { key: "1", label: "40%", title: "" },
    { key: "2", label: "60%", title: "" },
    { key: "3", label: "80%", title: "" },
    { key: "4", label: "Full", title: "80% of capacity or more" },
  ],
  picks: [
    { key: "0", label: "Few", title: "" },
    { key: "1", label: "", title: "" },
    { key: "2", label: "", title: "" },
    { key: "3", label: "", title: "" },
    { key: "4", label: "Busiest", title: "" },
  ],
  expiry: [
    { key: "expired", label: "Expired", title: "" },
    { key: "soon", label: "≤ 30 days", title: "" },
    { key: "later", label: "≤ 90 days", title: "" },
    { key: "fine", label: "Later", title: "" },
  ],
  status: [
    { key: "stock", label: "Holds stock", title: "" },
    { key: "full", label: "All allocated", title: "" },
    { key: "counting", label: "Being counted", title: "" },
    { key: "locked", label: "Locked", title: "" },
    { key: "recalled", label: "Recalled batch", title: "" },
  ],
};
const METRIC_HINT: Record<Metric, string> = {
  fill: "Quantity against the bin's capacity. Bins without a capacity show as half full when they hold stock.",
  picks: "Pick lines taken from each bin in the last 30 days. Busy bins far from the dock are candidates to move closer.",
  expiry: "The earliest expiry date of the stock in each bin.",
  status: "Locks, counts in progress, recalled batches and stock that is fully allocated.",
};

const isLeaf = (n: MapNode) => n.location_type === "BIN" || n.location_type === "DOCK";
const daysTo = (d: string) => dayjs(d).startOf("day").diff(dayjs().startOf("day"), "day");

function colour(n: MapNode, metric: Metric, mode: Mode, maxPicks: number): string | undefined {
  const s = STATES[mode];
  if (metric === "status") {
    if (n.has_recalled) return s.recalled;
    if (n.is_counting) return s.counting;
    if (n.is_locked) return s.locked;
    if (n.qty_on_hand <= 0) return undefined;
    return n.qty_allocated >= n.qty_on_hand ? s.full : s.stock;
  }
  if (metric === "picks") {
    if (!n.picks || !maxPicks) return undefined;
    // Square root: a few very busy bins should not flatten everything else into the lowest step
    return RAMPS.picks[mode][Math.min(4, Math.floor(Math.sqrt(n.picks / maxPicks) * 5))];
  }
  if (n.qty_on_hand <= 0) return undefined;
  if (metric === "expiry") {
    if (!n.nearest_expiry) return undefined;
    const days = daysTo(n.nearest_expiry);
    return days < 0 ? s.expired : days <= 30 ? s.soon : days <= 90 ? s.later : s.fine;
  }
  const share = n.capacity_qty ? n.qty_on_hand / n.capacity_qty : 0.5;
  return RAMPS.fill[mode][Math.max(0, Math.min(4, Math.ceil(share * 5) - 1))];
}

function legendSwatch(metric: Metric, key: string, mode: Mode) {
  return metric === "fill" || metric === "picks" ? RAMPS[metric][mode][Number(key)] : STATES[mode][key];
}

/* ------------------------------------------------------------------ activity */

type Tone = "in" | "out" | "scan" | "internal";
const IN_TYPES = new Set(["RECEIVE", "RETURN_IN", "ADJUST_IN", "COUNT_GAIN", "REPACK_IN"]);
const OUT_TYPES = new Set(["SHIP_OUT", "RETURN_OUT", "ADJUST_OUT", "COUNT_LOSS", "REPACK_OUT"]);
const toneOf = (e: MapActivity): Tone =>
  e.kind === "SCAN" ? "scan" : IN_TYPES.has(e.movement_type ?? "") ? "in" : OUT_TYPES.has(e.movement_type ?? "") ? "out" : "internal";
const SCAN_VERB: Record<string, string> = { PICK: "picked", PUTAWAY: "put away", COUNT: "counted" };
const eventKey = (e: MapActivity) => `${e.at}|${e.kind}|${e.location_id}|${e.document_id ?? ""}|${e.sku_code}|${e.qty ?? ""}`;
const localTime = (at: string) => dayjs(at + "Z");

function describe(e: MapActivity) {
  if (e.kind === "SCAN") return `${e.user_name ?? "Someone"} ${SCAN_VERB[e.doc_type ?? ""] ?? "confirmed"} ${e.sku_code}${e.qty != null ? ` × ${formatQty(e.qty)}` : ""}`;
  const label = MOVEMENT_TYPE_LABELS[e.movement_type ?? ""] ?? e.movement_type;
  return `${label}: ${e.sku_code} ${e.qty != null && e.qty > 0 ? "+" : ""}${formatQty(e.qty)}`;
}

const initials = (name?: string | null) =>
  (name ?? "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "?";

/* ------------------------------------------------------------------ layout */

interface Tree {
  root?: MapNode;
  children: Map<string, MapNode[]>;
  byId: Map<string, MapNode>;
  leafCount: number;
}

function buildTree(nodes: MapNode[]): Tree {
  const children = new Map<string, MapNode[]>();
  const byId = new Map<string, MapNode>();
  let root: MapNode | undefined;
  let leafCount = 0;
  for (const n of nodes) {
    byId.set(n.id, n);
    if (isLeaf(n)) leafCount += 1;
    if (!n.parent_id) root = n;
    else {
      const list = children.get(n.parent_id) ?? [];
      list.push(n);
      children.set(n.parent_id, list);
    }
  }
  return { root, children, byId, leafCount };
}

interface CellState {
  colour?: string;
  dim: boolean;
  flash?: { id: number; tone: Tone };
  people?: string[];
  replayCount?: number;
}

function Cell({ node, state, large, onOpen }: { node: MapNode; state: CellState; large: boolean; onOpen: (id: string) => void }) {
  const classes = ["wms-map-cell"];
  if (large) classes.push("is-large");
  if (!state.colour) classes.push("is-empty");
  if (state.dim) classes.push("is-dim");
  if (node.is_counting) classes.push("is-counting");
  if (node.has_recalled) classes.push("is-recalled");
  if (node.location_type === "DOCK") classes.push("is-dock");
  return (
    <button
      type="button"
      className={classes.join(" ")}
      data-id={node.id}
      style={state.colour ? { background: state.colour } : undefined}
      onClick={() => onOpen(node.id)}
      aria-label={`${LOCATION_TYPE_LABELS[node.location_type] ?? node.location_type} ${node.code}: ${formatQty(node.qty_on_hand)} on hand${node.is_locked ? ", locked" : ""}${node.has_recalled ? ", holds a recalled batch" : ""}`}
    >
      {large && <span className="wms-map-cell-code">{node.code}</span>}
      {node.is_locked && <LockOutlined className="wms-map-cell-icon" aria-hidden />}
      {state.flash && <span key={state.flash.id} className={`wms-map-ping tone-${state.flash.tone}`} aria-hidden />}
      {state.people && state.people.length > 0 && (
        <span className="wms-map-person" aria-hidden>
          {initials(state.people[0])}
          {state.people.length > 1 && <sup>+{state.people.length - 1}</sup>}
        </span>
      )}
    </button>
  );
}

function Group({ node, tree, cellState, large, onOpen, depth }: {
  node: MapNode;
  tree: Tree;
  cellState: (n: MapNode) => CellState;
  large: boolean;
  onOpen: (id: string) => void;
  depth: number;
}) {
  const kids = tree.children.get(node.id) ?? [];
  const leaves = kids.filter(isLeaf);
  const groups = kids.filter((k) => !isLeaf(k));
  if (!leaves.length && !groups.length) return null;
  const type = node.location_type.toLowerCase();
  return (
    <section className={`wms-map-group is-${type}`} data-depth={depth}>
      <header className="wms-map-group-label">
        <span className="wms-mono">{node.code}</span>
        {node.name && node.name !== node.code && <span className="wms-map-group-name">{node.name}</span>}
      </header>
      <div className="wms-map-group-body">
        {leaves.length > 0 && (
          <div className="wms-map-cells">
            {leaves.map((leaf) => (
              <Cell key={leaf.id} node={leaf} state={cellState(leaf)} large={large} onOpen={onOpen} />
            ))}
          </div>
        )}
        {groups.map((g) => (
          <Group key={g.id} node={g} tree={tree} cellState={cellState} large={large} onOpen={onOpen} depth={depth + 1} />
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ hover card */

function HoverCard({ node, at, people }: { node: MapNode; at: { x: number; y: number }; people?: string[] }) {
  const free = node.qty_on_hand - node.qty_allocated;
  return (
    <div className="wms-map-hover" style={{ left: at.x + 14, top: at.y + 14 }} role="tooltip">
      <div style={{ fontWeight: 600 }}>
        <span className="wms-mono">{node.code}</span> · {LOCATION_TYPE_LABELS[node.location_type] ?? node.location_type}
      </div>
      {node.qty_on_hand > 0 ? (
        <>
          <div>
            {formatQty(node.qty_on_hand)} on hand · {formatQty(free)} free
            {node.capacity_qty ? ` · ${Math.round((node.qty_on_hand / node.capacity_qty) * 100)}% of capacity` : ""}
          </div>
          <div>{node.sku_count} SKU{node.sku_count === 1 ? "" : "s"}{node.nearest_expiry ? ` · earliest expiry ${node.nearest_expiry}` : ""}</div>
        </>
      ) : (
        <div>Empty</div>
      )}
      <div>{node.picks} pick{node.picks === 1 ? "" : "s"} in 30 days</div>
      {node.is_locked && <div>Locked</div>}
      {node.is_counting && <div>Being counted: movements paused</div>}
      {node.has_recalled && <div style={{ color: "var(--wms-tone-red-fg)" }}>Holds a recalled batch</div>}
      {people && people.length > 0 && <div>Working here: {people.join(", ")}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ bin drawer */

function BinDrawer({ id, onClose }: { id?: string; onClose: () => void }) {
  const can = useCan();
  const { data, isLoading } = useQuery({
    queryKey: ["stock", "map-bin", id],
    queryFn: async () => (await apiClient.get<MapBinDetail>(`/stock/map/locations/${id}`)).data,
    enabled: !!id,
  });
  return (
    <Drawer
      open={!!id}
      onClose={onClose}
      size="large"
      title={data ? <span><span className="wms-mono">{data.location.code}</span> · {data.location.name}</span> : "Location"}
      extra={
        data && can("move.create") && data.stock.length > 0 ? (
          <Link to={`/moves/new?from=${data.location.id}`}>
            <Button icon={<SwapOutlined />}>Move stock</Button>
          </Link>
        ) : null
      }
    >
      {isLoading || !data ? (
        <Skeleton active />
      ) : (
        <>
          <Descriptions size="small" column={1} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="Path"><span className="wms-mono">{data.path}</span></Descriptions.Item>
            <Descriptions.Item label="Type">{LOCATION_TYPE_LABELS[data.location.location_type] ?? data.location.location_type}</Descriptions.Item>
            <Descriptions.Item label="Status">
              <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap" }}>
                {data.is_locked ? <Pill tone="slate" icon={<LockOutlined />}>Locked</Pill> : <Pill tone="green">Open</Pill>}
                {data.counting_doc && (
                  <Link to={`/cycle-counts/${data.counting_doc.id}`}><Pill tone="violet">Counting · {data.counting_doc.doc_no}</Pill></Link>
                )}
              </span>
            </Descriptions.Item>
            {data.capacity_qty != null && <Descriptions.Item label="Capacity">{formatQty(data.capacity_qty)}</Descriptions.Item>}
          </Descriptions>
          <Typography.Title level={5}>Stock</Typography.Title>
          <Table
            rowKey={(r) => `${r.item.id}|${r.batch_no}|${r.expiry_date}`}
            size="small"
            pagination={false}
            dataSource={data.stock}
            locale={{ emptyText: "Nothing here" }}
            scroll={{ x: "max-content" }}
            style={{ marginBottom: 20 }}
            columns={[
              { title: "SKU", render: (_, r) => <span className="wms-mono">{r.item.sku_code}</span> },
              {
                title: "Batch",
                render: (_, r) =>
                  r.batch_no ? (
                    <Link className="wms-mono" to={`/trace?item=${r.item.id}&batch=${encodeURIComponent(r.batch_no)}`}>{r.batch_no}</Link>
                  ) : (
                    <span className="wms-empty-value">—</span>
                  ),
              },
              { title: "Expiry", dataIndex: "expiry_date", render: (v: string | null) => v ?? <span className="wms-empty-value">—</span> },
              { title: "On hand", align: "right", render: (_, r) => formatQty(r.qty_on_hand) },
              { title: "Allocated", align: "right", render: (_, r) => (r.qty_allocated ? formatQty(r.qty_allocated) : <span className="wms-empty-value">—</span>) },
              {
                title: "",
                render: (_, r) =>
                  r.recall ? (
                    <Link to={`/recalls/${r.recall.id}`}><Pill tone="red" icon={<WarningOutlined />}>Recall {r.recall.doc_no}</Pill></Link>
                  ) : null,
              },
            ]}
          />
          <Typography.Title level={5}>Last 2 days here</Typography.Title>
          {data.recent.length ? (
            <div className="wms-map-feed">
              {data.recent.map((e) => <FeedRow key={eventKey(e)} event={e} />)}
            </div>
          ) : (
            <Typography.Text type="secondary">Nothing happened here in the last 2 days.</Typography.Text>
          )}
        </>
      )}
    </Drawer>
  );
}

function FeedRow({ event: e, code }: { event: MapActivity; code?: string }) {
  const tone = toneOf(e);
  const path = e.doc_type ? DOC_PATHS[e.doc_type] : undefined;
  return (
    <div className="wms-map-feed-row">
      <span className="wms-num wms-map-feed-time">{localTime(e.at).format("HH:mm:ss")}</span>
      <span className={`wms-map-feed-dot tone-${tone}`} aria-hidden />
      <span className="wms-map-feed-text">
        {describe(e)}
        {code && <> at <span className="wms-mono">{code}</span></>}
        {e.doc_no && path && e.document_id && (
          <>
            {" · "}
            <Link className="wms-mono" to={`/${path}/${e.document_id}`} title={DOC_TYPE_LABELS[e.doc_type ?? ""]}>{e.doc_no}</Link>
          </>
        )}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ the page */

const SPEEDS = [
  { label: "1 min/s", value: 60 },
  { label: "5 min/s", value: 300 },
  { label: "15 min/s", value: 900 },
];
const FLASH_MS = 1600;
const PRESENCE_MINUTES = 15;

export default function WarehouseMapPage() {
  const mode = useUiStore((s) => s.mode);
  const liveStatus = useLiveStore((s) => s.status);
  // ?warehouse=<id> opens that warehouse (a link to one site of several); otherwise the first by code
  const [params, setParams] = useSearchParams();
  const warehouseId = params.get("warehouse") ?? undefined;
  const setWarehouseId = (id: string) => setParams({ warehouse: id }, { replace: true });
  const [metric, setMetric] = useState<Metric>("fill");
  const [view, setView] = useState<"live" | "replay">("live");
  const [openId, setOpenId] = useState<string>();
  const [findItem, setFindItem] = useState<string>();
  const [hover, setHover] = useState<{ id: string; x: number; y: number }>();

  const map = useQuery({
    queryKey: ["stock", "map", warehouseId ?? null],
    queryFn: async () => (await apiClient.get<WarehouseMap>("/stock/map", { params: { warehouse_id: warehouseId } })).data,
    placeholderData: (previous) => previous,
  });
  const whId = map.data?.warehouse?.id;
  const tree = useMemo(() => buildTree(map.data?.nodes ?? []), [map.data]);
  const maxPicks = useMemo(() => Math.max(0, ...(map.data?.nodes ?? []).map((n) => n.picks)), [map.data]);

  // "Where is this item?": highlight the bins holding it, dim the rest
  const found = useQuery({
    queryKey: ["stock", "balances", "map-find", findItem],
    queryFn: async () => (await apiClient.get<StockBalance[]>("/stock/balances", { params: { item_id: findItem, limit: 500 } })).data,
    enabled: !!findItem,
  });
  const highlight = useMemo(() => (findItem && found.data ? new Set(found.data.map((b) => b.location.id)) : undefined), [findItem, found.data]);

  /* ---------- live: flash bins as things happen, and show who is where ---------- */
  const [flashes, setFlashes] = useState<Map<string, { id: number; tone: Tone; until: number }>>(new Map());
  const flashSeq = useRef(0);
  const flash = (events: MapActivity[]) => {
    if (!events.length) return;
    setFlashes((prev) => {
      const next = new Map(prev);
      const until = Date.now() + FLASH_MS;
      for (const e of events) next.set(e.location_id, { id: ++flashSeq.current, tone: toneOf(e), until });
      return next;
    });
  };
  useEffect(() => {
    if (!flashes.size) return;
    const timer = setTimeout(() => {
      const now = Date.now();
      setFlashes((prev) => new Map([...prev].filter(([, f]) => f.until > now)));
    }, FLASH_MS);
    return () => clearTimeout(timer);
  }, [flashes]);

  const activity = useQuery({
    queryKey: ["stock", "map-activity", whId],
    queryFn: async () =>
      (
        await apiClient.get<MapActivityPage>("/stock/map/activity", {
          params: { warehouse_id: whId, since: dayjs().subtract(PRESENCE_MINUTES, "minute").toISOString().slice(0, 19) },
        })
      ).data,
    enabled: !!whId && view === "live",
    // Live updates refetch it on every change; the interval only covers a stream that is reconnecting
    refetchInterval: liveStatus === "live" ? 60_000 : 10_000,
  });
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    seen.current = null;
  }, [whId]);
  useEffect(() => {
    const events = activity.data?.events;
    if (!events) return;
    const keys = new Set(events.map(eventKey));
    // The first load is history, not news: only what arrives after it flashes
    if (seen.current) flash(events.filter((e) => !seen.current!.has(eventKey(e))));
    seen.current = keys;
  }, [activity.data]);

  const people = useMemo(() => {
    const latest = new Map<string, MapActivity>();
    for (const e of activity.data?.events ?? []) if (e.user_id) latest.set(e.user_id, e);
    const byLocation = new Map<string, string[]>();
    for (const e of latest.values()) {
      const list = byLocation.get(e.location_id) ?? [];
      list.push(e.user_name ?? "?");
      byLocation.set(e.location_id, list);
    }
    return byLocation;
  }, [activity.data]);

  /* ---------- replay: play a day back ---------- */
  const [day, setDay] = useState<Dayjs>(dayjs().startOf("day"));
  const [clock, setClock] = useState(0); // minutes since the start of the day
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(300);
  const replay = useQuery({
    queryKey: ["stock", "map-replay", whId, day.format("YYYY-MM-DD")],
    queryFn: async () =>
      (
        await apiClient.get<MapActivityPage>("/stock/map/activity", {
          params: {
            warehouse_id: whId,
            since: day.startOf("day").toISOString().slice(0, 19),
            until: day.add(1, "day").startOf("day").toISOString().slice(0, 19),
          },
        })
      ).data,
    enabled: !!whId && view === "replay",
    staleTime: Infinity,
  });
  const replayEvents = useMemo(
    () => (replay.data?.events ?? []).map((e) => ({ e, minute: localTime(e.at).diff(day.startOf("day"), "minute", true) })),
    [replay.data, day],
  );
  // Today ends now (fractional minutes: events of the current minute must still play); other days at midnight
  const lastEvent = replayEvents.length ? replayEvents[replayEvents.length - 1]!.minute : 0;
  const dayEnd = day.isSame(dayjs(), "day")
    ? Math.min(1440, Math.max(dayjs().diff(day.startOf("day"), "minute", true), lastEvent + 1 / 60))
    : 1440;
  const clockRef = useRef(clock);
  clockRef.current = clock;
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    const timer = setInterval(() => {
      const now = performance.now();
      const from = clockRef.current;
      const to = Math.min(dayEnd, from + ((now - last) / 1000) * (speed / 60));
      last = now;
      flash(replayEvents.filter((r) => r.minute > from && r.minute <= to).map((r) => r.e));
      setClock(to);
      if (to >= dayEnd) setPlaying(false);
    }, 100);
    return () => clearInterval(timer);
  }, [playing, speed, replayEvents, dayEnd]);
  const replayCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of replayEvents) if (r.minute <= clock) counts.set(r.e.location_id, (counts.get(r.e.location_id) ?? 0) + 1);
    return counts;
  }, [replayEvents, clock]);
  const replayMax = Math.max(0, ...replayCounts.values());
  const replayRecent = useMemo(
    () => replayEvents.filter((r) => r.minute <= clock).slice(-25).reverse().map((r) => r.e),
    [replayEvents, clock],
  );

  const switchView = (v: "live" | "replay") => {
    setView(v);
    setPlaying(false);
    setFlashes(new Map());
    if (v === "replay") setClock(0);
  };

  /* ---------- render ---------- */
  const large = tree.leafCount > 0 && tree.leafCount <= 160;
  const cellState = (n: MapNode): CellState => {
    const f = flashes.get(n.id);
    if (view === "replay") {
      const count = replayCounts.get(n.id) ?? 0;
      return {
        colour: count ? RAMPS.picks[mode][Math.min(4, Math.floor(Math.sqrt(count / (replayMax || 1)) * 5))] : undefined,
        dim: !!highlight && !highlight.has(n.id),
        flash: f,
        replayCount: count,
      };
    }
    return { colour: colour(n, metric, mode, maxPicks), dim: !!highlight && !highlight.has(n.id), flash: f, people: people.get(n.id) };
  };
  const onMouseOver = (e: ReactMouseEvent) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>("[data-id]");
    if (el?.dataset.id) setHover({ id: el.dataset.id, x: e.clientX, y: e.clientY });
    else setHover(undefined);
  };
  const hovered = hover ? tree.byId.get(hover.id) : undefined;
  const rootLeaves = tree.root ? (tree.children.get(tree.root.id) ?? []).filter(isLeaf) : [];
  const rootGroups = tree.root ? (tree.children.get(tree.root.id) ?? []).filter((n) => !isLeaf(n)) : [];
  const feed = view === "live" ? [...(activity.data?.events ?? [])].reverse().slice(0, 25) : replayRecent;
  const totals = useMemo(() => {
    const leaves = (map.data?.nodes ?? []).filter(isLeaf);
    return {
      bins: leaves.length,
      used: leaves.filter((n) => n.qty_on_hand > 0).length,
      locked: leaves.filter((n) => n.is_locked).length,
      recalled: leaves.filter((n) => n.has_recalled).length,
    };
  }, [map.data]);

  if (map.error && !map.data) return <ErrorState title="Could not load the warehouse map" error={map.error} onRetry={() => map.refetch()} />;

  return (
    <>
      <PageHeader
        title="Warehouse map"
        description="Every bin of the warehouse, live. Bins pulse as stock moves and PDAs confirm work; replay any day to see where the work happened."
        extra={
          <>
            {(map.data?.warehouses.length ?? 0) > 1 && (
              <Select
                style={{ minWidth: 200 }}
                value={whId}
                onChange={setWarehouseId}
                aria-label="Warehouse"
                options={map.data!.warehouses.map((w) => ({ value: w.id, label: `${w.code} · ${w.name}` }))}
              />
            )}
            <Segmented
              value={view}
              onChange={(v) => switchView(v as "live" | "replay")}
              options={[{ label: "Live", value: "live" }, { label: "Replay a day", value: "replay" }]}
            />
          </>
        }
      />

      {!map.data ? (
        <Card><Skeleton active /></Card>
      ) : !tree.root ? (
        <Card>
          <Empty description={<>No warehouse yet. Create a WAREHOUSE location with zones, racks and bins under <Link to="/locations">Locations</Link>.</>} />
        </Card>
      ) : (
        <div className="wms-map-layout">
          <Card
            className="wms-map-card"
            title={
              view === "live" ? (
                <Segmented
                  size="small"
                  value={metric}
                  onChange={(v) => setMetric(v as Metric)}
                  options={[
                    { label: "Fill", value: "fill" },
                    { label: "Pick heat", value: "picks" },
                    { label: "Expiry", value: "expiry" },
                    { label: "Status", value: "status" },
                  ]}
                />
              ) : (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <DatePicker
                    size="small"
                    value={day}
                    allowClear={false}
                    disabledDate={(d) => d.isAfter(dayjs(), "day")}
                    onChange={(d) => {
                      if (d) {
                        setDay(d.startOf("day"));
                        setClock(0);
                        setPlaying(false);
                        setFlashes(new Map());
                      }
                    }}
                    aria-label="Day to replay"
                  />
                  <Button
                    size="small"
                    type="primary"
                    icon={playing ? <PauseOutlined /> : <CaretRightOutlined />}
                    disabled={!replay.data || !replayEvents.length}
                    onClick={() => {
                      // From the start (or the end), skip the quiet night: begin 10 minutes before the first event
                      if (!playing && (clock === 0 || clock >= dayEnd)) setClock(Math.max(0, (replayEvents[0]?.minute ?? 0) - 10));
                      setPlaying(!playing);
                    }}
                  >
                    {playing ? "Pause" : "Play"}
                  </Button>
                  <Segmented size="small" value={speed} onChange={(v) => setSpeed(v as number)} options={SPEEDS} />
                </span>
              )
            }
            extra={
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                <AimOutlined aria-hidden style={{ color: "var(--ant-color-text-tertiary)" }} />
                <ItemSelect allowClear size="small" placeholder="Where is an item?" style={{ width: 220 }} value={findItem} onChange={setFindItem} aria-label="Highlight bins holding an item" />
              </span>
            }
          >
            {view === "replay" && (
              <div className="wms-map-timeline">
                <span className="wms-num wms-map-clock">{day.startOf("day").add(clock, "minute").format("HH:mm")}</span>
                <Slider
                  min={0}
                  max={1440}
                  step={1}
                  value={clock}
                  onChange={(v) => {
                    setPlaying(false);
                    setClock(Math.min(v as number, dayEnd));
                  }}
                  tooltip={{ formatter: (v) => day.startOf("day").add(v ?? 0, "minute").format("HH:mm") }}
                  style={{ flex: 1 }}
                  aria-label="Time of day"
                />
                <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                  {replay.isLoading ? "Loading…" : `${replayEvents.filter((r) => r.minute <= clock).length} of ${replayEvents.length} events`}
                </Typography.Text>
              </div>
            )}
            {view === "replay" && replay.data?.truncated && (
              <Alert type="info" showIcon style={{ marginBottom: 12 }} title="A very busy day: only the latest 5,000 events are replayed." />
            )}
            {highlight && (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 12 }}
                title={highlight.size ? `Held in ${highlight.size} location${highlight.size === 1 ? "" : "s"}; the rest of the map is dimmed.` : "This item is not in stock anywhere."}
              />
            )}
            <div
              className={`wms-map ${large ? "is-large" : ""}`}
              onMouseOver={onMouseOver}
              onMouseLeave={() => setHover(undefined)}
              data-testid="warehouse-map"
            >
              {rootLeaves.length > 0 && (
                <section className="wms-map-group is-docks">
                  <header className="wms-map-group-label">Docks and loose bins</header>
                  <div className="wms-map-cells">
                    {rootLeaves.map((leaf) => <Cell key={leaf.id} node={leaf} state={cellState(leaf)} large={large} onOpen={setOpenId} />)}
                  </div>
                </section>
              )}
              <div className="wms-map-zones">
                {rootGroups.map((g) => (
                  <Group key={g.id} node={g} tree={tree} cellState={cellState} large={large} onOpen={setOpenId} depth={0} />
                ))}
              </div>
            </div>
            <div className="wms-heat-legend" aria-hidden>
              {view === "live" ? (
                <>
                  <Tooltip title={METRIC_HINT[metric]}>
                    <span style={{ textDecoration: "underline dotted" }}>{{ fill: "Fill", picks: "Pick heat", expiry: "Earliest expiry", status: "Status" }[metric]}</span>
                  </Tooltip>
                  {LEGENDS[metric].map((l) => (
                    <span key={l.key} className="wms-heat-legend-step" title={l.title}>
                      <span className="wms-heat-swatch" style={{ background: legendSwatch(metric, l.key, mode) }} />
                      {l.label}
                    </span>
                  ))}
                </>
              ) : (
                <>
                  <span>Touches so far</span>
                  {RAMPS.picks[mode].map((c, i) => (
                    <span key={c} className="wms-heat-legend-step">
                      <span className="wms-heat-swatch" style={{ background: c }} />
                      {i === 0 ? "Few" : i === 4 ? "Most" : ""}
                    </span>
                  ))}
                </>
              )}
              <span className="wms-heat-legend-step"><span className="wms-map-legend-ping tone-in" /> In</span>
              <span className="wms-heat-legend-step"><span className="wms-map-legend-ping tone-out" /> Out</span>
              <span className="wms-heat-legend-step"><span className="wms-map-legend-ping tone-scan" /> PDA scan</span>
            </div>
          </Card>

          <div className="wms-map-side">
            <Card size="small" title="At a glance">
              <div className="wms-map-glance">
                <div><div className="wms-num wms-map-glance-value">{totals.used}<span>/{totals.bins}</span></div>bins in use</div>
                <div><div className="wms-num wms-map-glance-value">{people.size}</div>people active, 15 min</div>
                <div><div className="wms-num wms-map-glance-value">{totals.locked}</div>locked</div>
                <div>
                  <div className="wms-num wms-map-glance-value" style={totals.recalled ? { color: "var(--wms-tone-red-fg)" } : undefined}>{totals.recalled}</div>
                  <Link to="/recalls">with recalls</Link>
                </div>
              </div>
            </Card>
            <Card
              size="small"
              title={view === "live" ? `Last ${PRESENCE_MINUTES} minutes` : `Up to ${day.startOf("day").add(clock, "minute").format("HH:mm")}`}
              extra={view === "live" && <Pill tone={liveStatus === "live" ? "green" : "amber"} dot>{liveStatus === "live" ? "Live" : "Reconnecting"}</Pill>}
            >
              {feed.length ? (
                <div className="wms-map-feed">
                  {feed.map((e) => <FeedRow key={eventKey(e)} event={e} code={tree.byId.get(e.location_id)?.code} />)}
                </div>
              ) : (
                <Typography.Text type="secondary">
                  {view === "live" ? "Quiet for now. Receipts, picks and scans show up here as they happen." : "Press Play, or drag the time slider."}
                </Typography.Text>
              )}
            </Card>
          </div>
        </div>
      )}

      {hovered && hover && <HoverCard node={hovered} at={hover} people={view === "live" ? people.get(hovered.id) : undefined} />}
      <BinDrawer id={openId} onClose={() => setOpenId(undefined)} />
    </>
  );
}
