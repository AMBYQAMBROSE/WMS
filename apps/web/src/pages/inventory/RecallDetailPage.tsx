import { AlertOutlined, DownloadOutlined, NodeIndexOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Space, Table, Typography, message } from "antd";
import { Link, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { Recall, TraceFlow } from "@/api/types";
import { ActionButton, formatDateTime } from "@/components/documents";
import { exportReport } from "@/components/reports";
import StatusTag from "@/components/StatusTag";
import { DESC_COLUMNS, DetailSkeleton, DocTitle, ErrorState, Kpi, KpiStrip, Pill, formatQty } from "@/components/ui";

/**
 * A batch recall: what it holds, how far the quarantine got, which shipments it stopped and whom to notify.
 * Everything below the header is the batch's live trace, so it follows the warehouse as goods are moved and returned.
 */
export default function RecallDetailPage() {
  const { id = "" } = useParams();
  const can = useCan();
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["recalls", id],
    queryFn: async () => (await apiClient.get<Recall>(`/recalls/${id}`)).data,
  });
  const release = useMutation({
    mutationFn: async () => (await apiClient.post<Recall>(`/recalls/${id}/release`)).data,
    onSuccess: (r) => {
      queryClient.setQueryData(["recalls", id], r);
      ["recalls", "stock", "sales-orders", "shipments"].forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
      message.success(`Recall ${r.document.doc_no} released: batch ${r.document.lines[0]?.batch_no} can be allocated and shipped again`);
    },
    onError: showError,
  });

  if (isLoading) return <DetailSkeleton />;
  if (!data) return <ErrorState title="Could not load this recall" error={error} onRetry={() => refetch()} back={{ to: "/recalls", label: "Back to recalls" }} />;

  const doc = data.document;
  const line = doc.lines[0]!;
  const trace = data.trace;
  const unit = line.item.base_uom.code;
  const active = doc.status === "ACTIVE";
  const quarantine = doc.location;
  const outside = trace.stock.filter((s) => s.location.id !== quarantine?.id);
  const outsideQty = outside.reduce((sum, s) => sum + s.qty_on_hand, 0);
  const inQuarantine = trace.stock.filter((s) => s.location.id === quarantine?.id).reduce((sum, s) => sum + s.qty_on_hand, 0);
  const customers = trace.outbound.filter((f) => f.movement_type === "SHIP_OUT");
  const draftMoves = data.moves.filter((m) => m.status === "DRAFT");
  const traceLink = `/trace?item=${line.item.id}&batch=${encodeURIComponent(line.batch_no ?? "")}`;

  return (
    <Space orientation="vertical" style={{ width: "100%" }} size={16}>
      <Card
        title={<DocTitle label="Batch recall" no={doc.doc_no} status={doc.status} historyOf={doc.id} />}
        extra={
          <Space wrap>
            <Link to={traceLink}><Button icon={<NodeIndexOutlined />}>Full trace</Button></Link>
            {active && (
              <ActionButton
                perm="recall.close"
                label="Release hold"
                confirm={`Release batch ${line.batch_no}? It can be allocated and shipped again right away.`}
                onConfirm={() => release.mutate()}
                loading={release.isPending}
              />
            )}
          </Space>
        }
      >
        {active ? (
          <Alert
            type="error"
            showIcon
            icon={<AlertOutlined />}
            style={{ marginBottom: 16 }}
            title={`Batch ${line.batch_no} is on hold: it is not allocated to orders and shipments carrying it cannot be posted.`}
          />
        ) : (
          <Alert type="info" showIcon style={{ marginBottom: 16 }} title={`Released ${formatDateTime(doc.posted_at)}. The batch is handled like any other again.`} />
        )}
        <Descriptions column={DESC_COLUMNS}>
          <Descriptions.Item label="Item"><span className="wms-mono">{line.item.sku_code}</span>&nbsp;{line.item.name}</Descriptions.Item>
          <Descriptions.Item label="Batch"><Link className="wms-mono" to={traceLink}>{line.batch_no}</Link></Descriptions.Item>
          <Descriptions.Item label="Expiry">{trace.expiry_dates.join(", ") || <span className="wms-empty-value">—</span>}</Descriptions.Item>
          <Descriptions.Item label="Reason">{doc.remark}</Descriptions.Item>
          <Descriptions.Item label="Quarantine">
            {quarantine ? <span className="wms-mono">{quarantine.code}</span> : <span className="wms-empty-value">None chosen</span>}
          </Descriptions.Item>
          <Descriptions.Item label="Started">{formatDateTime(doc.created_at)}</Descriptions.Item>
          <Descriptions.Item label="When it started">
            {formatQty(line.qty_planned)} {unit} in the warehouse, {formatQty(line.qty_actual)} {unit} already shipped
          </Descriptions.Item>
        </Descriptions>
        <div style={{ marginTop: 16 }}>
          <KpiStrip>
            <Kpi label="In the warehouse now" value={trace.summary.qty_on_hand} hint={unit} />
            {quarantine && <Kpi label="In quarantine" value={inQuarantine} hint={quarantine.code} />}
            <Kpi label="Not yet in quarantine" value={quarantine ? outsideQty : trace.summary.qty_on_hand} hint={`${outside.length} location${outside.length === 1 ? "" : "s"}`} />
            <Kpi label="Customers to notify" value={trace.summary.customers} hint={`${formatQty(trace.summary.shipped)} ${unit} shipped`} />
            <Kpi label="Shipments stopped" value={trace.pending_shipments.length} />
          </KpiStrip>
        </div>
      </Card>

      <Card title="Quarantine">
        {data.skipped.length > 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            title="Not in the quarantine move"
            description={
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {data.skipped.map((s, i) => (
                  <li key={i}><span className="wms-mono">{s.location.code}</span>: {formatQty(s.qty)} {unit}, {s.reason}</li>
                ))}
              </ul>
            }
          />
        )}
        {data.moves.length > 0 ? (
          <Space wrap style={{ marginBottom: 12 }}>
            {data.moves.map((m) => (
              <span key={m.id} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                Move <Link className="wms-mono" to={`/moves/${m.id}`}>{m.doc_no}</Link> <StatusTag status={m.status} />
              </span>
            ))}
            {draftMoves.length > 0 && <Typography.Text type="secondary">Post the move once the goods are in quarantine.</Typography.Text>}
          </Space>
        ) : (
          <Typography.Paragraph type="secondary">
            {quarantine ? "Nothing could be moved when the recall started." : "No quarantine location was chosen; the batch is held where it is."}
          </Typography.Paragraph>
        )}
        <Table
          rowKey={(r) => `${r.location.id}-${r.expiry_date}`}
          size="small"
          dataSource={trace.stock}
          pagination={false}
          locale={{ emptyText: "None of the batch is left in the warehouse" }}
          columns={[
            { title: "Location", render: (_, r) => <span className="wms-mono">{r.location.code}</span> },
            { title: "Name", render: (_, r) => r.location.name },
            { title: "On hand", align: "right", render: (_, r) => formatQty(r.qty_on_hand) },
            { title: "Allocated", align: "right", render: (_, r) => (r.qty_allocated ? formatQty(r.qty_allocated) : <span className="wms-empty-value">—</span>) },
            {
              title: "",
              render: (_, r) =>
                r.location.id === quarantine?.id ? (
                  <Pill tone="green" dot>In quarantine</Pill>
                ) : r.qty_allocated > 0 ? (
                  <Typography.Text type="secondary">
                    {r.location.location_type === "DOCK" ? "Picked: return it to stock from its pick list" : "Allocated: cancel the pick list to release it"}
                  </Typography.Text>
                ) : active && can("move.create") ? (
                  <Link to={`/moves/new?from=${r.location.id}`}>Move…</Link>
                ) : null,
            },
          ]}
        />
      </Card>

      {trace.pending_shipments.length > 0 && (
        <Card title={`Shipments ${active ? "stopped" : "held up"} (${trace.pending_shipments.length})`}>
          <FlowTable rows={trace.pending_shipments} unit={unit} />
        </Card>
      )}

      <Card
        title={`Customers to notify (${customers.length})`}
        extra={
          customers.length > 0 && (
            <Button icon={<DownloadOutlined />} onClick={() => exportReport(`/recalls/${doc.id}/customers.csv`, {})}>
              Download list
            </Button>
          )
        }
      >
        <FlowTable rows={customers} unit={unit} empty="The batch has not reached any customer." />
      </Card>
    </Space>
  );
}

