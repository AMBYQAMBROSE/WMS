import { DocumentListPage, formatDateTime } from "@/components/documents";

export default function RepacksPage() {
  return (
    <DocumentListPage
      path="repacks"
      createLabel="New repack"
      createPerm="repack.create"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      columns={[
        { title: "Remark", dataIndex: "remark" },
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
      ]}
    />
  );
}
