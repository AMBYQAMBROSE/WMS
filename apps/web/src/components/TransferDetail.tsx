import { Card, Descriptions, Space, Spin } from "antd";
import { Link, useParams } from "react-router";

import { DocTitle } from "@/components/ui";
import {
  ActionButton,
  DocumentLinesTable,
  formatDateTime,
  useDocument,
  useDocumentAction,
} from "@/components/documents";

const PERM_PREFIX = { putaways: "putaway", moves: "move" } as const;

/** Putaway / move detail: posting moves the stock from the source to the target location */
export default function TransferDetail({ path, docLabel }: { path: "putaways" | "moves"; docLabel: string }) {
  const { id = "" } = useParams();
  const { data: doc, isLoading } = useDocument(path, id);
  const action = useDocumentAction(path, id);

  if (isLoading || !doc) return <Spin />;
  const run = (name: string) => () => action.mutate(name);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={docLabel} no={doc.doc_no} status={doc.status} />}
        extra={
          doc.status === "DRAFT" && (
            <Space>
              <ActionButton
                perm={`${PERM_PREFIX[path]}.post`}
                type="primary"
                label="Post"
                confirm="Are the goods at the target location? Posting moves the stock immediately."
                onConfirm={run("post")}
                loading={action.isPending}
              />
              <ActionButton perm={`${PERM_PREFIX[path]}.cancel`} danger label="Cancel" confirm={`Cancel this ${docLabel.toLowerCase()}?`} onConfirm={run("cancel")} loading={action.isPending} />
            </Space>
          )
        }
      >
        <Descriptions column={3}>
          {path === "putaways" && (
            <Descriptions.Item label="Source goods receipt">
              {doc.ref_document && <Link to={`/grns/${doc.ref_document.id}`}>{doc.ref_document.doc_no}</Link>}
            </Descriptions.Item>
          )}
          <Descriptions.Item label="Posted">{formatDateTime(doc.posted_at)}</Descriptions.Item>
          <Descriptions.Item label="Remark">{doc.remark}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="Lines">
        <DocumentLinesTable
          lines={doc.lines}
          columns={[
            { title: "Quantity", dataIndex: "qty_actual" },
            { title: "Batch no.", dataIndex: "batch_no" },
            { title: "Expiry date", dataIndex: "expiry_date" },
            { title: "From location", render: (_, l) => l.from_location?.code },
            { title: "To location", render: (_, l) => l.to_location?.code },
          ]}
        />
      </Card>
    </Space>
  );
}
