import { DocumentListPage, formatDateTime } from "@/components/documents";
import { postAndCancel } from "@/components/ListTools";

export default function RepacksPage() {
  return (
    <DocumentListPage
      path="repacks"
      createLabel="New repack"
      createPerm="repack.create"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      batchActions={postAndCancel("repack")}
      columns={[
        { title: "Remark", dataIndex: "remark", ellipsis: true },
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
      ]}
    />
  );
}
