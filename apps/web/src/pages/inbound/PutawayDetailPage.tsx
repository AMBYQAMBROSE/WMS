import { Card, Descriptions, Space, Spin } from "antd";
import { Link, useParams } from "react-router-dom";

import StatusTag from "@/components/StatusTag";
import {
  ActionButton,
  DocumentLinesTable,
  formatDateTime,
  useDocument,
  useDocumentAction,
} from "@/components/documents";

export default function PutawayDetailPage() {
  const { id = "" } = useParams();
  const { data: pa, isLoading } = useDocument("putaways", id);
  const action = useDocumentAction("putaways", id);

  if (isLoading || !pa) return <Spin />;
  const run = (name: string) => () => action.mutate(name);

  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Card
        title={`上架单 ${pa.doc_no}`}
        extra={
          pa.status === "DRAFT" && (
            <Space>
              <ActionButton type="primary" label="过账" confirm="确认货物已放到目标储位？过账后库存立即转移。" onConfirm={run("post")} loading={action.isPending} />
              <ActionButton danger label="取消" confirm="确定取消该上架单？" onConfirm={run("cancel")} loading={action.isPending} />
            </Space>
          )
        }
      >
        <Descriptions column={3}>
          <Descriptions.Item label="状态"><StatusTag status={pa.status} /></Descriptions.Item>
          <Descriptions.Item label="来源收货单">
            {pa.ref_document && <Link to={`/grns/${pa.ref_document.id}`}>{pa.ref_document.doc_no}</Link>}
          </Descriptions.Item>
          <Descriptions.Item label="过账时间">{formatDateTime(pa.posted_at)}</Descriptions.Item>
          <Descriptions.Item label="备注">{pa.remark}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="明细">
        <DocumentLinesTable
          lines={pa.lines}
          columns={[
            { title: "数量", dataIndex: "qty_actual" },
            { title: "批次号", dataIndex: "batch_no" },
            { title: "到期日", dataIndex: "expiry_date" },
            { title: "来源仓位", render: (_, l) => l.from_location?.code },
            { title: "目标储位", render: (_, l) => l.to_location?.code },
          ]}
        />
      </Card>
    </Space>
  );
}
