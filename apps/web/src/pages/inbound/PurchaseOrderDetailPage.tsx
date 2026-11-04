import { useQuery } from "@tanstack/react-query";
import { Button, Card, Descriptions, Space, Spin, Table } from "antd";
import { Link, useNavigate, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { DocumentSummary } from "@/api/types";
import StatusTag from "@/components/StatusTag";
import { DocTitle } from "@/components/ui";
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
  const { data: po, isLoading } = useDocument("purchase-orders", id);
  const action = useDocumentAction("purchase-orders", id);
  const { data: grns } = useQuery({
    queryKey: ["grns", "by-po", id],
    queryFn: async () => (await apiClient.get<DocumentSummary[]>("/grns", { params: { po_id: id } })).data,
  });

  if (isLoading || !po) return <Spin />;
  const run = (name: string) => () => action.mutate(name);
  const receivable = po.status === "CONFIRMED" || po.status === "PARTIALLY_RECEIVED";

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Purchase order"} no={po.doc_no} status={po.status} />}
        extra={
          <Space>
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
        <Descriptions column={3}>
          <Descriptions.Item label="Supplier">{po.partner?.code} {po.partner?.name}</Descriptions.Item>
          <Descriptions.Item label="Expected arrival">{po.expected_date}</Descriptions.Item>
          <Descriptions.Item label="Created">{formatDateTime(po.created_at)}</Descriptions.Item>
          <Descriptions.Item label="Remark" span={2}>{po.remark}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Lines">
        <DocumentLinesTable
          lines={po.lines}
          columns={[
            { title: "Ordered", dataIndex: "qty_planned" },
            { title: "Received", dataIndex: "qty_actual" },
            { title: "Open", render: (_, l) => Math.max(l.qty_planned - l.qty_actual, 0) },
          ]}
        />
      </Card>

      <Card title="Receipts">
        <Table<DocumentSummary>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={grns}
          columns={[
            { title: "Receipt no.", dataIndex: "doc_no", render: (v: string, r) => <Link to={`/grns/${r.id}`}>{v}</Link> },
            { title: "Status", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
            { title: "Receiving location", render: (_, r) => r.location?.code },
            { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
          ]}
        />
      </Card>
    </Space>
  );
}
