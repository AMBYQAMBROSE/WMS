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

export default function GrnDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const can = useCan();
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
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Goods receipt"} no={grn.doc_no} status={grn.status} historyOf={grn.id} />}
        extra={
          <Space>
            {grn.status === "DRAFT" && (
              <>
                <ActionButton perm="grn.post" type="primary" label="Post" confirm="Posting increases stock immediately and cannot be undone. Continue?" onConfirm={run("post")} loading={action.isPending} />
                <ActionButton perm="grn.cancel" danger label="Cancel" confirm="Cancel this goods receipt?" onConfirm={run("cancel")} loading={action.isPending} />
              </>
            )}
            {grn.status === "POSTED" && can("putaway.create") && (
              <Button type="primary" onClick={() => navigate(`/putaways/new?grn=${id}`)}>
                Create putaway
              </Button>
            )}
          </Space>
        }
      >
        <Descriptions column={3}>
          <Descriptions.Item label="Purchase order">
            {grn.ref_document && <Link to={`/purchase-orders/${grn.ref_document.id}`}>{grn.ref_document.doc_no}</Link>}
          </Descriptions.Item>
          <Descriptions.Item label="Supplier">{grn.partner?.name}</Descriptions.Item>
          <Descriptions.Item label="Receiving location">{grn.location?.code} {grn.location?.name}</Descriptions.Item>
          <Descriptions.Item label="Posted">{formatDateTime(grn.posted_at)}</Descriptions.Item>
          <Descriptions.Item label="Remark">{grn.remark}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Lines">
        <DocumentLinesTable
          lines={grn.lines}
          columns={[
            { title: "Open at creation", dataIndex: "qty_planned" },
            { title: "Received", dataIndex: "qty_actual" },
            { title: "Batch no.", dataIndex: "batch_no" },
            { title: "Expiry date", dataIndex: "expiry_date" },
          ]}
        />
      </Card>

      <Card title="Putaways">
        <Table<DocumentSummary>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={putaways}
          columns={[
            { title: "Putaway no.", dataIndex: "doc_no", render: (v: string, r) => <Link to={`/putaways/${r.id}`}>{v}</Link> },
            { title: "Status", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
            { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
          ]}
        />
      </Card>
    </Space>
  );
}
