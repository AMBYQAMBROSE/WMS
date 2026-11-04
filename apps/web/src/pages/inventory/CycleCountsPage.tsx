import { DocumentListPage, formatDateTime } from "@/components/documents";

export default function CycleCountsPage() {
  return (
    <DocumentListPage
      path="cycle-counts"
      createLabel="Start cycle count"
      createPerm="cycle_count.create"
      statuses={["COUNTING", "POSTED", "CANCELLED"]}
      batchActions={[{ key: "cancel", label: "Cancel", perm: "cycle_count.cancel", statuses: ["COUNTING"], danger: true }]}
      columns={[
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
        { title: "Remark", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
