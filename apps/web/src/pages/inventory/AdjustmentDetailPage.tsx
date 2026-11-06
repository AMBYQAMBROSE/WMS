import { Card, Descriptions, Space, Typography } from "antd";
import { useParams } from "react-router";

import { DESC_COLUMNS, DetailSkeleton, DocTitle, ErrorState, formatQty } from "@/components/ui";
import {
  ActionButton,
  DocumentLinesTable,
  formatDateTime,
  useDocument,
  useDocumentAction,
} from "@/components/documents";

export default function AdjustmentDetailPage() {
  const { id = "" } = useParams();
  const { data: doc, isLoading, error, refetch } = useDocument("adjustments", id);
  const action = useDocumentAction("adjustments", id);

  if (isLoading) return <DetailSkeleton />;
  if (!doc) return <ErrorState title="Could not load this adjustment" error={error} onRetry={() => refetch()} back={{ to: "/adjustments", label: "Back to stock adjustments" }} />;
  const run = (name: string) => () => action.mutate(name);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Stock adjustment"} no={doc.doc_no} status={doc.status} historyOf={doc.id} />}
        extra={
          doc.status === "DRAFT" && (
            <Space wrap>
              <ActionButton
                perm="adjustment.post"
                type="primary"
                label="Approve and post"
                confirm="Posting changes stock by the line quantities immediately and cannot be undone. Continue?"
                onConfirm={run("post")}
                loading={action.isPending}
              />
              <ActionButton perm="adjustment.cancel" danger label="Cancel" confirm="Cancel this adjustment?" onConfirm={run("cancel")} loading={action.isPending} />
            </Space>
          )
        }
      >
        <Descriptions column={DESC_COLUMNS}>
          <Descriptions.Item label="Reason">
            {doc.reason_code && `${doc.reason_code.code} ${doc.reason_code.name}`}
          </Descriptions.Item>
          <Descriptions.Item label="Posted">{formatDateTime(doc.posted_at) || <span className="wms-empty-value">Not yet — needs approval</span>}</Descriptions.Item>
          <Descriptions.Item label="Remark" span="filled">
            {doc.remark || <span className="wms-empty-value">—</span>}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="Lines">
        <DocumentLinesTable
          lines={doc.lines}
          columns={[
            { title: "Location", render: (_, l) => <span className="wms-mono">{l.to_location?.code}</span> },
            {
              title: "Adjustment",
              dataIndex: "qty_actual",
              align: "right",
              render: (v: number) => (
                <Typography.Text type={v < 0 ? "danger" : "success"} className="wms-num" strong>
                  {v > 0 ? `+${formatQty(v)}` : formatQty(v)}
                </Typography.Text>
              ),
            },
            { title: "Batch no.", dataIndex: "batch_no" },
            { title: "Expiry date", dataIndex: "expiry_date" },
          ]}
        />
      </Card>
    </Space>
  );
}
