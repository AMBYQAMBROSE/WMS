import { DocumentListPage, formatDateTime } from "@/components/documents";

export default function AdjustmentsPage() {
  return (
    <DocumentListPage
      path="adjustments"
      createLabel="New adjustment"
      createPerm="adjustment.create"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      columns={[
        { title: "Reason", render: (_, r) => r.reason_code && `${r.reason_code.code} ${r.reason_code.name}` },
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
        { title: "Remark", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
