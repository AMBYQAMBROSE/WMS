import { useQuery } from "@tanstack/react-query";
import { Button, Card, Descriptions, Space, Spin, Table } from "antd";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { DocumentSummary } from "@/api/types";
import StatusTag from "@/components/StatusTag";
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
    <Space direction="vertical" style={{ width: "100%" }}>
      <Card
        title={`采购单 ${po.doc_no}`}
        extra={
          <Space>
            {po.status === "DRAFT" && (
              <>
                <Button onClick={() => navigate(`/purchase-orders/${id}/edit`)}>编辑</Button>
                <ActionButton type="primary" label="确认" confirm="确认后不能再修改，继续？" onConfirm={run("confirm")} loading={action.isPending} />
              </>
            )}
            {receivable && (
              <Button type="primary" onClick={() => navigate(`/grns/new?po=${id}`)}>
                收货
              </Button>
            )}
            {po.status === "PARTIALLY_RECEIVED" && (
              <ActionButton label="结案" confirm="结案后剩余数量不再收货，继续？" onConfirm={run("close")} loading={action.isPending} />
            )}
            {(po.status === "DRAFT" || po.status === "CONFIRMED") && (
              <ActionButton danger label="取消" confirm="确定取消该采购单？" onConfirm={run("cancel")} loading={action.isPending} />
            )}
          </Space>
        }
      >
        <Descriptions column={3}>
          <Descriptions.Item label="状态"><StatusTag status={po.status} /></Descriptions.Item>
          <Descriptions.Item label="供应商">{po.partner?.code} {po.partner?.name}</Descriptions.Item>
          <Descriptions.Item label="预计到货">{po.expected_date}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDateTime(po.created_at)}</Descriptions.Item>
          <Descriptions.Item label="备注" span={2}>{po.remark}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="明细">
        <DocumentLinesTable
          lines={po.lines}
          columns={[
            { title: "订购数量", dataIndex: "qty_planned" },
            { title: "已收数量", dataIndex: "qty_actual" },
            { title: "未收数量", render: (_, l) => Math.max(l.qty_planned - l.qty_actual, 0) },
          ]}
        />
      </Card>

      <Card title="收货记录">
        <Table<DocumentSummary>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={grns}
          columns={[
            { title: "收货单号", dataIndex: "doc_no", render: (v: string, r) => <Link to={`/grns/${r.id}`}>{v}</Link> },
            { title: "状态", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
            { title: "收货仓位", render: (_, r) => r.location?.code },
            { title: "过账时间", dataIndex: "posted_at", render: formatDateTime },
          ]}
        />
      </Card>
    </Space>
  );
}
