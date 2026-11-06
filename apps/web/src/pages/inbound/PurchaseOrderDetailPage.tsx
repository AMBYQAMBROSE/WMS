import { useQuery } from "@tanstack/react-query";
import { Button, Card, Descriptions, Space, Table } from "antd";
import { Link, useNavigate, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { DocumentSummary } from "@/api/types";
import StatusTag from "@/components/StatusTag";
import { DESC_COLUMNS, DetailSkeleton, DocTitle, ErrorState, QtyProgress, emptyLocale, formatQty } from "@/components/ui";
import { PurchaseOrderSteps } from "@/components/workflows";
import {
  ActionButton,
  DocumentLinesTable,
  formatDateTime,
  useDocument,
  useDocumentAction,
} from "@/components/documents";

export default function PurchaseOrderDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const can = useCan();
  const { data: po, isLoading, error, refetch } = useDocument("purchase-orders", id);
  const action = useDocumentAction("purchase-orders", id);
  const { data: grns, isLoading: grnsLoading } = useQuery({
    queryKey: ["grns", "by-po", id],
    queryFn: async () => (await apiClient.get<DocumentSummary[]>("/grns", { params: { po_id: id } })).data,
  });

  if (isLoading) return <DetailSkeleton />;
  if (!po) return <ErrorState title="Could not load this purchase order" error={error} onRetry={() => refetch()} back={{ to: "/purchase-orders", label: "Back to purchase orders" }} />;
  const run = (name: string) => () => action.mutate(name);
  const receivable = po.status === "CONFIRMED" || po.status === "PARTIALLY_RECEIVED";

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Purchase order"} no={po.doc_no} status={po.status} historyOf={po.id} />}
        extra={
          <Space wrap>
            {po.status === "DRAFT" && (
              <>
                {can("purchase_order.update") && (
                  <Button onClick={() => navigate(`/purchase-orders/${id}/edit`)}>Edit</Button>
                )}
                <ActionButton perm="purchase_order.confirm" type="primary" label="Confirm" confirm="The order cannot be edited after confirmation. Continue?" onConfirm={run("confirm")} loading={action.isPending} />
              </>
            )}
            {receivable && can("grn.create") && (
              <Button type="primary" onClick={() => navigate(`/grns/new?po=${id}`)}>
                Receive
              </Button>
            )}
            {po.status === "PARTIALLY_RECEIVED" && (
              <ActionButton perm="purchase_order.close" label="Close" confirm="The remaining quantity will not be received. Continue?" onConfirm={run("close")} loading={action.isPending} />
            )}
            {(po.status === "DRAFT" || po.status === "CONFIRMED") && (
              <ActionButton perm="purchase_order.cancel" danger label="Cancel" confirm="Cancel this purchase order?" onConfirm={run("cancel")} loading={action.isPending} />
            )}
          </Space>
        }
      >
        <PurchaseOrderSteps status={po.status} />
        <Descriptions column={DESC_COLUMNS}>
          <Descriptions.Item label="Supplier">{po.partner?.code} {po.partner?.name}</Descriptions.Item>
          <Descriptions.Item label="Expected arrival">{po.expected_date ?? <span className="wms-empty-value">Not set</span>}</Descriptions.Item>
          <Descriptions.Item label="Created">{formatDateTime(po.created_at)}</Descriptions.Item>
          <Descriptions.Item label="Remark" span="filled">{po.remark || <span className="wms-empty-value">—</span>}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Lines">
        <DocumentLinesTable
          lines={po.lines}
          columns={[
            { title: "Ordered", dataIndex: "qty_planned", align: "right", render: formatQty },
            { title: "Received", key: "received", render: (_, l) => <QtyProgress done={l.qty_actual} total={l.qty_planned} label="Received" /> },
            { title: "Open", align: "right", render: (_, l) => formatQty(Math.max(l.qty_planned - l.qty_actual, 0)) },
          ]}
        />
      </Card>

      <Card title="Receipts">
        <Table<DocumentSummary>
          rowKey="id"
          size="small"
          pagination={false}
          loading={grnsLoading}
          dataSource={grns}
          scroll={{ x: "max-content" }}
          locale={emptyLocale("No goods receipts yet")}
          columns={[
            { title: "Receipt no.", dataIndex: "doc_no", render: (v: string, r) => <Link className="wms-mono" to={`/grns/${r.id}`}>{v}</Link> },
            { title: "Status", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
            { title: "Receiving location", render: (_, r) => r.location?.code },
            { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
          ]}
        />
      </Card>
    </Space>
  );
}
