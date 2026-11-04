import { DocumentListPage, formatDateTime } from "@/components/documents";

export default function ReturnsOutPage() {
  return (
    <DocumentListPage
      path="returns-out"
      createLabel="New return to supplier"
      createPerm="return_out.create"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      columns={[
        { title: "Supplier", render: (_, r) => r.partner?.name },
        { title: "Reason", render: (_, r) => r.reason_code?.name },
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
      ]}
    />
  );
}
