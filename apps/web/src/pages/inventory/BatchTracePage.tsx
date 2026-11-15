import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { AlertOutlined, SearchOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Empty, Form, Input, Modal, Segmented, Skeleton, Space, Table, Tabs, Typography, message } from "antd";
import { Link, useNavigate, useSearchParams } from "react-router";

import { apiClient } from "@/api/client";
import { getErrorMessage } from "@/api/errors";
import { useCan } from "@/api/me";
import type { BatchHit, BatchTrace, DocumentTrace, Recall, TraceFlow } from "@/api/types";
import { formatDateTime } from "@/components/documents";
import { ItemSelect, LocationSelect } from "@/components/selects";
import StatusTag from "@/components/StatusTag";
import { ErrorState, Kpi, KpiStrip, Pill, formatQty, type Accent } from "@/components/ui";
import { DOC_PATHS, DOC_TYPE_LABELS, MOVEMENT_TYPE_LABELS } from "@/constants/labels";

/* ------------------------------------------------------------------ helpers */

const FLOW_TONE: Record<string, Accent> = {
  RECEIVE: "green", RETURN_IN: "cyan", REPACK_IN: "slate", ADJUST_IN: "slate", COUNT_GAIN: "slate",
  SHIP_OUT: "amber", RETURN_OUT: "violet", REPACK_OUT: "slate", ADJUST_OUT: "slate", COUNT_LOSS: "slate",
};
const toneVar = (tone: Accent) => `var(--wms-tone-${tone}-fg)`;

function DocLink({ doc }: { doc?: { id: string; doc_type: string; doc_no: string } | null }) {
  if (!doc) return <span className="wms-empty-value">—</span>;
  const path = DOC_PATHS[doc.doc_type];
  return path ? <Link className="wms-mono" to={`/${path}/${doc.id}`}>{doc.doc_no}</Link> : <span className="wms-mono">{doc.doc_no}</span>;
}

const traceUrl = (itemId: string, batch: string) => `/trace?item=${itemId}&batch=${encodeURIComponent(batch)}`;

/* ------------------------------------------------------------------ flow diagram */

interface FlowNode {
  key: string;
  title: ReactNode;
  meta: ReactNode;
  qty: number;
  tone: Accent;
}

const MAX_SIDE = 7;

/** Keep the busiest nodes; fold the rest into one "+N more" node so a batch sent to 300 stores stays readable */
function fold(nodes: FlowNode[], noun: string): FlowNode[] {
  if (nodes.length <= MAX_SIDE) return nodes;
  const sorted = [...nodes].sort((a, b) => b.qty - a.qty);
  const kept = sorted.slice(0, MAX_SIDE - 1);
  const rest = sorted.slice(MAX_SIDE - 1);
  return [
    ...kept,
    { key: "more", title: `+${rest.length} more ${noun}`, meta: "See the tables below", qty: rest.reduce((s, n) => s + n.qty, 0), tone: "slate" },
  ];
}

function flowNode(f: TraceFlow, i: number): FlowNode {
  const label = MOVEMENT_TYPE_LABELS[f.movement_type] ?? f.movement_type;
  return {
    key: `${f.document?.id ?? i}-${f.movement_type}`,
    title: f.partner ? f.partner.name : label,
    meta: (
      <>
        {f.document ? <DocLink doc={f.document} /> : label} · {formatDateTime(f.at).slice(0, 10)}
      </>
    ),
    qty: f.qty,
    tone: FLOW_TONE[f.movement_type] ?? "slate",
  };
}

