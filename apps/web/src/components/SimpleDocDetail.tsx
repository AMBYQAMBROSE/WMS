import { Card, Descriptions, Space, Spin } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link, useParams } from "react-router";

import type { Document, DocumentLine } from "@/api/types";
import { DocTitle } from "@/components/ui";
import { ActionButton, DocumentLinesTable, formatDateTime, useDocument, useDocumentAction } from "@/components/documents";

/** Detail page for two-step documents, draft -> post/cancel (shared by customer returns, returns to supplier and repacks) */
export default function SimpleDocDetail({
  path,
  docLabel,
  permPrefix,
  postConfirm,
  partnerLabel,
  refPath,
  columns,
  lineFilter,
}: {
  path: string;
  docLabel: string;
  permPrefix: string;
  postConfirm: string;
  partnerLabel?: string;
  /** Frontend route of the source document (customer return -> sales order, return to supplier -> purchase order) */
  refPath?: string;
  columns: ColumnsType<DocumentLine>;
  /** Group lines for display (repack: consumed / produced); a single "Lines" group when omitted */
  lineFilter?: (doc: Document) => { title: string; lines: DocumentLine[] }[];
}) {
  const { id = "" } = useParams();
  const { data: doc, isLoading } = useDocument(path, id);
  const action = useDocumentAction(path, id);
  if (isLoading || !doc) return <Spin />;
  const run = (name: string) => () => action.mutate(name);
  const groups = lineFilter ? lineFilter(doc) : [{ title: "Lines", lines: doc.lines }];

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={docLabel} no={doc.doc_no} status={doc.status} historyOf={doc.id} />}
        extra={
          doc.status === "DRAFT" && (
            <Space>
              <ActionButton perm={`${permPrefix}.post`} type="primary" label="Post" confirm={postConfirm} onConfirm={run("post")} loading={action.isPending} />
              <ActionButton perm={`${permPrefix}.cancel`} danger label="Cancel" confirm={`Cancel this ${docLabel.toLowerCase()}?`} onConfirm={run("cancel")} loading={action.isPending} />
            </Space>
          )
        }
      >
        <Descriptions column={3}>
          {partnerLabel && (
            <Descriptions.Item label={partnerLabel}>
              {doc.partner?.code} {doc.partner?.name}
            </Descriptions.Item>
          )}
          {refPath && (
            <Descriptions.Item label="Source document">
              {doc.ref_document ? <Link to={`/${refPath}/${doc.ref_document.id}`}>{doc.ref_document.doc_no}</Link> : "None"}
            </Descriptions.Item>
          )}
          {doc.reason_code && (
            <Descriptions.Item label="Reason">
              {doc.reason_code.code} {doc.reason_code.name}
            </Descriptions.Item>
          )}
          <Descriptions.Item label="Posted">{formatDateTime(doc.posted_at)}</Descriptions.Item>
          <Descriptions.Item label="Remark">{doc.remark}</Descriptions.Item>
        </Descriptions>
      </Card>
      {groups.map((g) => (
        <Card key={g.title} title={g.title}>
          <DocumentLinesTable lines={g.lines} columns={columns} />
        </Card>
      ))}
    </Space>
  );
}
