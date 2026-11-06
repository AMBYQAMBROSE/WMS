import { Card, Descriptions, Space } from "antd";
import { Link, useParams } from "react-router";

import { DESC_COLUMNS, DetailSkeleton, DocTitle, ErrorState, formatQty } from "@/components/ui";
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
  const { data: doc, isLoading, error, refetch } = useDocument(path, id);
  const action = useDocumentAction(path, id);

  if (isLoading) return <DetailSkeleton />;
  if (!doc) return <ErrorState title={`Could not load this ${docLabel.toLowerCase()}`} error={error} onRetry={() => refetch()} back={{ to: `/${path}`, label: "Back to the list" }} />;
  const run = (name: string) => () => action.mutate(name);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={docLabel} no={doc.doc_no} status={doc.status} historyOf={doc.id} />}
        extra={
          doc.status === "DRAFT" && (
            <Space wrap>
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
        <Descriptions column={DESC_COLUMNS}>
          {path === "putaways" && (
            <Descriptions.Item label="Source goods receipt">
              {doc.ref_document ? <Link className="wms-mono" to={`/grns/${doc.ref_document.id}`}>{doc.ref_document.doc_no}</Link> : <span className="wms-empty-value">None</span>}
            </Descriptions.Item>
          )}
          <Descriptions.Item label="Posted">{formatDateTime(doc.posted_at) || <span className="wms-empty-value">Not yet</span>}</Descriptions.Item>
          <Descriptions.Item label="Remark">{doc.remark || <span className="wms-empty-value">—</span>}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="Lines">
        <DocumentLinesTable
          lines={doc.lines}
          columns={[
            { title: "Quantity", dataIndex: "qty_actual", align: "right", render: formatQty },
            { title: "Batch no.", dataIndex: "batch_no" },
            { title: "Expiry date", dataIndex: "expiry_date" },
            { title: "From location", render: (_, l) => <span className="wms-mono">{l.from_location?.code}</span> },
            { title: "To location", render: (_, l) => <span className="wms-mono">{l.to_location?.code}</span> },
          ]}
        />
      </Card>
    </Space>
  );
}
