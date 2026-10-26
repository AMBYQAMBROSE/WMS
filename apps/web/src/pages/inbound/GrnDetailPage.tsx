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

export default function GrnDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data: grn, isLoading } = useDocument("grns", id);
  const action = useDocumentAction("grns", id);
  const { data: putaways } = useQuery({
    queryKey: ["putaways", "by-grn", id],
    queryFn: async () =>
      (await apiClient.get<DocumentSummary[]>("/putaways", { params: { grn_id: id } })).data,
  });

  if (isLoading || !grn) return <Spin />;
  const run = (name: string) => () => action.mutate(name);

  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Card
        title={`收货单 ${grn.doc_no}`}
        extra={
          <Space>
            {grn.status === "DRAFT" && (
              <>
                <ActionButton type="primary" label="过账" confirm="过账后库存立即增加且不能撤销，继续？" onConfirm={run("post")} loading={action.isPending} />
                <ActionButton danger label="取消" confirm="确定取消该收货单？" onConfirm={run("cancel")} loading={action.isPending} />
              </>
            )}
            {grn.status === "POSTED" && (
              <Button type="primary" onClick={() => navigate(`/putaways/new?grn=${id}`)}>
                生成上架单
              </Button>
            )}
          </Space>
        }
      >
        <Descriptions column={3}>
          <Descriptions.Item label="状态"><StatusTag status={grn.status} /></Descriptions.Item>
          <Descriptions.Item label="采购单">
            {grn.ref_document && <Link to={`/purchase-orders/${grn.ref_document.id}`}>{grn.ref_document.doc_no}</Link>}
          </Descriptions.Item>
          <Descriptions.Item label="供应商">{grn.partner?.name}</Descriptions.Item>
          <Descriptions.Item label="收货仓位">{grn.location?.code} {grn.location?.name}</Descriptions.Item>
          <Descriptions.Item label="过账时间">{formatDateTime(grn.posted_at)}</Descriptions.Item>
          <Descriptions.Item label="备注">{grn.remark}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="明细">
        <DocumentLinesTable
          lines={grn.lines}
          columns={[
            { title: "建单时未收", dataIndex: "qty_planned" },
            { title: "实收数量", dataIndex: "qty_actual" },
            { title: "批次号", dataIndex: "batch_no" },
            { title: "到期日", dataIndex: "expiry_date" },
          ]}
        />
      </Card>

      <Card title="上架记录">
        <Table<DocumentSummary>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={putaways}
          columns={[
            { title: "上架单号", dataIndex: "doc_no", render: (v: string, r) => <Link to={`/putaways/${r.id}`}>{v}</Link> },
            { title: "状态", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
            { title: "过账时间", dataIndex: "posted_at", render: formatDateTime },
          ]}
        />
      </Card>
    </Space>
  );
}
