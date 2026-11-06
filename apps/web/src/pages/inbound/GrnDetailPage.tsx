import { useQuery } from "@tanstack/react-query";
import { Button, Card, Descriptions, Space, Table } from "antd";
import { Link, useNavigate, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { DocumentSummary } from "@/api/types";
import StatusTag from "@/components/StatusTag";
import { DESC_COLUMNS, DetailSkeleton, DocTitle, ErrorState, emptyLocale, formatQty } from "@/components/ui";
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
  const { data: grn, isLoading, error, refetch } = useDocument("grns", id);
  const action = useDocumentAction("grns", id);
  const { data: putaways, isLoading: putawaysLoading } = useQuery({
    queryKey: ["putaways", "by-grn", id],
    queryFn: async () =>
      (await apiClient.get<DocumentSummary[]>("/putaways", { params: { grn_id: id } })).data,
  });

  if (isLoading) return <DetailSkeleton />;
  if (!grn) return <ErrorState title="Could not load this goods receipt" error={error} onRetry={() => refetch()} back={{ to: "/grns", label: "Back to goods receipts" }} />;
  const run = (name: string) => () => action.mutate(name);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Goods receipt"} no={grn.doc_no} status={grn.status} historyOf={grn.id} />}
        extra={
          <Space wrap>
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
        <Descriptions column={DESC_COLUMNS}>
          <Descriptions.Item label="Purchase order">
            {grn.ref_document ? <Link className="wms-mono" to={`/purchase-orders/${grn.ref_document.id}`}>{grn.ref_document.doc_no}</Link> : <span className="wms-empty-value">None</span>}
          </Descriptions.Item>
          <Descriptions.Item label="Supplier">{grn.partner?.name}</Descriptions.Item>
          <Descriptions.Item label="Receiving location">{grn.location?.code} {grn.location?.name}</Descriptions.Item>
          <Descriptions.Item label="Posted">{formatDateTime(grn.posted_at) || <span className="wms-empty-value">Not yet</span>}</Descriptions.Item>
          <Descriptions.Item label="Remark">{grn.remark}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Lines">
        <DocumentLinesTable
          lines={grn.lines}
          columns={[
            { title: "Open at creation", dataIndex: "qty_planned", align: "right", render: formatQty },
            { title: "Received", dataIndex: "qty_actual", align: "right", render: formatQty },
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
          loading={putawaysLoading}
          dataSource={putaways}
          locale={emptyLocale("No putaways yet")}
          columns={[
            { title: "Putaway no.", dataIndex: "doc_no", render: (v: string, r) => <Link className="wms-mono" to={`/putaways/${r.id}`}>{v}</Link> },
            { title: "Status", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
            { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
          ]}
        />
      </Card>
    </Space>
  );
}
