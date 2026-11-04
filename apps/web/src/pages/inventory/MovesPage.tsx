import { DocumentListPage, formatDateTime } from "@/components/documents";

export default function MovesPage() {
  return (
    <DocumentListPage
      path="moves"
      createLabel="New move"
      createPerm="move.create"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      columns={[
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
        { title: "Remark", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
