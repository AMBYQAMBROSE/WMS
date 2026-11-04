import { Card, Descriptions, Space, Spin, Typography } from "antd";
import { useParams } from "react-router";

import { DocTitle } from "@/components/ui";
import {
  ActionButton,
  DocumentLinesTable,
  formatDateTime,
  useDocument,
  useDocumentAction,
} from "@/components/documents";

export default function AdjustmentDetailPage() {
  const { id = "" } = useParams();
  const { data: doc, isLoading } = useDocument("adjustments", id);
  const action = useDocumentAction("adjustments", id);

  if (isLoading || !doc) return <Spin />;
  const run = (name: string) => () => action.mutate(name);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Stock adjustment"} no={doc.doc_no} status={doc.status} />}
        extra={
          doc.status === "DRAFT" && (
            <Space>
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
        <Descriptions column={3}>
          <Descriptions.Item label="Reason">
            {doc.reason_code && `${doc.reason_code.code} ${doc.reason_code.name}`}
          </Descriptions.Item>
          <Descriptions.Item label="Posted">{formatDateTime(doc.posted_at)}</Descriptions.Item>
          <Descriptions.Item label="Remark" span={3}>
            {doc.remark}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="Lines">
        <DocumentLinesTable
          lines={doc.lines}
          columns={[
            { title: "Location", render: (_, l) => l.to_location?.code },
            {
              title: "Adjustment",
              dataIndex: "qty_actual",
              render: (v: number) => (
                <Typography.Text type={v < 0 ? "danger" : "success"}>{v > 0 ? `+${v}` : v}</Typography.Text>
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