function FlowTable({ rows, unit, empty }: { rows: TraceFlow[]; unit: string; empty?: string }) {
  return (
    <Table<TraceFlow>
      rowKey={(r, i) => `${r.document?.id ?? i}`}
      size="small"
      dataSource={rows}
      pagination={{ pageSize: 20, hideOnSinglePage: true }}
      scroll={{ x: "max-content" }}
      locale={{ emptyText: empty }}
      columns={[
        { title: "Customer", render: (_, r) => r.partner?.name ?? <span className="wms-empty-value">—</span> },
        { title: "Contact", render: (_, r) => [r.partner?.contact_name, r.partner?.contact_phone].filter(Boolean).join(" · ") || <span className="wms-empty-value">—</span> },
        { title: "Address", render: (_, r) => r.partner?.address ?? <span className="wms-empty-value">—</span>, ellipsis: true },
        { title: "Delivery order", render: (_, r) => (r.document ? <Link className="wms-mono" to={`/shipments/${r.document.id}`}>{r.document.doc_no}</Link> : "—") },
        { title: "Sales order", render: (_, r) => (r.source ? <Link className="wms-mono" to={`/sales-orders/${r.source.id}`}>{r.source.doc_no}</Link> : "—") },
        { title: "Date", render: (_, r) => formatDateTime(r.at) },
        { title: "Qty", align: "right", render: (_, r) => `${formatQty(r.qty)} ${unit}` },
      ]}
    />
  );
}