function FlowDiagram({ trace }: { trace: BatchTrace }) {
  const unit = trace.item.base_uom.code;
  const left = fold(trace.inbound.map(flowNode), "sources");
  const right = [
    ...fold(trace.outbound.map(flowNode), "destinations"),
    ...fold(
      trace.stock.map((s) => ({
        key: `stock-${s.location.id}-${s.expiry_date}`,
        title: <>In stock · <span className="wms-mono">{s.location.code}</span></>,
        meta: s.qty_allocated ? `${formatQty(s.qty_allocated)} allocated` : "Free",
        qty: s.qty_on_hand,
        tone: "blue" as Accent,
      })),
      "locations",
    ).slice(0, 4),
  ];

  const canvas = useRef<HTMLDivElement>(null);
  const hub = useRef<HTMLDivElement>(null);
  const leftRefs = useRef<(HTMLDivElement | null)[]>([]);
  const rightRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [paths, setPaths] = useState<{ d: string; width: number; tone: Accent; key: string }[]>([]);

  useLayoutEffect(() => {
    const draw = () => {
      const c = canvas.current?.getBoundingClientRect();
      const h = hub.current?.getBoundingClientRect();
      if (!c || !h) return;
      const max = Math.max(1, ...left.map((n) => n.qty), ...right.map((n) => n.qty));
      const width = (qty: number) => Math.max(2, Math.min(26, (qty / max) * 26));
      const next: typeof paths = [];
      const band = (nodes: FlowNode[], refs: (HTMLDivElement | null)[], side: "left" | "right") => {
        const total = nodes.reduce((s, n) => s + width(n.qty), 0);
        let offset = h.top + h.height / 2 - total / 2 - c.top;
        nodes.forEach((n, i) => {
          const r = refs[i]?.getBoundingClientRect();
          if (!r) return;
          const w = width(n.qty);
          const hubY = offset + w / 2;
          offset += w;
          const nodeY = r.top + r.height / 2 - c.top;
          const [x1, y1, x2, y2] =
            side === "left" ? [r.right - c.left, nodeY, h.left - c.left, hubY] : [h.right - c.left, hubY, r.left - c.left, nodeY];
          const mid = (x1 + x2) / 2;
          next.push({ key: `${side}-${n.key}`, d: `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`, width: w, tone: n.tone });
        });
      };
      band(left, leftRefs.current, "left");
      band(right, rightRefs.current, "right");
      setPaths(next);
    };
    draw();
    const observer = new ResizeObserver(draw);
    if (canvas.current) observer.observe(canvas.current);
    return () => observer.disconnect();
  }, [trace]); // eslint-disable-line react-hooks/exhaustive-deps

  const nodeCard = (n: FlowNode, i: number, refs: typeof leftRefs) => (
    <div key={n.key} ref={(el) => { refs.current[i] = el; }} className="wms-trace-node" style={{ ["--node-accent" as string]: toneVar(n.tone) }}>
      <span className="wms-trace-node-qty wms-num">{formatQty(n.qty)} {unit}</span>
      <div className="wms-trace-node-title">{n.title}</div>
      <div className="wms-trace-node-meta">{n.meta}</div>
    </div>
  );

  return (
    <div className="wms-trace-flow" data-testid="trace-flow">
      <div className="wms-trace-canvas" ref={canvas}>
        <svg aria-hidden>
          {paths.map((p) => (
            <path key={p.key} d={p.d} fill="none" stroke={toneVar(p.tone)} strokeOpacity={0.32} strokeWidth={p.width} strokeLinecap="butt" />
          ))}
        </svg>
        <div className="wms-trace-cols">
          <div className="wms-trace-col">
            <div className="wms-trace-col-title">Came from</div>
            {left.length ? left.map((n, i) => nodeCard(n, i, leftRefs)) : <Typography.Text type="secondary">No receipts recorded</Typography.Text>}
          </div>
          <div ref={hub} className={`wms-trace-hub ${trace.active_recall ? "is-recalled" : ""}`}>
            <div className="wms-trace-col-title">Batch</div>
            <div className="wms-trace-hub-batch wms-mono">{trace.batch_no}</div>
            <div className="wms-trace-hub-item">{trace.item.sku_code} · {trace.item.name}</div>
            {trace.expiry_dates.length > 0 && <div className="wms-trace-hub-item">Expires {trace.expiry_dates.join(", ")}</div>}
            {trace.active_recall && (
              <div style={{ marginTop: 8 }}>
                <Link to={`/recalls/${trace.active_recall.id}`}><Pill tone="red" icon={<AlertOutlined />}>On hold · {trace.active_recall.doc_no}</Pill></Link>
              </div>
            )}
          </div>
          <div className="wms-trace-col">
            <div className="wms-trace-col-title">Went to / is now</div>
            {right.length ? right.map((n, i) => nodeCard(n, i, rightRefs)) : <Typography.Text type="secondary">Nothing left the warehouse yet</Typography.Text>}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ recall dialog */

function RecallDialog({ trace, open, onClose }: { trace: BatchTrace; open: boolean; onClose: () => void }) {
  const [form] = Form.useForm<{ reason: string; quarantine_location_id?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const recall = useMutation({
    mutationFn: async (values: { reason: string; quarantine_location_id?: string }) =>
      (await apiClient.post<Recall>("/recalls", { item_id: trace.item.id, batch_no: trace.batch_no, ...values })).data,
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["stock"] });
      queryClient.invalidateQueries({ queryKey: ["recalls"] });
      message.success(`Recall ${r.document.doc_no} started: batch ${trace.batch_no} is on hold`);
      onClose();
      navigate(`/recalls/${r.document.id}`);
    },
  });
  const s = trace.summary;
  return (
    <Modal
      open={open}
      title={<span><AlertOutlined style={{ color: "var(--wms-tone-red-fg)" }} /> Recall batch {trace.batch_no}</span>}
      okText="Start recall"
      okButtonProps={{ danger: true, loading: recall.isPending }}
      onOk={() => form.submit()}
      onCancel={onClose}
      destroyOnHidden
    >
      <Typography.Paragraph>
        The batch is held at once: it is no longer allocated to orders, and shipments carrying it cannot be posted.
      </Typography.Paragraph>
      <ul style={{ paddingLeft: 18, marginTop: 0 }}>
        <li>{formatQty(s.qty_on_hand)} {trace.item.base_uom.code} in the warehouse{s.qty_allocated ? `, of which ${formatQty(s.qty_allocated)} is allocated or picked` : ""}.</li>
        <li>{formatQty(s.shipped)} shipped to {s.customers} customer{s.customers === 1 ? "" : "s"}: you get the list to notify them.</li>
        {trace.pending_shipments.length > 0 && <li>{trace.pending_shipments.length} loaded shipment{trace.pending_shipments.length === 1 ? "" : "s"} will be stopped.</li>}
      </ul>
      {recall.error && <Alert type="error" showIcon style={{ marginBottom: 12 }} title={getErrorMessage(recall.error)} />}
      <Form form={form} layout="vertical" onFinish={(v) => recall.mutate(v)} requiredMark="optional">
        <Form.Item name="reason" label="Reason" rules={[{ required: true, whitespace: true, message: "Say why the batch is recalled" }]}>
          <Input.TextArea rows={2} maxLength={400} placeholder="e.g. Supplier reported contamination" autoFocus />
        </Form.Item>
        <Form.Item
          name="quarantine_location_id"
          label="Quarantine location"
          extra="Optional. A draft move takes everything that can move now to this bin or dock; post it once the goods are there."
        >
          <LocationSelect types={["BIN", "DOCK"]} allowClear placeholder="Leave empty to only hold the batch" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ one batch */

function TraceView({ itemId, batch }: { itemId: string; batch: string }) {
  const can = useCan();
  const [recallOpen, setRecallOpen] = useState(false);
  const { data: trace, isLoading, error, refetch } = useQuery({
    queryKey: ["stock", "trace", itemId, batch],
    queryFn: async () => (await apiClient.get<BatchTrace>("/trace/batch", { params: { item_id: itemId, batch_no: batch } })).data,
    retry: false,
  });
  if (isLoading) return <Card><Skeleton active /></Card>;
  if (!trace) return <ErrorState title="Could not trace this batch" error={error} onRetry={() => refetch()} />;
  const s = trace.summary;
  const unit = trace.item.base_uom.code;
  const customers = trace.outbound.filter((f) => f.movement_type === "SHIP_OUT");

  return (
    <Space orientation="vertical" style={{ width: "100%" }} size={16}>
      <Card
        title={
          <span style={{ display: "inline-flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span>Batch <span className="wms-mono">{trace.batch_no}</span></span>
            <Typography.Text type="secondary" style={{ fontWeight: 400 }}>{trace.item.sku_code} · {trace.item.name}</Typography.Text>
            {trace.active_recall && <Pill tone="red" dot>On hold</Pill>}
          </span>
        }
        extra={
          trace.active_recall ? (
            <Link to={`/recalls/${trace.active_recall.id}`}><Button danger icon={<AlertOutlined />}>Open recall {trace.active_recall.doc_no}</Button></Link>
          ) : can("recall.create") ? (
            <Button danger icon={<AlertOutlined />} onClick={() => setRecallOpen(true)}>Recall this batch</Button>
          ) : null
        }
      >
        <KpiStrip>
          <Kpi label="Received" value={s.received} hint={`${s.suppliers} supplier${s.suppliers === 1 ? "" : "s"}`} />
          <Kpi label="Shipped" value={s.shipped} hint={`${s.shipments} shipment${s.shipments === 1 ? "" : "s"}`} />
          <Kpi label="Customers" value={s.customers} />
          <Kpi label="In the warehouse" value={s.qty_on_hand} hint={s.qty_allocated ? `${formatQty(s.qty_allocated)} allocated` : unit} />
          {(s.returned_in > 0 || s.returned_out > 0) && <Kpi label="Returned" value={s.returned_in + s.returned_out} hint={`${formatQty(s.returned_in)} in · ${formatQty(s.returned_out)} out`} />}
          {(s.other_in > 0 || s.other_out > 0) && <Kpi label="Adjusted / counted" value={s.other_in - s.other_out} hint={`+${formatQty(s.other_in)} / -${formatQty(s.other_out)}`} />}
        </KpiStrip>
        <div style={{ marginTop: 20 }}>
          <FlowDiagram trace={trace} />
        </div>
        {trace.pending_shipments.length > 0 && (
          <Alert
            type={trace.active_recall ? "error" : "warning"}
            showIcon
            style={{ marginTop: 16 }}
            title={
              <>
                {trace.active_recall ? "Stopped by the recall: " : "Loaded and about to leave: "}
                {trace.pending_shipments.map((p, i) => (
                  <span key={p.document?.id ?? i}>
                    {i > 0 && ", "}
                    <DocLink doc={p.document} /> ({p.partner?.name}, {formatQty(p.qty)} {unit})
                  </span>
                ))}
              </>
            }
          />
        )}
      </Card>

      <Card>
        <Tabs
          items={[
            {
              key: "customers",
              label: `Customers (${customers.length})`,
              children: (
                <Table<TraceFlow>
                  rowKey={(r, i) => `${r.document?.id ?? i}`}
                  size="small"
                  dataSource={customers}
                  pagination={{ pageSize: 20, hideOnSinglePage: true }}
                  scroll={{ x: "max-content" }}
                  locale={{ emptyText: "Not shipped to anyone yet" }}
                  columns={[
                    { title: "Customer", render: (_, r) => (r.partner ? <>{r.partner.name} <Typography.Text type="secondary" className="wms-mono">{r.partner.code}</Typography.Text></> : "—") },
                    { title: "Contact", render: (_, r) => [r.partner?.contact_name, r.partner?.contact_phone].filter(Boolean).join(" · ") || <span className="wms-empty-value">—</span> },
                    { title: "Address", render: (_, r) => r.partner?.address ?? <span className="wms-empty-value">—</span>, ellipsis: true },
                    { title: "Delivery order", render: (_, r) => <DocLink doc={r.document} /> },
                    { title: "Sales order", render: (_, r) => <DocLink doc={r.source} /> },
                    { title: "Shipped", render: (_, r) => formatDateTime(r.at) },
                    { title: "Vehicle", render: (_, r) => r.vehicle_no ?? <span className="wms-empty-value">—</span> },
                    { title: "Qty", align: "right", render: (_, r) => `${formatQty(r.qty)} ${unit}` },
                  ]}
                />
              ),
            },
            {
              key: "inbound",
              label: `Came from (${trace.inbound.length})`,
              children: (
                <Table<TraceFlow>
                  rowKey={(r, i) => `${r.document?.id ?? i}-${r.movement_type}`}
                  size="small"
                  dataSource={trace.inbound}
                  pagination={{ pageSize: 20, hideOnSinglePage: true }}
                  scroll={{ x: "max-content" }}
                  columns={[
                    { title: "How", render: (_, r) => <Pill tone={FLOW_TONE[r.movement_type] ?? "slate"}>{MOVEMENT_TYPE_LABELS[r.movement_type] ?? r.movement_type}</Pill> },
                    { title: "From", render: (_, r) => r.partner?.name ?? <span className="wms-empty-value">—</span> },
                    { title: "Document", render: (_, r) => <DocLink doc={r.document} /> },
                    { title: "Source", render: (_, r) => <DocLink doc={r.source} /> },
                    { title: "When", render: (_, r) => formatDateTime(r.at) },
                    { title: "Qty", align: "right", render: (_, r) => `${formatQty(r.qty)} ${unit}` },
                  ]}
                />
              ),
            },
            {
              key: "other-out",
              label: `Other outflows (${trace.outbound.length - customers.length})`,
              children: (
                <Table<TraceFlow>
                  rowKey={(r, i) => `${r.document?.id ?? i}-${r.movement_type}`}
                  size="small"
                  dataSource={trace.outbound.filter((f) => f.movement_type !== "SHIP_OUT")}
                  pagination={{ pageSize: 20, hideOnSinglePage: true }}
                  locale={{ emptyText: "No returns to supplier, write-offs or repacks" }}
                  columns={[
                    { title: "How", render: (_, r) => <Pill tone={FLOW_TONE[r.movement_type] ?? "slate"}>{MOVEMENT_TYPE_LABELS[r.movement_type] ?? r.movement_type}</Pill> },
                    { title: "To", render: (_, r) => r.partner?.name ?? <span className="wms-empty-value">—</span> },
                    { title: "Document", render: (_, r) => <DocLink doc={r.document} /> },
                    { title: "When", render: (_, r) => formatDateTime(r.at) },
                    { title: "Qty", align: "right", render: (_, r) => `${formatQty(r.qty)} ${unit}` },
                  ]}
                />
              ),
            },
            {
              key: "stock",
              label: `In stock (${trace.stock.length})`,
              children: (
                <Table
                  rowKey={(r) => `${r.location.id}-${r.expiry_date}`}
                  size="small"
                  dataSource={trace.stock}
                  pagination={false}
                  locale={{ emptyText: "None of this batch is left in the warehouse" }}
                  columns={[
                    { title: "Location", render: (_, r) => <span className="wms-mono">{r.location.code}</span> },
                    { title: "Name", render: (_, r) => r.location.name },
                    { title: "Expiry", render: (_, r) => r.expiry_date ?? <span className="wms-empty-value">—</span> },
                    { title: "On hand", align: "right", render: (_, r) => formatQty(r.qty_on_hand) },
                    { title: "Allocated", align: "right", render: (_, r) => (r.qty_allocated ? formatQty(r.qty_allocated) : <span className="wms-empty-value">—</span>) },
                  ]}
                />
              ),
            },
            {
              key: "movements",
              label: `Every movement (${trace.movements_total})`,
              children: (
                <>
                  {trace.movements_total > trace.movements.length && (
                    <Typography.Paragraph type="secondary">Showing the latest {trace.movements.length} of {trace.movements_total}.</Typography.Paragraph>
                  )}
                  <Table
                    rowKey={(r, i) => `${r.at}-${i}`}
                    size="small"
                    dataSource={trace.movements}
                    pagination={{ pageSize: 50, hideOnSinglePage: true }}
                    scroll={{ x: "max-content" }}
                    columns={[
                      { title: "When", render: (_, r) => formatDateTime(r.at) },
                      { title: "Movement", render: (_, r) => MOVEMENT_TYPE_LABELS[r.movement_type] ?? r.movement_type },
                      { title: "Location", render: (_, r) => <span className="wms-mono">{r.location.code}</span> },
                      { title: "Document", render: (_, r) => <DocLink doc={r.document} /> },
                      { title: "By", render: (_, r) => r.user_name ?? <span className="wms-empty-value">—</span> },
                      { title: "Qty", align: "right", render: (_, r) => <span className="wms-num">{r.qty > 0 ? "+" : ""}{formatQty(r.qty)}</span> },
                    ]}
                  />
                </>
              ),
            },
            ...(trace.recalls.length
              ? [{
                  key: "recalls",
                  label: `Recalls (${trace.recalls.length})`,
                  children: (
                    <Space wrap>
                      {trace.recalls.map((r) => (
                        <span key={r.id} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                          <DocLink doc={r} /> <StatusTag status={r.status} />
                        </span>
                      ))}
                    </Space>
                  ),
                }]
              : []),
          ]}
        />
      </Card>
      <RecallDialog trace={trace} open={recallOpen} onClose={() => setRecallOpen(false)} />
    </Space>
  );
}

/* ------------------------------------------------------------------ reverse: from a document */

function DocumentView({ docNo }: { docNo: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["stock", "trace-doc", docNo],
    queryFn: async () => (await apiClient.get<DocumentTrace>("/trace/documents/lookup", { params: { doc_no: docNo } })).data,
    retry: false,
  });
  if (isLoading) return <Card><Skeleton active /></Card>;
  if (!data) return <Alert type="warning" showIcon title={getErrorMessage(error)} />;
  const d = data.document;
  return (
    <Card
      title={
        <span style={{ display: "inline-flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          {DOC_TYPE_LABELS[d.doc_type] ?? d.doc_type} <DocLink doc={d} /> <StatusTag status={d.status} />
          {data.partner && <Typography.Text type="secondary" style={{ fontWeight: 400 }}>{data.partner.name}</Typography.Text>}
        </span>
      }
    >
      <Typography.Paragraph type="secondary">
        Each batch on this document, where it came from and how far it spread. Open a batch for its full trace or to recall it.
      </Typography.Paragraph>
      <Table
        rowKey={(r) => `${r.item.id}|${r.batch_no}|${r.expiry_date}`}
        size="small"
        dataSource={data.batches}
        pagination={false}
        scroll={{ x: "max-content" }}
        columns={[
          { title: "SKU", render: (_, r) => <span className="wms-mono">{r.item.sku_code}</span> },
          { title: "Item", render: (_, r) => r.item.name, ellipsis: true },
          {
            title: "Batch",
            render: (_, r) =>
              r.batch_no ? (
                <span style={{ display: "inline-flex", gap: 6, alignItems: "center", whiteSpace: "nowrap" }}>
                  <Link className="wms-mono" to={traceUrl(r.item.id, r.batch_no)}>{r.batch_no}</Link>
                  {r.active_recall && <Link to={`/recalls/${r.active_recall.id}`}><Pill tone="red" dot>On hold</Pill></Link>}
                </span>
              ) : (
                <Typography.Text type="secondary">Not batch managed</Typography.Text>
              ),
          },
          { title: "Expiry", render: (_, r) => r.expiry_date ?? <span className="wms-empty-value">—</span> },
          { title: "Qty here", align: "right", render: (_, r) => formatQty(r.qty) },
          { title: "Supplier", render: (_, r) => r.suppliers.map((p) => p.name).join(", ") || <span className="wms-empty-value">—</span> },
          { title: "Receipts", render: (_, r) => (r.receipts.length ? r.receipts.map((g, i) => <span key={g.id}>{i > 0 && ", "}<DocLink doc={g} /></span>) : <span className="wms-empty-value">—</span>) },
          { title: "Other customers", align: "right", render: (_, r) => (r.batch_no ? r.other_customers : "") },
          { title: "Still in stock", align: "right", render: (_, r) => (r.batch_no ? formatQty(r.qty_on_hand) : "") },
        ]}
      />
    </Card>
  );
}

/* ------------------------------------------------------------------ the page */

export default function BatchTracePage() {
  const [params, setParams] = useSearchParams();
  const itemId = params.get("item") ?? undefined;
  const batch = params.get("batch") ?? undefined;
  const docNo = params.get("doc") ?? undefined;
  const [by, setBy] = useState<"batch" | "document">(docNo ? "document" : "batch");
  const [batchInput, setBatchInput] = useState(batch ?? "");
  const [itemInput, setItemInput] = useState<string | undefined>(itemId);
  const [docInput, setDocInput] = useState(docNo ?? "");
  const [search, setSearch] = useState<{ q: string; item?: string }>();

  const hits = useQuery({
    queryKey: ["stock", "trace-search", search],
    queryFn: async () => (await apiClient.get<BatchHit[]>("/trace/batches", { params: { q: search!.q || undefined, item_id: search!.item } })).data,
    enabled: !!search,
  });

  const open = (hit: BatchHit) => {
    setSearch(undefined);
    setParams({ item: hit.item.id, batch: hit.batch_no });
  };
  // One match: open it straight away
  const only = hits.data?.length === 1 ? hits.data[0] : undefined;
  useEffect(() => {
    if (only && search) open(only);
  }, [only]); // eslint-disable-line react-hooks/exhaustive-deps

  const runSearch = () => {
    if (by === "document") {
      if (docInput.trim()) setParams({ doc: docInput.trim() });
      return;
    }
    if (!batchInput.trim() && !itemInput) return;
    setParams({});
    setSearch({ q: batchInput.trim(), item: itemInput });
  };

  return (
    <Space orientation="vertical" style={{ width: "100%" }} size={16}>
      <Card>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <Segmented
            value={by}
            onChange={(v) => setBy(v as "batch" | "document")}
            options={[{ label: "By batch", value: "batch" }, { label: "From a document", value: "document" }]}
          />
          {by === "batch" ? (
            <>
              <Input
                style={{ width: 220 }}
                placeholder="Batch number"
                value={batchInput}
                onChange={(e) => setBatchInput(e.target.value)}
                onPressEnter={runSearch}
                allowClear
                aria-label="Batch number"
                autoFocus
              />
              <ItemSelect allowClear placeholder="Item (optional)" style={{ width: 280 }} value={itemInput} onChange={setItemInput} aria-label="Item" />
            </>
          ) : (
            <Input
              style={{ width: 300 }}
              placeholder="Delivery order, receipt or other document no."
              value={docInput}
              onChange={(e) => setDocInput(e.target.value)}
              onPressEnter={runSearch}
              allowClear
              aria-label="Document number"
            />
          )}
          <Button type="primary" icon={<SearchOutlined />} onClick={runSearch}>Trace</Button>
        </div>
        <Typography.Paragraph type="secondary" style={{ margin: "10px 0 0" }}>
          {by === "batch"
            ? "Type the start of a batch number, or choose an item to see all its batches. Scanning a barcode into the field works too."
            : "A customer complains about a delivery? Enter its number to see which batches it carried, where they came from and who else received them."}
        </Typography.Paragraph>
      </Card>

      {search && !only && (
        <Card title="Matching batches">
          <Table<BatchHit>
            rowKey={(r) => `${r.item.id}|${r.batch_no}`}
            size="small"
            loading={hits.isLoading}
            dataSource={hits.data}
            pagination={false}
            locale={{ emptyText: <Empty description="No batch found" /> }}
            onRow={(r) => ({ onClick: () => open(r), style: { cursor: "pointer" } })}
            columns={[
              { title: "Batch", render: (_, r) => <a className="wms-mono">{r.batch_no}</a> },
              { title: "SKU", render: (_, r) => <span className="wms-mono">{r.item.sku_code}</span> },
              { title: "Item", render: (_, r) => r.item.name },
              { title: "First seen", render: (_, r) => formatDateTime(r.first_seen) },
              { title: "Last movement", render: (_, r) => formatDateTime(r.last_seen) },
              { title: "In stock", align: "right", render: (_, r) => formatQty(r.qty_on_hand) },
              { title: "", render: (_, r) => (r.recalled ? <Pill tone="red" dot>On hold</Pill> : null) },
            ]}
          />
        </Card>
      )}

      {itemId && batch && !search && <TraceView key={`${itemId}|${batch}`} itemId={itemId} batch={batch} />}
      {docNo && !search && <DocumentView key={docNo} docNo={docNo} />}
    </Space>
  );
}
