import { DocumentListPage, formatDateTime } from "@/components/documents";
import { postAndCancel } from "@/components/ListTools";

export default function MovesPage() {
  return (
    <DocumentListPage
      path="moves"
      createLabel="New move"
      createPerm="move.create"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      batchActions={postAndCancel("move")}
      columns={[
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
        { title: "Remark", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
